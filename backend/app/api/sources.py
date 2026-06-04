from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_library_access, require_super_admin
from app.models import ApprovalLog, SourceDatabase, User
from app.utils import dumps

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceUpdate(BaseModel):
    display_name: str = Field(min_length=2)
    source_type: str = Field(min_length=2)
    base_url: str | None = None
    is_enabled: bool = True
    notes: str | None = None


def serialize_source(source: SourceDatabase) -> dict:
    return {
        "id": source.id,
        "source_key": source.source_key,
        "display_name": source.display_name,
        "source_type": source.source_type,
        "base_url": source.base_url,
        "is_enabled": source.is_enabled,
        "notes": source.notes,
        "created_at": source.created_at,
    }


@router.get("")
def list_sources(_: User = Depends(require_library_access), db: Session = Depends(get_db)) -> dict:
    rows = db.query(SourceDatabase).order_by(SourceDatabase.display_name.asc()).all()
    return {"sources": [serialize_source(row) for row in rows]}


@router.patch("/{source_id}")
def update_source(
    source_id: int,
    payload: SourceUpdate,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    source = db.get(SourceDatabase, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    before = serialize_source(source)
    source.display_name = payload.display_name
    source.source_type = payload.source_type
    source.base_url = payload.base_url
    source.is_enabled = payload.is_enabled
    source.notes = payload.notes
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="source_updated",
            entity_type="source_database",
            entity_id=source.id,
            before_json=dumps(before),
            after_json=dumps(serialize_source(source)),
        )
    )
    db.commit()
    db.refresh(source)
    return {"source": serialize_source(source)}
