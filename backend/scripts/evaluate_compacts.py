import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter

DEFAULT_DATABASE = Path("/private/tmp/rcaabut-dashboard-evaluation.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE}")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if os.environ.get("EVALUATION_RESET", "1") == "1" and DEFAULT_DATABASE.exists():
    DEFAULT_DATABASE.unlink()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


DEFAULT_PDFS = [
    Path("/Users/kxgbaorun/Downloads/MAT225 Course Compact_2324.pdf"),
    Path("/Users/kxgbaorun/Downloads/CSC216_Course_Compact.pdf"),
    Path("/Users/kxgbaorun/Documents/2025_2026 NUC-COS331_CSC415 AI_Course_Compact.pdf"),
]


def discover_pdfs() -> list[Path]:
    configured = os.environ.get("EVALUATION_PDFS")
    if configured:
        return [Path(item).expanduser() for item in configured.split(os.pathsep) if Path(item).expanduser().exists()]
    return [path for path in DEFAULT_PDFS if path.exists()]


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@rcaabut.local", "password": "ChangeMe123!"},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def evaluate_pdf(client: TestClient, headers: dict[str, str], pdf_path: Path) -> dict:
    started = perf_counter()
    with pdf_path.open("rb") as handle:
        upload = client.post(
            "/compacts/upload",
            headers=headers,
            files={"compact_pdf": (pdf_path.name, handle, "application/pdf")},
        )
    upload.raise_for_status()
    extraction_job_id = upload.json()["job_id"]
    extraction_job = client.get(f"/jobs/{extraction_job_id}", headers=headers)
    extraction_job.raise_for_status()
    course_id = extraction_job.json()["course_id"]
    if not course_id:
        raise AssertionError(f"{pdf_path.name}: extraction did not create a course")

    detail = client.get(f"/courses/{course_id}", headers=headers)
    detail.raise_for_status()
    detail_json = detail.json()
    topics = detail_json["topics"]
    if not topics:
        raise AssertionError(f"{pdf_path.name}: no topics extracted")

    confirm = client.post(f"/courses/{course_id}/topics/confirm", headers=headers)
    confirm.raise_for_status()
    generation = client.post(f"/courses/{course_id}/generate-resources", headers=headers)
    generation.raise_for_status()
    generation_job_id = generation.json()["job_id"]
    generation_job = client.get(f"/jobs/{generation_job_id}", headers=headers)
    generation_job.raise_for_status()
    if generation_job.json()["status"] != "completed":
        raise AssertionError(f"{pdf_path.name}: resource generation did not complete")

    detail = client.get(f"/courses/{course_id}", headers=headers)
    detail.raise_for_status()
    detail_json = detail.json()
    course = detail_json["course"]
    topics = detail_json["topics"]
    candidates = detail_json["candidates"]
    searchable_topics = [topic for topic in topics if topic["is_searchable"]]
    non_searchable_topics = [topic for topic in topics if not topic["is_searchable"]]
    if searchable_topics and len(candidates) < len(searchable_topics):
        raise AssertionError(f"{pdf_path.name}: candidate count is lower than searchable topic count")

    candidates_by_topic: dict[int, int] = {}
    for candidate in candidates:
        candidates_by_topic[candidate["topic_id"]] = candidates_by_topic.get(candidate["topic_id"], 0) + 1

    approved_resource_id = None
    if candidates:
        first = candidates[0]
        review = client.post(
            f"/courses/{course_id}/candidates/{first['id']}/review",
            headers=headers,
            json={"action": "approve"},
        )
        review.raise_for_status()
        approved = review.json()["approved_resource"]
        approved_resource_id = approved["id"] if approved else None

    json_export = client.post(f"/courses/{course_id}/exports/json", headers=headers)
    json_export.raise_for_status()
    csv_export = client.get(f"/courses/{course_id}/exports/csv", headers=headers)
    csv_export.raise_for_status()

    return {
        "pdf": str(pdf_path),
        "course_id": course_id,
        "course_code": course["course_code"],
        "course_title": course["course_title"],
        "topics_extracted": len(topics),
        "searchable_topics": len(searchable_topics),
        "non_searchable_topics": len(non_searchable_topics),
        "candidate_resources": len(candidates),
        "average_candidates_per_searchable_topic": round(len(candidates) / len(searchable_topics), 2)
        if searchable_topics
        else 0,
        "minimum_candidates_for_a_searchable_topic": min(
            [candidates_by_topic.get(topic["id"], 0) for topic in searchable_topics],
            default=0,
        ),
        "average_extraction_confidence": round(mean([topic["extraction_confidence"] for topic in topics]), 3),
        "approved_resource_id": approved_resource_id,
        "json_export_topics": len(json_export.json()["payload"]["resources_by_topics"]),
        "csv_export_rows": max(len(csv_export.text.splitlines()) - 1, 0),
        "elapsed_seconds": round(perf_counter() - started, 2),
    }


