from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.deps import get_current_user
from app.models import ApprovalLog, User
from app.schemas import ChangePasswordRequest, LoginRequest, TokenOut
from app.utils import dumps

router = APIRouter(prefix="/auth", tags=["auth"])


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
    }


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    token = create_access_token(str(user.id), user.role)
    return TokenOut(access_token=token, user=user_payload(user))


@router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return user_payload(current_user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    db.add(
        ApprovalLog(
            actor_id=current_user.id,
            action="password_changed",
            entity_type="user",
            entity_id=current_user.id,
            after_json=dumps({"self_service": True}),
        )
    )
    db.commit()
    return {"ok": True}
