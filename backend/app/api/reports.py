from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_library_access
from app.models import ApprovalLog, ApprovedResource, CandidateResource, Course, ExportRecord, ProcessingJob, Topic, User
from app.utils import loads

router = APIRouter(prefix="/reports", tags=["reports"])


def _actor_name(db: Session, actor_id: int | None) -> str:
    if actor_id is None:
        return "System"
    actor = db.get(User, actor_id)
    return actor.full_name if actor else "Unknown user"


def _course_label(db: Session, course_id: int | None) -> str:
    if course_id is None:
        return "Unknown course"
    course = db.get(Course, course_id)
    if course is None:
        return "Unknown course"
    return f"{course.course_code} - {course.course_title}"


def _export_filename(db: Session, row: ExportRecord) -> str:
    course = db.get(Course, row.course_id)
    course_code = course.course_code if course and course.course_code else "course"
    extension = "html" if row.export_type == "html" else row.export_type
    return f"{course_code}_stored_rcaabut_export.{extension}"


def _export_media_type(export_type: str) -> str:
    if export_type == "csv":
        return "text/csv"
    if export_type == "html":
        return "text/html"
    return "application/json"


@router.get("/activity")
def activity(_: User = Depends(require_library_access), db: Session = Depends(get_db)) -> dict:
    logs = db.query(ApprovalLog).order_by(ApprovalLog.created_at.desc()).limit(100).all()
    return {
        "activity": [
            {
                "id": log.id,
                "actor": _actor_name(db, log.actor_id),
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "before": loads(log.before_json, None),
                "after": loads(log.after_json, None),
                "created_at": log.created_at,
            }
            for log in logs
        ]
    }


@router.get("/exports")
def exports(_: User = Depends(require_library_access), db: Session = Depends(get_db)) -> dict:
    rows = db.query(ExportRecord).order_by(ExportRecord.created_at.desc()).limit(40).all()
    return {
        "exports": [
            {
                "id": row.id,
                "course_id": row.course_id,
                "course": _course_label(db, row.course_id),
                "export_type": row.export_type,
                "created_by": _actor_name(db, row.created_by_id),
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.get("/exports/{export_id}/download")
def download_export(export_id: int, _: User = Depends(require_library_access), db: Session = Depends(get_db)) -> Response:
    row = db.get(ExportRecord, export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Export not found")
    filename = _export_filename(db, row)
    return Response(
        row.payload_json,
        media_type=_export_media_type(row.export_type),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/evaluation")
def evaluation(_: User = Depends(require_library_access), db: Session = Depends(get_db)) -> dict:
    courses = db.query(Course).all()
    topics = db.query(Topic).all()
    candidates = db.query(CandidateResource).all()
    approved = db.query(ApprovedResource).all()
    completed_jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.status == "completed", ProcessingJob.finished_at.isnot(None))
        .all()
    )

    durations = [
        max((job.finished_at - job.created_at).total_seconds(), 0)
        for job in completed_jobs
        if job.finished_at is not None
    ]
    source_breakdown: dict[str, int] = {}
    category_breakdown: dict[str, int] = {}
    status_breakdown: dict[str, int] = {}
    confidence_values = [topic.extraction_confidence for topic in topics]

    for candidate in candidates:
        source_breakdown[candidate.source_system] = source_breakdown.get(candidate.source_system, 0) + 1
        category_breakdown[candidate.category] = category_breakdown.get(candidate.category, 0) + 1
        status_breakdown[candidate.status] = status_breakdown.get(candidate.status, 0) + 1

    total_candidates = len(candidates)
    total_approved = len(approved)
    searchable_topics = [topic for topic in topics if topic.is_searchable]
    avg_candidates_per_topic = total_candidates / len(searchable_topics) if searchable_topics else 0

    return {
        "summary": {
            "courses": len(courses),
            "topics_extracted": len(topics),
            "searchable_topics": len(searchable_topics),
            "candidate_resources": total_candidates,
            "approved_resources": total_approved,
            "approval_rate": round(total_approved / total_candidates, 3) if total_candidates else 0,
            "average_candidates_per_searchable_topic": round(avg_candidates_per_topic, 2),
            "average_extraction_confidence": round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0,
            "average_completed_job_seconds": round(sum(durations) / len(durations), 2) if durations else 0,
        },
        "source_breakdown": source_breakdown,
        "category_breakdown": category_breakdown,
        "candidate_status_breakdown": status_breakdown,
    }
