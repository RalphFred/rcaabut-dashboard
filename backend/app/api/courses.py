import csv
from html import escape
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.deps import require_library_access
from app.models import (
    ApprovalLog,
    ApprovedResource,
    CandidateResource,
    Course,
    CourseCompact,
    ExportRecord,
    ProcessingJob,
    SourceDatabase,
    Topic,
    User,
)
from app.schemas import (
    ApprovedResourceUpdate,
    CandidateReview,
    CandidateUpdate,
    CourseUpdate,
    ManualResourceCreate,
    TopicCreate,
    TopicUpdate,
)
from app.services.connectors import discover_resource_candidates
from app.services.fallbacks import generate_resources_fallback
from app.services.gemini import rerank_connector_resources
from app.utils import RCAABUT_CATEGORIES, dumps, loads

router = APIRouter(prefix="/courses", tags=["courses"])


def serialize_topic(topic: Topic) -> dict:
    return {
        "id": topic.id,
        "module_number": topic.module_number,
        "module_title": topic.module_title,
        "week_number": topic.week_number,
        "topic_title": topic.topic_title,
        "subtopics": loads(topic.subtopics_json, []),
        "outcomes": loads(topic.outcomes_json, []),
        "extraction_confidence": topic.extraction_confidence,
        "is_searchable": topic.is_searchable,
    }


def serialize_course(course: Course) -> dict:
    return {
        "id": course.id,
        "course_code": course.course_code,
        "course_title": course.course_title,
        "college": course.college,
        "department": course.department,
        "programme": course.programme,
        "level": course.level,
        "semester": course.semester,
        "session": course.session,
        "lecturers": loads(course.lecturers_json, []),
        "description": course.description,
        "status": course.status,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
    }


def serialize_candidate(candidate: CandidateResource) -> dict:
    return {
        "id": candidate.id,
        "course_id": candidate.course_id,
        "topic_id": candidate.topic_id,
        "category": candidate.category,
        "title": candidate.title,
        "authors": loads(candidate.authors_json, []),
        "year": candidate.year,
        "abstract": candidate.abstract,
        "url": candidate.url,
        "source_system": candidate.source_system,
        "relevance_score": candidate.relevance_score,
        "match_reason": candidate.match_reason,
        "status": candidate.status,
    }


def serialize_approved(resource: ApprovedResource) -> dict:
    return {
        "id": resource.id,
        "course_id": resource.course_id,
        "topic_id": resource.topic_id,
        "candidate_id": resource.candidate_id,
        "category": resource.category,
        "title": resource.title,
        "authors": loads(resource.authors_json, []),
        "year": resource.year,
        "url": resource.url,
        "source_system": resource.source_system,
        "note": resource.note,
        "created_at": resource.created_at,
    }


def course_context(course: Course) -> dict:
    return {
        "course_code": course.course_code,
        "course_title": course.course_title,
        "department": course.department,
        "programme": course.programme,
        "description": course.description,
    }


def topic_context(topic: Topic) -> dict:
    return {
        "week_number": topic.week_number,
        "module_title": topic.module_title,
        "topic_title": topic.topic_title,
        "subtopics": loads(topic.subtopics_json, []),
        "outcomes": loads(topic.outcomes_json, []),
    }


def archived_previous_status(db: Session, course_id: int) -> str:
    archive_log = (
        db.query(ApprovalLog)
        .filter(
            ApprovalLog.entity_type == "course",
            ApprovalLog.entity_id == course_id,
            ApprovalLog.action == "course_archived",
        )
        .order_by(ApprovalLog.created_at.desc(), ApprovalLog.id.desc())
        .first()
    )
    before = loads(archive_log.before_json if archive_log else None, {})
    status = before.get("status")
    return status if isinstance(status, str) and status != "archived" else "extracted"


