import os
import sys
from uuid import uuid4
from pathlib import Path

DEFAULT_DATABASE = Path("/private/tmp/rcaabut-dashboard-smoke.db")
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE}"
os.environ.setdefault("DATABASE_URL", DEFAULT_DATABASE_URL)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if os.environ["DATABASE_URL"] == DEFAULT_DATABASE_URL and os.environ.get("SMOKE_RESET", "1") == "1" and DEFAULT_DATABASE.exists():
    DEFAULT_DATABASE.unlink()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


DEFAULT_PDFS = [
    Path("/Users/kxgbaorun/Downloads/MAT225 Course Compact_2324.pdf"),
    Path("/Users/kxgbaorun/Downloads/CSC216_Course_Compact.pdf"),
    Path("/Users/kxgbaorun/Documents/2025_2026 NUC-COS331_CSC415 AI_Course_Compact.pdf"),
]


def find_pdf() -> Path:
    configured = os.environ.get("SMOKE_PDF")
    if configured:
        path = Path(configured)
        if path.exists():
            return path
    for path in DEFAULT_PDFS:
        if path.exists():
            return path
    raise SystemExit("No smoke-test PDF found. Set SMOKE_PDF=/path/to/course-compact.pdf")


def main() -> None:
    pdf_path = find_pdf()
    with TestClient(app) as client:
        ready = client.get("/health/ready")
        ready.raise_for_status()
        assert ready.json()["database"] == "ok", "Readiness check did not confirm database"

        login = client.post(
            "/auth/login",
            json={"email": "admin@rcaabut.local", "password": "ChangeMe123!"},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        admin_id = login.json()["user"]["id"]

        self_disable = client.patch(
            f"/users/{admin_id}",
            headers=headers,
            json={"is_active": False},
        )
        assert self_disable.status_code == 400, "Super Admin was allowed to disable their own account"
        self_demote = client.patch(
            f"/users/{admin_id}",
            headers=headers,
            json={"role": "library_staff"},
        )
        assert self_demote.status_code == 400, "Super Admin was allowed to demote their own account"

        staff_email = f"staff-{uuid4().hex[:8]}@rcaabut.local"
        staff_create = client.post(
            "/users",
            headers=headers,
            json={
                "full_name": "Smoke Test Staff",
                "email": staff_email,
                "password": "Initial123!",
                "role": "library_staff",
                "is_active": True,
            },
        )
        staff_create.raise_for_status()
        staff_id = staff_create.json()["user"]["id"]
        staff_reset = client.patch(
            f"/users/{staff_id}",
            headers=headers,
            json={"password": "Reset123!"},
        )
        staff_reset.raise_for_status()
        staff_login = client.post(
            "/auth/login",
            json={"email": staff_email, "password": "Reset123!"},
        )
        staff_login.raise_for_status()
        assert staff_login.json()["user"]["role"] == "library_staff", "Reset staff login did not return Library Staff role"
        staff_headers = {"Authorization": f"Bearer {staff_login.json()['access_token']}"}
        staff_change = client.post(
            "/auth/change-password",
            headers=staff_headers,
            json={"current_password": "Reset123!", "new_password": "Changed123!"},
        )
        staff_change.raise_for_status()
        staff_changed_login = client.post(
            "/auth/login",
            json={"email": staff_email, "password": "Changed123!"},
        )
        staff_changed_login.raise_for_status()
        assert staff_changed_login.json()["user"]["id"] == staff_id, "Changed staff password did not log into the same user"
        changed_staff_headers = {"Authorization": f"Bearer {staff_changed_login.json()['access_token']}"}
        staff_disable = client.patch(
            f"/users/{staff_id}",
            headers=headers,
            json={"is_active": False},
        )
        staff_disable.raise_for_status()
        inactive_staff_login = client.post(
            "/auth/login",
            json={"email": staff_email, "password": "Changed123!"},
        )
        assert inactive_staff_login.status_code == 403, "Inactive staff account was allowed to log in"
        inactive_token_check = client.get("/auth/me", headers=changed_staff_headers)
        assert inactive_token_check.status_code == 401, "Disabled staff token was still accepted"
        staff_enable = client.patch(
            f"/users/{staff_id}",
            headers=headers,
            json={"is_active": True},
        )
        staff_enable.raise_for_status()
        reenabled_staff_login = client.post(
            "/auth/login",
            json={"email": staff_email, "password": "Changed123!"},
        )
        reenabled_staff_login.raise_for_status()
        assert reenabled_staff_login.json()["user"]["id"] == staff_id, "Re-enabled staff account could not log in"

        sources = client.get("/sources", headers=headers)
        sources.raise_for_status()
        source_rows = sources.json()["sources"]
        assert source_rows, "Default source connectors were not seeded"
        first_source = source_rows[0]
        toggle = client.patch(
            f"/sources/{first_source['id']}",
            headers=headers,
            json={
                "display_name": first_source["display_name"],
                "source_type": first_source["source_type"],
                "base_url": first_source.get("base_url"),
                "is_enabled": first_source["is_enabled"],
                "notes": first_source.get("notes") or "Smoke-test verified source.",
            },
        )
        toggle.raise_for_status()

        invalid_upload = client.post(
            "/compacts/upload",
            headers=headers,
            files={"compact_pdf": ("not-a-compact.txt", b"not a pdf", "text/plain")},
        )
        assert invalid_upload.status_code == 400, "Non-PDF upload was not rejected"
        fake_pdf_upload = client.post(
            "/compacts/upload",
            headers=headers,
            files={"compact_pdf": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
        assert fake_pdf_upload.status_code == 400, "Invalid PDF bytes were not rejected"

        with pdf_path.open("rb") as handle:
            upload = client.post(
                "/compacts/upload",
                headers=headers,
                files={"compact_pdf": (pdf_path.name, handle, "application/pdf")},
            )
        upload.raise_for_status()
        job_id = upload.json()["job_id"]
        job = client.get(f"/jobs/{job_id}", headers=headers)
        job.raise_for_status()
        course_id = job.json()["course_id"]
        assert course_id, "Extraction job did not create a course"

        detail = client.get(f"/courses/{course_id}", headers=headers)
        detail.raise_for_status()
        topics = detail.json()["topics"]
        assert topics, "No topics were extracted"

        status_bypass = client.patch(
            f"/courses/{course_id}",
            headers=headers,
            json={
                "course_code": detail.json()["course"]["course_code"],
                "course_title": detail.json()["course"]["course_title"],
                "college": detail.json()["course"]["college"],
                "department": detail.json()["course"]["department"],
                "programme": detail.json()["course"]["programme"],
                "level": detail.json()["course"]["level"],
                "semester": detail.json()["course"]["semester"],
                "session": detail.json()["course"]["session"],
                "lecturers": detail.json()["course"]["lecturers"],
                "description": detail.json()["course"]["description"],
                "status": "topics_reviewed",
            },
        )
        status_bypass.raise_for_status()
        assert status_bypass.json()["course"]["status"] == "extracted", "Metadata update changed workflow status"

        premature_generation = client.post(f"/courses/{course_id}/generate-resources", headers=headers)
        assert premature_generation.status_code == 409, "Resource generation was allowed before topic confirmation"

        for topic in topics:
            make_unsearchable = client.patch(
                f"/courses/{course_id}/topics/{topic['id']}",
                headers=headers,
                json={
                    "module_number": topic["module_number"],
                    "module_title": topic["module_title"],
                    "week_number": topic["week_number"],
                    "topic_title": topic["topic_title"],
                    "subtopics": topic["subtopics"],
                    "outcomes": topic["outcomes"],
                    "is_searchable": False,
                },
            )
            make_unsearchable.raise_for_status()
        client.post(f"/courses/{course_id}/topics/confirm", headers=headers).raise_for_status()
        no_searchable_generation = client.post(f"/courses/{course_id}/generate-resources", headers=headers)
        assert no_searchable_generation.status_code == 409, "Resource generation was allowed with no searchable topics"

        for topic in topics:
            restore_topic = client.patch(
                f"/courses/{course_id}/topics/{topic['id']}",
                headers=headers,
                json={
                    "module_number": topic["module_number"],
                    "module_title": topic["module_title"],
                    "week_number": topic["week_number"],
                    "topic_title": topic["topic_title"],
                    "subtopics": topic["subtopics"],
                    "outcomes": topic["outcomes"],
                    "is_searchable": topic["is_searchable"],
                },
            )
            restore_topic.raise_for_status()

        client.post(f"/courses/{course_id}/topics/confirm", headers=headers).raise_for_status()
        client.post(f"/courses/{course_id}/generate-resources", headers=headers).raise_for_status()

        detail = client.get(f"/courses/{course_id}", headers=headers)
        detail.raise_for_status()
        candidates = detail.json()["candidates"]
        searchable_topics = [topic for topic in topics if topic["is_searchable"]]
        assert searchable_topics, "No searchable topics were extracted"
        assert len(candidates) >= len(searchable_topics), "No candidate resources generated"

        empty_json_export = client.post(f"/courses/{course_id}/exports/json", headers=headers)
        assert empty_json_export.status_code == 409, "JSON export was allowed before any resource approval"
        empty_csv_export = client.get(f"/courses/{course_id}/exports/csv", headers=headers)
        assert empty_csv_export.status_code == 409, "CSV export was allowed before any resource approval"
        empty_html_export = client.get(f"/courses/{course_id}/exports/html", headers=headers)
        assert empty_html_export.status_code == 409, "HTML export was allowed before any resource approval"

        cleanup_topic = searchable_topics[-1]
        cleanup_manual_resource = client.post(
            f"/courses/{course_id}/manual-resources",
            headers=headers,
            json={
                "topic_id": cleanup_topic["id"],
                "category": "Books",
                "title": "Smoke-test non-searchable cleanup resource",
                "authors": ["Smoke Tester"],
                "year": 2026,
                "url": "https://example.com/non-searchable-cleanup",
                "note": "Created to verify non-searchable topic cleanup.",
            },
        )
        cleanup_manual_resource.raise_for_status()
        make_cleanup_topic_unsearchable = client.patch(
            f"/courses/{course_id}/topics/{cleanup_topic['id']}",
            headers=headers,
            json={
                "module_number": cleanup_topic["module_number"],
                "module_title": cleanup_topic["module_title"],
                "week_number": cleanup_topic["week_number"],
                "topic_title": cleanup_topic["topic_title"],
                "subtopics": cleanup_topic["subtopics"],
                "outcomes": cleanup_topic["outcomes"],
                "is_searchable": False,
            },
        )
        make_cleanup_topic_unsearchable.raise_for_status()
        assert make_cleanup_topic_unsearchable.json()["candidate_resources_deleted"] >= 1, "Non-searchable topic update did not remove candidates"
        assert make_cleanup_topic_unsearchable.json()["approved_resources_deleted"] >= 1, "Non-searchable topic update did not remove approved resources"
        detail_after_cleanup_topic = client.get(f"/courses/{course_id}", headers=headers)
        detail_after_cleanup_topic.raise_for_status()
        assert all(
            candidate["topic_id"] != cleanup_topic["id"] for candidate in detail_after_cleanup_topic.json()["candidates"]
        ), "Non-searchable topic candidates still appear in course detail"
        assert all(
            resource["topic_id"] != cleanup_topic["id"] for resource in detail_after_cleanup_topic.json()["approved_resources"]
        ), "Non-searchable topic approved resources still appear in course detail"
        manual_for_non_searchable = client.post(
            f"/courses/{course_id}/manual-resources",
            headers=headers,
            json={
                "topic_id": cleanup_topic["id"],
                "category": "Books",
                "title": "Invalid non-searchable topic resource",
                "authors": ["Smoke Tester"],
                "year": 2026,
                "url": "https://example.com/invalid-non-searchable",
                "note": "This should fail because the topic is not searchable.",
            },
        )
        assert manual_for_non_searchable.status_code == 409, "Manual resource was allowed for a non-searchable topic"
        searchable_topics = [topic for topic in searchable_topics if topic["id"] != cleanup_topic["id"]]
        candidates = [
            candidate
            for candidate in detail_after_cleanup_topic.json()["candidates"]
            if candidate["topic_id"] != cleanup_topic["id"]
        ]

        first = candidates[0]
        invalid_candidate_update = client.patch(
            f"/courses/{course_id}/candidates/{first['id']}",
            headers=headers,
            json={
                "category": "Invalid Category",
                "title": first["title"],
                "authors": first["authors"],
                "year": first["year"],
                "abstract": first["abstract"],
                "url": first["url"],
                "match_reason": first["match_reason"],
            },
        )
        assert invalid_candidate_update.status_code == 422, "Invalid candidate category was not rejected"
        invalid_review = client.post(
            f"/courses/{course_id}/candidates/{first['id']}/review",
            headers=headers,
            json={"action": "approve", "category": "Invalid Category"},
        )
        assert invalid_review.status_code == 422, "Invalid review category was not rejected"
        invalid_manual_resource = client.post(
            f"/courses/{course_id}/manual-resources",
            headers=headers,
            json={
                "topic_id": searchable_topics[0]["id"],
                "category": "Invalid Category",
                "title": "Invalid manual resource",
                "authors": ["Smoke Tester"],
                "year": 2026,
                "url": "https://example.com/invalid-manual",
                "note": "This should fail validation.",
            },
        )
        assert invalid_manual_resource.status_code == 422, "Invalid manual resource category was not rejected"

        review = client.post(
            f"/courses/{course_id}/candidates/{first['id']}/review",
            headers=headers,
            json={"action": "approve"},
        )
        review.raise_for_status()
        reject_after_approve = client.post(
            f"/courses/{course_id}/candidates/{first['id']}/review",
            headers=headers,
            json={"action": "reject"},
        )
        reject_after_approve.raise_for_status()
        detail_after_reject = client.get(f"/courses/{course_id}", headers=headers)
        detail_after_reject.raise_for_status()
        rejected_candidate = [
            item for item in detail_after_reject.json()["candidates"] if item["id"] == first["id"]
        ][0]
        assert rejected_candidate["status"] == "rejected", "Candidate reject did not update candidate status"
        approved_after_reject = [
            item
            for item in detail_after_reject.json()["approved_resources"]
            if item["candidate_id"] == first["id"]
        ]
        assert not approved_after_reject, "Rejecting an approved candidate did not remove its approved record"
        reapprove = client.post(
            f"/courses/{course_id}/candidates/{first['id']}/review",
            headers=headers,
            json={"action": "approve"},
        )
        reapprove.raise_for_status()
        second_review = client.post(
            f"/courses/{course_id}/candidates/{first['id']}/review",
            headers=headers,
            json={"action": "approve", "title": first["title"] + " Updated"},
        )
        second_review.raise_for_status()
        approved_id = second_review.json()["approved_resource"]["id"]
        detail_after_review = client.get(f"/courses/{course_id}", headers=headers)
        detail_after_review.raise_for_status()
        approved_for_candidate = [
            item
            for item in detail_after_review.json()["approved_resources"]
            if item["candidate_id"] == first["id"]
        ]
        assert len(approved_for_candidate) == 1, "Duplicate approval record was created"

        invalid_approved_update = client.patch(
            f"/courses/{course_id}/approved-resources/{approved_id}",
            headers=headers,
            json={
                "category": "Invalid Category",
                "title": "Invalid approved resource update",
                "authors": ["Smoke Tester"],
                "year": 2026,
                "url": "https://example.com/invalid-approved",
                "note": "This should fail validation.",
            },
        )
        assert invalid_approved_update.status_code == 422, "Invalid approved resource category was not rejected"
        approved_update = client.patch(
            f"/courses/{course_id}/approved-resources/{approved_id}",
            headers=headers,
            json={
                "category": "Books",
                "title": "Smoke-test approved resource",
                "authors": ["Smoke Tester"],
                "year": 2026,
                "url": "https://example.com/smoke-resource",
                "note": "Updated during smoke test.",
            },
        )
        approved_update.raise_for_status()

        client.post(f"/courses/{course_id}/generate-resources", headers=headers).raise_for_status()
        detail_after_regeneration = client.get(f"/courses/{course_id}", headers=headers)
        detail_after_regeneration.raise_for_status()
        regenerated_detail = detail_after_regeneration.json()
        regenerated_approved = [
            item for item in regenerated_detail["approved_resources"] if item["id"] == approved_id
        ]
        assert regenerated_approved, "Approved resource was lost after resource regeneration"
        assert regenerated_approved[0]["candidate_id"] is None, "Approved resource was not detached from regenerated candidates"
        assert len(regenerated_detail["candidates"]) >= len(searchable_topics), "Regeneration did not create candidate resources"

        json_export = client.post(f"/courses/{course_id}/exports/json", headers=headers)
        json_export.raise_for_status()
        export_payload = json_export.json()["payload"]
        assert export_payload["resource_categories"], "JSON export is missing RCAABUT categories"
        first_topic_group = export_payload["resources_by_topics"][0]
        assert "categories" in first_topic_group, "JSON export is not grouped by category"
        assert "resources" in first_topic_group, "JSON export is missing compatibility resource rows"
        csv_export = client.get(f"/courses/{course_id}/exports/csv", headers=headers)
        csv_export.raise_for_status()
        assert "resource_number" in csv_export.text.splitlines()[0], "CSV export is missing resource numbering"
        html_export = client.get(f"/courses/{course_id}/exports/html", headers=headers)
        html_export.raise_for_status()
        assert "Resources By Topics" in html_export.text, "HTML export is missing RCAABUT heading"
        assert "Smoke-test approved resource" in html_export.text, "HTML export is missing approved resource"

        before_archive_detail = client.get(f"/courses/{course_id}", headers=headers)
        before_archive_detail.raise_for_status()
        assert before_archive_detail.json()["course"]["status"] == "exported", "Export did not update course status"
        archived = client.post(f"/courses/{course_id}/archive", headers=headers)
        archived.raise_for_status()
        assert archived.json()["course"]["status"] == "archived", "Course archive did not update status"
        archived_detail = client.get(f"/courses/{course_id}", headers=headers)
        archived_detail.raise_for_status()
        assert archived_detail.json()["course"]["status"] == "archived", "Archived course detail could not be loaded"
        archived_metadata_update = client.patch(
            f"/courses/{course_id}",
            headers=headers,
            json={
                "course_code": before_archive_detail.json()["course"]["course_code"],
                "course_title": before_archive_detail.json()["course"]["course_title"],
                "college": before_archive_detail.json()["course"]["college"],
                "department": before_archive_detail.json()["course"]["department"],
                "programme": before_archive_detail.json()["course"]["programme"],
                "level": before_archive_detail.json()["course"]["level"],
                "semester": before_archive_detail.json()["course"]["semester"],
                "session": before_archive_detail.json()["course"]["session"],
                "lecturers": before_archive_detail.json()["course"]["lecturers"],
                "description": "Archived mutation should be rejected.",
            },
        )
        assert archived_metadata_update.status_code == 409, "Archived course metadata update was allowed"
        archived_confirm = client.post(f"/courses/{course_id}/topics/confirm", headers=headers)
        assert archived_confirm.status_code == 409, "Archived course topic confirmation was allowed"
        archived_export = client.post(f"/courses/{course_id}/exports/json", headers=headers)
        assert archived_export.status_code == 409, "Archived course export was allowed"
        archive_again = client.post(f"/courses/{course_id}/archive", headers=headers)
        assert archive_again.status_code == 409, "Archived course was archived again"
        restored = client.post(f"/courses/{course_id}/restore", headers=headers)
        restored.raise_for_status()
        assert restored.json()["course"]["status"] == "exported", "Course restore did not preserve previous workflow status"

        approved_delete = client.delete(f"/courses/{course_id}/approved-resources/{approved_id}", headers=headers)
        approved_delete.raise_for_status()

        topic_to_delete = searchable_topics[-1]
        manual_before_topic_delete = client.post(
            f"/courses/{course_id}/manual-resources",
            headers=headers,
            json={
                "topic_id": topic_to_delete["id"],
                "category": "Books",
                "title": "Smoke-test removable topic resource",
                "authors": ["Smoke Tester"],
                "year": 2026,
                "url": "https://example.com/removable-topic-resource",
                "note": "Created to verify topic deletion cleans approved resources.",
            },
        )
        manual_before_topic_delete.raise_for_status()
        topic_delete = client.delete(f"/courses/{course_id}/topics/{topic_to_delete['id']}", headers=headers)
        topic_delete.raise_for_status()
        assert topic_delete.json()["candidate_resources_deleted"] >= 1, "Topic deletion did not remove generated candidates"
        assert topic_delete.json()["approved_resources_deleted"] >= 1, "Topic deletion did not remove approved resources"
        detail_after_topic_delete = client.get(f"/courses/{course_id}", headers=headers)
        detail_after_topic_delete.raise_for_status()
        assert all(
            topic["id"] != topic_to_delete["id"] for topic in detail_after_topic_delete.json()["topics"]
        ), "Deleted topic still appears in course detail"
        assert all(
            candidate["topic_id"] != topic_to_delete["id"] for candidate in detail_after_topic_delete.json()["candidates"]
        ), "Deleted topic candidates still appear in course detail"
        assert all(
            resource["topic_id"] != topic_to_delete["id"] for resource in detail_after_topic_delete.json()["approved_resources"]
        ), "Deleted topic approved resources still appear in course detail"

        activity = client.get("/reports/activity", headers=headers)
        exports = client.get("/reports/exports", headers=headers)
        evaluation = client.get("/reports/evaluation", headers=headers)
        activity.raise_for_status()
        exports.raise_for_status()
        evaluation.raise_for_status()
        assert activity.json()["activity"], "No activity logs returned"
        activity_actions = [item["action"] for item in activity.json()["activity"]]
        for expected_action in [
            "compact_uploaded",
            "compact_extracted",
            "resource_generation_started",
            "resource_generation_completed",
        ]:
            assert expected_action in activity_actions, f"{expected_action} was not written to the activity log"
        export_activity = [
            item for item in activity.json()["activity"] if item["action"] == "export_generated"
        ]
        assert len(export_activity) >= 3, "Export generation was not written to the activity log"
        assert exports.json()["exports"], "No export history returned"
        latest_export_id = exports.json()["exports"][0]["id"]
        stored_export = client.get(f"/reports/exports/{latest_export_id}/download", headers=headers)
        stored_export.raise_for_status()
        assert stored_export.text, "Stored export download returned an empty payload"
        final_detail = detail_after_topic_delete.json()
        final_topic_count = len(final_detail["topics"])
        final_candidate_count = len(final_detail["candidates"])
        assert evaluation.json()["summary"]["topics_extracted"] >= final_topic_count, "Evaluation summary did not include current topics"

        print(
            {
                "pdf": str(pdf_path),
                "course_id": course_id,
                "topics": final_topic_count,
                "candidates": final_candidate_count,
                "activity": len(activity.json()["activity"]),
                "exports": len(exports.json()["exports"]),
                "average_job_seconds": evaluation.json()["summary"]["average_completed_job_seconds"],
                "sources": len(source_rows),
            }
        )


if __name__ == "__main__":
    main()
