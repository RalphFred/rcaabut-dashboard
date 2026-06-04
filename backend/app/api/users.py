from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.deps import require_super_admin
from app.models import ApprovalLog, User
from app.schemas import UserCreate, UserUpdate
from app.utils import dumps

router = APIRouter(prefix="/users", tags=["users"])


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


def active_super_admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "super_admin", User.is_active.is_(True)).count()


@router.get("")
def list_users(_: User = Depends(require_super_admin), db: Session = Depends(get_db)) -> dict:
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {"users": [serialize_user(user) for user in users]}


@router.post("")
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="user_created",
            entity_type="user",
            entity_id=user.id,
            after_json=dumps(serialize_user(user)),
        )
    )
    db.commit()
    return {"user": serialize_user(user)}


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    before = serialize_user(user)
    data = payload.model_dump(exclude_unset=True)

    if user.id == current_user.id:
        if data.get("is_active") is False:
            raise HTTPException(status_code=400, detail="You cannot disable your own Super Admin account")
        if data.get("role") and data["role"] != "super_admin":
            raise HTTPException(status_code=400, detail="You cannot change your own Super Admin role")

    removes_active_super_admin = (
        user.role == "super_admin"
        and user.is_active
        and (
            data.get("is_active") is False
            or (data.get("role") is not None and data["role"] != "super_admin")
        )
    )
    if removes_active_super_admin and active_super_admin_count(db) <= 1:
        raise HTTPException(status_code=409, detail="At least one active Super Admin account is required")

    for field in ["full_name", "role", "is_active"]:
        if field in data:
            setattr(user, field, data[field])
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
    db.commit()
    db.refresh(user)
    after = serialize_user(user)
    if data.get("password"):
        after["password_reset"] = True
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="user_updated",
            entity_type="user",
            entity_id=user.id,
            before_json=dumps(before),
            after_json=dumps(after),
        )
    )
    db.commit()
    return {"user": serialize_user(user)}