def write_reports(output_dir: Path, results: list[dict], aggregate: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(UTC).isoformat(), "aggregate": aggregate, "courses": results}
    (output_dir / "compact-evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Compact Evaluation Results",
        "",
        f"Generated at: {payload['generated_at']}",
        "",
        "## Aggregate",
        "",
        f"- Course compacts processed: {aggregate['course_compacts_processed']}",
        f"- Topics extracted: {aggregate['topics_extracted']}",
        f"- Searchable topics: {aggregate['searchable_topics']}",
        f"- Candidate resources: {aggregate['candidate_resources']}",
        f"- Average candidates per searchable topic: {aggregate['average_candidates_per_searchable_topic']}",
        f"- Average extraction confidence: {aggregate['average_extraction_confidence']}",
        "",
        "## Per Compact",
        "",
        "| Compact | Course | Topics | Searchable | Candidates | Min/topic | Confidence | Seconds |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    Path(row["pdf"]).name,
                    f"{row['course_code']} - {row['course_title']}",
                    str(row["topics_extracted"]),
                    str(row["searchable_topics"]),
                    str(row["candidate_resources"]),
                    str(row["minimum_candidates_for_a_searchable_topic"]),
                    str(row["average_extraction_confidence"]),
                    str(row["elapsed_seconds"]),
                ]
            )
            + " |"
        )
    (output_dir / "compact-evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    pdfs = discover_pdfs()
    if not pdfs:
        raise SystemExit("No evaluation PDFs found. Set EVALUATION_PDFS with path-separated PDF paths.")

    default_output_dir = Path(__file__).resolve().parents[2] / "evaluation-results"
    output_dir = Path(os.environ.get("EVALUATION_OUTPUT_DIR", str(default_output_dir))).resolve()
    with TestClient(app) as client:
        ready = client.get("/health/ready")
        ready.raise_for_status()
        headers = login(client)
        results = [evaluate_pdf(client, headers, pdf_path) for pdf_path in pdfs]

        total_searchable = sum(row["searchable_topics"] for row in results)
        total_candidates = sum(row["candidate_resources"] for row in results)
        aggregate = {
            "course_compacts_processed": len(results),
            "topics_extracted": sum(row["topics_extracted"] for row in results),
            "searchable_topics": total_searchable,
            "non_searchable_topics": sum(row["non_searchable_topics"] for row in results),
            "candidate_resources": total_candidates,
            "average_candidates_per_searchable_topic": round(total_candidates / total_searchable, 2)
            if total_searchable
            else 0,
            "average_extraction_confidence": round(mean([row["average_extraction_confidence"] for row in results]), 3),
            "total_elapsed_seconds": round(sum(row["elapsed_seconds"] for row in results), 2),
        }
        write_reports(output_dir, results, aggregate)
        print(json.dumps({"output_dir": str(output_dir), "aggregate": aggregate, "courses": results}, indent=2))


if __name__ == "__main__":
    main()