def ensure_course_not_archived(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.status == "archived":
        raise HTTPException(status_code=409, detail="Restore the course before modifying or exporting it")
    return course


def generate_resources_job(job_id: int, course_id: int, actor_id: int | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        course = db.get(Course, course_id)
        if job is None or course is None:
            return
        job.status = "running"
        job.progress = 10
        job.message = "Preparing topics for recommendation"
        db.commit()

        topics = (
            db.query(Topic)
            .filter(Topic.course_id == course_id, Topic.is_searchable.is_(True))
            .order_by(Topic.week_number.asc().nullslast(), Topic.id.asc())
            .all()
        )
        total = max(len(topics), 1)
        enabled_sources = {
            row.source_key
            for row in db.query(SourceDatabase).filter(SourceDatabase.is_enabled.is_(True)).all()
        }
        if not enabled_sources:
            enabled_sources = {"openalex", "crossref", "open_library", "tool_suggestion"}
        (
            db.query(ApprovedResource)
            .filter(ApprovedResource.course_id == course_id, ApprovedResource.candidate_id.isnot(None))
            .update({ApprovedResource.candidate_id: None}, synchronize_session=False)
        )
        db.query(CandidateResource).filter(CandidateResource.course_id == course_id).delete()
        db.commit()

        for index, topic in enumerate(topics, start=1):
            query = " ".join(
                str(part)
                for part in [
                    course.course_title,
                    topic.topic_title,
                    " ".join(loads(topic.subtopics_json, [])[:3]),
                ]
                if part
            )
            connector_rows = discover_resource_candidates(query, limit=12, enabled_sources=enabled_sources)
            try:
                rows = rerank_connector_resources(course_context(course), topic_context(topic), connector_rows)
            except Exception:
                rows = connector_rows[:5]
            if not rows:
                rows = generate_resources_fallback(course_context(course), topic_context(topic))
            elif len(rows) < 5:
                seen = {(row.get("url") or row.get("title") or "").strip().lower() for row in rows}
                for fallback_row in generate_resources_fallback(course_context(course), topic_context(topic)):
                    key = (fallback_row.get("url") or fallback_row.get("title") or "").strip().lower()
                    if key not in seen:
                        rows.append(fallback_row)
                        seen.add(key)
                    if len(rows) >= 5:
                        break
            for row in rows[:5]:
                db.add(
                    CandidateResource(
                        course_id=course.id,
                        topic_id=topic.id,
                        category=row.get("category", "Books"),
                        title=row.get("title", "Untitled resource"),
                        authors_json=dumps(row.get("authors", [])),
                        year=row.get("year"),
                        abstract=row.get("abstract") or "",
                        url=row.get("url") or "",
                        source_system=row.get("source_system") or "metadata_connector",
                        source_record_id=row.get("source_record_id"),
                        relevance_score=float(row.get("relevance_score") or 0),
                        match_reason=row.get("match_reason") or "",
                    )
                )
            job.progress = 10 + int((index / total) * 85)
            job.message = f"Generated resources for week {topic.week_number or index}"
            db.commit()

        course.status = "resources_generated"
        job.status = "completed"
        job.progress = 100
        job.message = "Resources generated"
        job.finished_at = datetime.utcnow()
        db.add(
            ApprovalLog(
                actor_id=actor_id,
                action="resource_generation_completed",
                entity_type="course",
                entity_id=course_id,
                after_json=dumps(
                    {
                        "job_id": job.id,
                        "searchable_topics": len(topics),
                        "candidate_resources": db.query(CandidateResource).filter(CandidateResource.course_id == course_id).count(),
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
            db.add(
                ApprovalLog(
                    actor_id=actor_id,
                    action="resource_generation_failed",
                    entity_type="course",
                    entity_id=course_id,
                    after_json=dumps({"job_id": job.id, "error": str(exc)}),
                )
            )
            db.commit()
    finally:
        db.close()


@router.get("")
def list_courses(_: User = Depends(require_library_access), db: Session = Depends(get_db)) -> dict:
    courses = db.query(Course).order_by(Course.created_at.desc()).all()
    return {"courses": [serialize_course(course) for course in courses]}


@router.get("/{course_id}")
def get_course(course_id: int, _: User = Depends(require_library_access), db: Session = Depends(get_db)) -> dict:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    topics = db.query(Topic).filter(Topic.course_id == course_id).order_by(Topic.week_number.asc().nullslast()).all()
    candidates = db.query(CandidateResource).filter(CandidateResource.course_id == course_id).all()
    approved = db.query(ApprovedResource).filter(ApprovedResource.course_id == course_id).all()
    return {
        "course": serialize_course(course),
        "topics": [serialize_topic(topic) for topic in topics],
        "candidates": [serialize_candidate(candidate) for candidate in candidates],
        "approved_resources": [serialize_approved(resource) for resource in approved],
    }


@router.patch("/{course_id}")
def update_course(
    course_id: int,
    payload: CourseUpdate,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = ensure_course_not_archived(db, course_id)
    before = serialize_course(course)
    course.course_code = payload.course_code.strip() or course.course_code
    course.course_title = payload.course_title.strip() or course.course_title
    course.college = payload.college
    course.department = payload.department
    course.programme = payload.programme
    course.level = payload.level
    course.semester = payload.semester
    course.session = payload.session
    course.lecturers_json = dumps(payload.lecturers)
    course.description = payload.description
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="course_updated",
            entity_type="course",
            entity_id=course.id,
            before_json=dumps(before),
            after_json=dumps(payload.model_dump()),
        )
    )
    db.commit()
    db.refresh(course)
    return {"course": serialize_course(course)}


@router.post("/{course_id}/archive")
def archive_course(
    course_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = ensure_course_not_archived(db, course_id)
    before = serialize_course(course)
    course.status = "archived"
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="course_archived",
            entity_type="course",
            entity_id=course.id,
            before_json=dumps(before),
            after_json=dumps(serialize_course(course)),
        )
    )
    db.commit()
    db.refresh(course)
    return {"course": serialize_course(course)}


@router.post("/{course_id}/restore")
def restore_course(
    course_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    before = serialize_course(course)
    if course.status == "archived":
        course.status = archived_previous_status(db, course_id)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="course_restored",
            entity_type="course",
            entity_id=course.id,
            before_json=dumps(before),
            after_json=dumps(serialize_course(course)),
        )
    )
    db.commit()
    db.refresh(course)
    return {"course": serialize_course(course)}


@router.delete("/{course_id}")
def delete_course(
    course_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    before = serialize_course(course)
    approved_deleted = db.query(ApprovedResource).filter(ApprovedResource.course_id == course_id).delete(synchronize_session=False)
    candidates_deleted = db.query(CandidateResource).filter(CandidateResource.course_id == course_id).delete(synchronize_session=False)
    exports_deleted = db.query(ExportRecord).filter(ExportRecord.course_id == course_id).delete(synchronize_session=False)
    jobs_deleted = db.query(ProcessingJob).filter(ProcessingJob.course_id == course_id).delete(synchronize_session=False)
    compacts_deleted = db.query(CourseCompact).filter(CourseCompact.course_id == course_id).delete(synchronize_session=False)
    topics_deleted = db.query(Topic).filter(Topic.course_id == course_id).delete(synchronize_session=False)
    db.delete(course)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="course_deleted",
            entity_type="course",
            entity_id=course_id,
            before_json=dumps(before),
            after_json=dumps(
                {
                    "topics_deleted": topics_deleted,
                    "candidate_resources_deleted": candidates_deleted,
                    "approved_resources_deleted": approved_deleted,
                    "exports_deleted": exports_deleted,
                    "jobs_deleted": jobs_deleted,
                    "compacts_deleted": compacts_deleted,
                }
            ),
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/{course_id}/topics")
def add_topic(
    course_id: int,
    payload: TopicCreate,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = ensure_course_not_archived(db, course_id)
    topic = Topic(
        course_id=course_id,
        module_number=payload.module_number,
        module_title=payload.module_title,
        week_number=payload.week_number,
        topic_title=payload.topic_title,
        subtopics_json=dumps(payload.subtopics),
        outcomes_json=dumps(payload.outcomes),
        is_searchable=payload.is_searchable,
        extraction_confidence=1.0,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    db.add(ApprovalLog(actor_id=current_user.id, action="topic_added", entity_type="topic", entity_id=topic.id))
    db.commit()
    return {"topic": serialize_topic(topic)}


@router.patch("/{course_id}/topics/{topic_id}")
def update_topic(
    course_id: int,
    topic_id: int,
    payload: TopicUpdate,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.course_id != course_id:
        raise HTTPException(status_code=404, detail="Topic not found")
    ensure_course_not_archived(db, course_id)
    before = serialize_topic(topic)
    topic.module_number = payload.module_number
    topic.module_title = payload.module_title
    topic.week_number = payload.week_number
    topic.topic_title = payload.topic_title
    topic.subtopics_json = dumps(payload.subtopics)
    topic.outcomes_json = dumps(payload.outcomes)
    topic.is_searchable = payload.is_searchable
    candidates_deleted = 0
    approved_deleted = 0
    if before["is_searchable"] and not payload.is_searchable:
        approved_deleted = (
            db.query(ApprovedResource)
            .filter(ApprovedResource.course_id == course_id, ApprovedResource.topic_id == topic_id)
            .delete(synchronize_session=False)
        )
        candidates_deleted = (
            db.query(CandidateResource)
            .filter(CandidateResource.course_id == course_id, CandidateResource.topic_id == topic_id)
            .delete(synchronize_session=False)
        )
    db.commit()
    db.refresh(topic)
    after = serialize_topic(topic)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="topic_updated",
            entity_type="topic",
            entity_id=topic.id,
            before_json=dumps(before),
            after_json=dumps(
                {
                    **after,
                    "candidate_resources_deleted": candidates_deleted,
                    "approved_resources_deleted": approved_deleted,
                }
            ),
        )
    )
    db.commit()
    return {"topic": after, "candidate_resources_deleted": candidates_deleted, "approved_resources_deleted": approved_deleted}


@router.delete("/{course_id}/topics/{topic_id}")
def delete_topic(
    course_id: int,
    topic_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.course_id != course_id:
        raise HTTPException(status_code=404, detail="Topic not found")
    ensure_course_not_archived(db, course_id)
    before = serialize_topic(topic)
    approved_deleted = (
        db.query(ApprovedResource)
        .filter(ApprovedResource.course_id == course_id, ApprovedResource.topic_id == topic_id)
        .delete(synchronize_session=False)
    )
    candidates_deleted = (
        db.query(CandidateResource)
        .filter(CandidateResource.course_id == course_id, CandidateResource.topic_id == topic_id)
        .delete(synchronize_session=False)
    )
    db.delete(topic)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="topic_deleted",
            entity_type="topic",
            entity_id=topic_id,
            before_json=dumps(before),
            after_json=dumps(
                {
                    "candidate_resources_deleted": candidates_deleted,
                    "approved_resources_deleted": approved_deleted,
                }
            ),
        )
    )
    db.commit()
    return {"ok": True, "candidate_resources_deleted": candidates_deleted, "approved_resources_deleted": approved_deleted}


@router.post("/{course_id}/topics/confirm")
def confirm_topics(
    course_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = ensure_course_not_archived(db, course_id)
    course.status = "topics_reviewed"
    db.add(ApprovalLog(actor_id=current_user.id, action="topics_reviewed", entity_type="course", entity_id=course_id))
    db.commit()
    return {"course": serialize_course(course)}


@router.post("/{course_id}/generate-resources")
def generate_resources(
    course_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = ensure_course_not_archived(db, course_id)
    if course.status not in {"topics_reviewed", "resources_generated", "exported"}:
        raise HTTPException(status_code=409, detail="Confirm extracted topics before generating resources")
    searchable_topic_count = (
        db.query(Topic)
        .filter(Topic.course_id == course_id, Topic.is_searchable.is_(True))
        .count()
    )
    if searchable_topic_count == 0:
        raise HTTPException(status_code=409, detail="At least one searchable teaching topic is required before generating resources")
    job = ProcessingJob(course_id=course_id, job_type="resource_generation", status="queued", progress=0)
    course.status = "under_review"
    db.add(job)
    db.add(ApprovalLog(actor_id=current_user.id, action="resource_generation_started", entity_type="course", entity_id=course_id))
    db.commit()
    db.refresh(job)
    background_tasks.add_task(generate_resources_job, job.id, course_id, current_user.id)
    return {"job_id": job.id, "course": serialize_course(course)}


@router.patch("/{course_id}/candidates/{candidate_id}")
def update_candidate(
    course_id: int,
    candidate_id: int,
    payload: CandidateUpdate,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    candidate = db.get(CandidateResource, candidate_id)
    if candidate is None or candidate.course_id != course_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    ensure_course_not_archived(db, course_id)
    before = serialize_candidate(candidate)
    candidate.category = payload.category
    candidate.title = payload.title
    candidate.authors_json = dumps(payload.authors)
    candidate.year = payload.year
    candidate.abstract = payload.abstract
    candidate.url = payload.url
    candidate.match_reason = payload.match_reason
    candidate.status = "edited"
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="candidate_updated",
            entity_type="candidate_resource",
            entity_id=candidate.id,
            before_json=dumps(before),
        )
    )
    db.commit()
    db.refresh(candidate)
    return {"candidate": serialize_candidate(candidate)}


@router.post("/{course_id}/candidates/{candidate_id}/review")
def review_candidate(
    course_id: int,
    candidate_id: int,
    payload: CandidateReview,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    candidate = db.get(CandidateResource, candidate_id)
    if candidate is None or candidate.course_id != course_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    ensure_course_not_archived(db, course_id)
    candidate.status = "approved" if payload.action == "approve" else "rejected"
    approved = None
    removed_approved = None
    if payload.action == "approve":
        approved = db.query(ApprovedResource).filter(ApprovedResource.candidate_id == candidate.id).first()
        if approved is None:
            approved = ApprovedResource(
                course_id=course_id,
                topic_id=candidate.topic_id,
                candidate_id=candidate.id,
                category=payload.category or candidate.category,
                title=payload.title or candidate.title,
                authors_json=dumps(payload.authors if payload.authors is not None else loads(candidate.authors_json, [])),
                year=payload.year if payload.year is not None else candidate.year,
                url=payload.url if payload.url is not None else candidate.url,
                source_system=candidate.source_system,
                note=payload.note,
                approved_by_id=current_user.id,
            )
            db.add(approved)
        else:
            approved.category = payload.category or approved.category
            approved.title = payload.title or approved.title
            approved.authors_json = dumps(payload.authors if payload.authors is not None else loads(approved.authors_json, []))
            approved.year = payload.year if payload.year is not None else approved.year
            approved.url = payload.url if payload.url is not None else approved.url
            approved.note = payload.note
    else:
        approved_to_remove = db.query(ApprovedResource).filter(ApprovedResource.candidate_id == candidate.id).first()
        if approved_to_remove is not None:
            removed_approved = serialize_approved(approved_to_remove)
            db.delete(approved_to_remove)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action=f"candidate_{payload.action}d",
            entity_type="candidate_resource",
            entity_id=candidate.id,
            after_json=dumps({**payload.model_dump(), "removed_approved_resource": removed_approved}),
        )
    )
    db.commit()
    return {"candidate": serialize_candidate(candidate), "approved_resource": serialize_approved(approved) if approved else None}


@router.patch("/{course_id}/approved-resources/{resource_id}")
def update_approved_resource(
    course_id: int,
    resource_id: int,
    payload: ApprovedResourceUpdate,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    resource = db.get(ApprovedResource, resource_id)
    if resource is None or resource.course_id != course_id:
        raise HTTPException(status_code=404, detail="Approved resource not found")
    ensure_course_not_archived(db, course_id)
    before = serialize_approved(resource)
    resource.category = payload.category
    resource.title = payload.title
    resource.authors_json = dumps(payload.authors)
    resource.year = payload.year
    resource.url = payload.url
    resource.note = payload.note
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="approved_resource_updated",
            entity_type="approved_resource",
            entity_id=resource.id,
            before_json=dumps(before),
            after_json=dumps(serialize_approved(resource)),
        )
    )
    db.commit()
    db.refresh(resource)
    return {"approved_resource": serialize_approved(resource)}


@router.delete("/{course_id}/approved-resources/{resource_id}")
def delete_approved_resource(
    course_id: int,
    resource_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    resource = db.get(ApprovedResource, resource_id)
    if resource is None or resource.course_id != course_id:
        raise HTTPException(status_code=404, detail="Approved resource not found")
    ensure_course_not_archived(db, course_id)
    before = serialize_approved(resource)
    db.delete(resource)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="approved_resource_deleted",
            entity_type="approved_resource",
            entity_id=resource_id,
            before_json=dumps(before),
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/{course_id}/manual-resources")
def add_manual_resource(
    course_id: int,
    payload: ManualResourceCreate,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    topic = db.get(Topic, payload.topic_id)
    if topic is None or topic.course_id != course_id:
        raise HTTPException(status_code=404, detail="Topic not found")
    ensure_course_not_archived(db, course_id)
    if not topic.is_searchable:
        raise HTTPException(status_code=409, detail="Approved resources can only be added to searchable teaching topics")
    resource = ApprovedResource(
        course_id=course_id,
        topic_id=payload.topic_id,
        category=payload.category,
        title=payload.title,
        authors_json=dumps(payload.authors),
        year=payload.year,
        url=payload.url,
        source_system="manual",
        note=payload.note,
        approved_by_id=current_user.id,
    )
    db.add(resource)
    db.add(ApprovalLog(actor_id=current_user.id, action="manual_resource_added", entity_type="approved_resource", entity_id=0))
    db.commit()
    db.refresh(resource)
    return {"approved_resource": serialize_approved(resource)}


def build_export_payload(db: Session, course: Course) -> dict:
    topics = db.query(Topic).filter(Topic.course_id == course.id).order_by(Topic.week_number.asc().nullslast()).all()
    approved = db.query(ApprovedResource).filter(ApprovedResource.course_id == course.id).all()
    category_order = {category: index for index, category in enumerate(RCAABUT_CATEGORIES)}
    by_topic: dict[int, list[ApprovedResource]] = {}
    for resource in approved:
        by_topic.setdefault(resource.topic_id, []).append(resource)

    resources_by_topics = []
    for topic in topics:
        topic_resources = sorted(
            by_topic.get(topic.id, []),
            key=lambda resource: (
                category_order.get(resource.category, len(category_order)),
                resource.title.lower(),
                resource.id,
            ),
        )
        categories = {category: [] for category in RCAABUT_CATEGORIES}
        flat_resources = []
        category_counts: dict[str, int] = {}
        for resource in topic_resources:
            category = resource.category if resource.category in categories else resource.category or "Uncategorised"
            categories.setdefault(category, [])
            category_counts[category] = category_counts.get(category, 0) + 1
            serialized = serialize_approved(resource)
            serialized["resource_number"] = category_counts[category]
            serialized["category_resource_label"] = f"{category_counts[category]}. {serialized['title']}"
            categories[category].append(serialized)
            flat_resources.append(serialized)
        resources_by_topics.append(
            {
                "topic": serialize_topic(topic),
                "module_number": topic.module_number,
                "module_title": topic.module_title,
                "week_number": topic.week_number,
                "topic_title": topic.topic_title,
                "categories": categories,
                "resources": flat_resources,
            }
        )

    return {
        "course": serialize_course(course),
        "generated_at": datetime.utcnow(),
        "resource_categories": RCAABUT_CATEGORIES,
        "resources_by_topics": resources_by_topics,
    }


def build_html_export(payload: dict) -> str:
    course = payload["course"]
    title = f"{course['course_code']} - {course['course_title']}".strip(" -")
    sections = []
    for topic_group in payload["resources_by_topics"]:
        topic_label = f"Week {topic_group['week_number'] or '-'}: {topic_group['topic_title']}"
        if topic_group.get("module_title"):
            topic_label = f"{topic_label} ({topic_group['module_title']})"
        category_blocks = []
        for category, resources in topic_group["categories"].items():
            if not resources:
                continue
            resource_items = []
            for resource in resources:
                authors = "; ".join(resource["authors"]) or "Unknown author"
                year = f" ({resource['year']})" if resource.get("year") else ""
                url = resource.get("url") or ""
                link = f'<a href="{escape(url)}">{escape(url)}</a>' if url else ""
                resource_items.append(
                    "<li>"
                    f"<strong>{resource['resource_number']}. {escape(resource['title'])}</strong>{escape(year)}"
                    f"<br><span>{escape(authors)}</span>"
                    f"{'<br>' + link if link else ''}"
                    "</li>"
                )
            category_blocks.append(f"<h3>{escape(category)}</h3><ol>{''.join(resource_items)}</ol>")
        if not category_blocks:
            category_blocks.append("<p class=\"empty\">No approved resources for this topic yet.</p>")
        sections.append(f"<section><h2>{escape(topic_label)}</h2>{''.join(category_blocks)}</section>")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} RCAABUT Resources</title>
  <style>
    body {{ margin: 0; padding: 40px; color: #10231f; background: #f7f4ec; font-family: Georgia, 'Times New Roman', serif; }}
    main {{ max-width: 960px; margin: 0 auto; background: #fff; border: 1px solid #d8e3d2; padding: 36px; }}
    header {{ border-bottom: 3px solid #0c6b4f; margin-bottom: 28px; padding-bottom: 18px; }}
    .eyebrow {{ color: #0c6b4f; font-size: 12px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 10px; font-size: 34px; line-height: 1.1; }}
    h2 {{ margin: 28px 0 12px; color: #0c6b4f; font-size: 22px; }}
    h3 {{ margin: 18px 0 8px; color: #8a6a1f; font-size: 16px; text-transform: uppercase; letter-spacing: 0.08em; }}
    section {{ border-top: 1px solid #e7eadf; padding-top: 8px; }}
    ol {{ margin: 0 0 12px 24px; padding: 0; }}
    li {{ margin: 0 0 12px; line-height: 1.45; }}
    a {{ color: #0c6b4f; word-break: break-word; }}
    .meta, .empty {{ color: #53635d; }}
    @media print {{ body {{ background: #fff; padding: 0; }} main {{ border: none; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">Covenant University Library RCAABUT Resources By Topics</div>
      <h1>{escape(title)}</h1>
      <p class="meta">{escape(course.get('department') or 'Department pending')} · {escape(course.get('session') or 'Session pending')} · Generated {escape(str(payload['generated_at']))}</p>
    </header>
    {''.join(sections)}
  </main>
</body>
</html>"""


def add_export_record(db: Session, course_id: int, export_type: str, payload_json: str, current_user: User) -> ExportRecord:
    export = ExportRecord(course_id=course_id, export_type=export_type, payload_json=payload_json, created_by_id=current_user.id)
    db.add(export)
    db.flush()
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="export_generated",
            entity_type="export_record",
            entity_id=export.id,
            after_json=dumps({"course_id": course_id, "export_type": export_type}),
        )
    )
    return export


def require_approved_resources(db: Session, course_id: int) -> None:
    approved_count = db.query(ApprovedResource).filter(ApprovedResource.course_id == course_id).count()
    if approved_count == 0:
        raise HTTPException(status_code=409, detail="Approve at least one resource before exporting")


@router.post("/{course_id}/exports/json")
def create_json_export(
    course_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> dict:
    course = ensure_course_not_archived(db, course_id)
    require_approved_resources(db, course_id)
    payload = build_export_payload(db, course)
    course.status = "exported"
    export = add_export_record(db, course_id, "json", dumps(payload), current_user)
    db.commit()
    db.refresh(export)
    return {"export_id": export.id, "payload": payload}


@router.get("/{course_id}/exports/csv")
def download_csv_export(
    course_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> Response:
    course = ensure_course_not_archived(db, course_id)
    require_approved_resources(db, course_id)
    payload = build_export_payload(db, course)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "course_code",
            "course_title",
            "module_number",
            "module_title",
            "week",
            "topic",
            "category",
            "resource_number",
            "title",
            "authors",
            "year",
            "url",
            "source",
        ]
    )
    for topic_group in payload["resources_by_topics"]:
        for category, resources in topic_group["categories"].items():
            for resource in resources:
                writer.writerow(
                    [
                        course.course_code or "",
                        course.course_title or "",
                        topic_group["module_number"] or "",
                        topic_group["module_title"] or "",
                        topic_group["week_number"] or "",
                        topic_group["topic_title"] or "",
                        category,
                        resource["resource_number"],
                        resource["title"],
                        "; ".join(resource["authors"]),
                        resource["year"] or "",
                        resource["url"] or "",
                        resource["source_system"] or "",
                    ]
                )
    csv_payload = buffer.getvalue()
    add_export_record(db, course_id, "csv", csv_payload, current_user)
    course.status = "exported"
    db.commit()
    filename = f"{course.course_code or 'course'}_rcaabut_resources.csv"
    return Response(
        csv_payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{course_id}/exports/html")
def download_html_export(
    course_id: int,
    current_user: User = Depends(require_library_access),
    db: Session = Depends(get_db),
) -> Response:
    course = ensure_course_not_archived(db, course_id)
    require_approved_resources(db, course_id)
    payload = build_export_payload(db, course)
    html_payload = build_html_export(payload)
    add_export_record(db, course_id, "html", html_payload, current_user)
    course.status = "exported"
    db.commit()
    filename = f"{course.course_code or 'course'}_rcaabut_resources.html"
    return Response(
        html_payload,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
