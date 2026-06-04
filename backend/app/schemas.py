from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.utils import RCAABUT_CATEGORIES


def validate_rcaabut_category(value: str | None) -> str | None:
    if value is None:
        return value
    if value not in RCAABUT_CATEGORIES:
        allowed = ", ".join(RCAABUT_CATEGORIES)
        raise ValueError(f"Category must be one of: {allowed}")
    return value


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2)
    email: str
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(super_admin|library_staff)$")
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: str | None = Field(default=None, pattern="^(super_admin|library_staff)$")
    is_active: bool | None = None


class TopicUpdate(BaseModel):
    module_number: int | None = None
    module_title: str | None = None
    week_number: int | None = None
    topic_title: str
    subtopics: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    is_searchable: bool = True


class CourseUpdate(BaseModel):
    course_code: str
    course_title: str
    college: str | None = None
    department: str | None = None
    programme: str | None = None
    level: str | None = None
    semester: str | None = None
    session: str | None = None
    lecturers: list[str] = Field(default_factory=list)
    description: str | None = None


class TopicCreate(TopicUpdate):
    pass


class CandidateUpdate(BaseModel):
    category: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    url: str | None = None
    match_reason: str | None = None

    _validate_category = field_validator("category")(validate_rcaabut_category)


class CandidateReview(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    category: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    url: str | None = None
    note: str | None = None

    _validate_category = field_validator("category")(validate_rcaabut_category)


class ManualResourceCreate(BaseModel):
    topic_id: int
    category: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    url: str | None = None
    note: str | None = None

    _validate_category = field_validator("category")(validate_rcaabut_category)


class ApprovedResourceUpdate(BaseModel):
    category: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    url: str | None = None
    note: str | None = None

    _validate_category = field_validator("category")(validate_rcaabut_category)
