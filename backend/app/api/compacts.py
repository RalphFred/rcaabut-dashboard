from pathlib import Path
from tempfile import NamedTemporaryFile
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.deps import require_library_access
from app.models import ApprovalLog, Course, CourseCompact, ProcessingJob, Topic, User
from app.services.fallbacks import parse_course_compact_fallback
from app.services.gemini import parse_course_compact
from app.services.pdf import extract_text_from_pdf
from app.utils import dumps

router = APIRouter(prefix="/compacts", tags=["compacts"])

PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


def _safe_topic(row: dict) -> dict:
    title = str(row.get("topic_title") or row.get("topic") or "").strip()
    if not title:
        title = "Untitled topic"
    lowered = title.lower()
    skip = any(word in lowered for word in ["revision", "examination", "exam"])
    return {
        "module_number": row.get("module_number"),
        "module_title": row.get("module_title") or "",
        "week_number": row.get("week_number"),
        "topic_title": title,
        "subtopics": row.get("subtopics") or [],
        "outcomes": row.get("outcomes") or [],
        "is_searchable": bool(row.get("is_searchable", True)) and not skip,
        "extraction_confidence": float(row.get("extraction_confidence") or 0.75),
    }


def parse_compact_job(job_id: int, compact_id: int, temp_path: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        compact = db.get(CourseCompact, compact_id)
        if job is None or compact is None:
            return
        job.status = "running"
        job.progress = 15
        job.message = "Extracting text from PDF"
        db.commit()

        extracted_text = extract_text_from_pdf(Path(temp_path))
        compact.extracted_text = extracted_text
        compact.status = "text_extracted"
        job.progress = 40
        job.message = "Parsing compact with AI"
        db.commit()

        try:
            parsed = parse_course_compact(extracted_text)
        except Exception:
            parsed = parse_course_compact_fallback(extracted_text)

        course = Course(
            course_code=(parsed.get("course_code") or "UNKNOWN").strip(),
            course_title=(parsed.get("course_title") or "Untitled Course Compact").strip(),
            college=(parsed.get("college") or "").strip() or None,
            department=(parsed.get("department") or "").strip() or None,
            programme=(parsed.get("programme") or "").strip() or None,
            level=(parsed.get("level") or "").strip() or None,
            semester=(parsed.get("semester") or "").strip() or None,
            session=(parsed.get("session") or "").strip() or None,
            lecturers_json=dumps([item for item in parsed.get("lecturers", []) if item]),
            description=(parsed.get("description") or "").strip() or None,
            status="extracted",
            uploaded_by_id=compact.uploaded_by_id,
        )
        db.add(course)
        db.flush()

        for raw_topic in parsed.get("topics", []):
            topic = _safe_topic(raw_topic)
            db.add(
                Topic(
                    course_id=course.id,
                    module_number=topic["module_number"],
                    module_title=topic["module_title"],
                    week_number=topic["week_number"],
                    topic_title=topic["topic_title"],
                    subtopics_json=dumps(topic["subtopics"]),
                    outcomes_json=dumps(topic["outcomes"]),
                    extraction_confidence=topic["extraction_confidence"],
                    is_searchable=topic["is_searchable"],
                )
            )

        compact.course_id = course.id
        compact.status = "extracted"
        job.course_id = course.id
        job.status = "completed"
        job.progress = 100
        job.message = "Compact extracted and ready for topic review"
        job.finished_at = datetime.utcnow()
        db.add(
            ApprovalLog(
                actor_id=compact.uploaded_by_id,
                action="compact_extracted",
                entity_type="course",
                entity_id=course.id,
                after_json=dumps(
                    {
                        "compact_id": compact.id,
                        "filename": compact.original_filename,
                        "course_code": course.course_code,
                        "course_title": course.course_title,
                        "topics_extracted": len(parsed.get("topics", [])),
                    }
                ),
            )
        )
        db.commit()
    except Exception as exc:
        if "job" in locals() and job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
        if "compact" in locals() and compact is not None:
            compact.status = "failed"
            compact.error_message = str(exc)
            db.add(
                ApprovalLog(
                    actor_id=compact.uploaded_by_id,
                    action="compact_extraction_failed",
                    entity_type="course_compact",
                    entity_id=compact.id,
                    after_json=dumps({"filename": compact.original_filename, "error": str(exc)}),
                )
            )
        db.commit()
    finally:
        Path(temp_path).unlink(missing_ok=True)
        db.close()


@router.post("/upload")
async def upload_compact(
    background_tasks: BackgroundTasks,
    compact_pdf: UploadFile = File(...),
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    filename = compact_pdf.filename or "course-compact.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only course compact PDFs are allowed")
    if compact_pdf.content_type and compact_pdf.content_type not in PDF_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    content = await compact_pdf.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")
    max_bytes = settings.max_compact_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"PDF exceeds {settings.max_compact_upload_mb} MB upload limit")
    if not content.lstrip().startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")

    with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(content)
        temp_path = temp_file.name

    compact = CourseCompact(
        original_filename=filename,
        content_type=compact_pdf.content_type,
        file_size=len(content),
        status="uploaded",
        uploaded_by_id=current_user.id,
    )
    db.add(compact)
    db.flush()
    job = ProcessingJob(compact_id=compact.id, job_type="compact_extraction", status="queued", progress=0)
    db.add(job)
    db.flush()
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="compact_uploaded",
            entity_type="course_compact",
            entity_id=compact.id,
            after_json=dumps({"filename": filename, "file_size": len(content), "job_id": job.id}),
        )
    )
    db.commit()
    db.refresh(compact)
    db.refresh(job)

    background_tasks.add_task(parse_compact_job, job.id, compact.id, temp_path)
    return {"compact_id": compact.id, "job_id": job.id, "status": compact.status}
