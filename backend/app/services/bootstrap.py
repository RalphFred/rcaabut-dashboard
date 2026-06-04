from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import SourceDatabase, User


DEFAULT_SOURCES = [
    {
        "source_key": "openalex",
        "display_name": "OpenAlex",
        "source_type": "open_metadata",
        "base_url": "https://api.openalex.org",
        "notes": "Broad open scholarly metadata source for articles, books, and works.",
    },
    {
        "source_key": "crossref",
        "display_name": "Crossref",
        "source_type": "doi_metadata",
        "base_url": "https://api.crossref.org",
        "notes": "DOI-focused academic metadata source.",
    },
    {
        "source_key": "open_library",
        "display_name": "Open Library",
        "source_type": "book_metadata",
        "base_url": "https://openlibrary.org",
        "notes": "Open book and textbook metadata source.",
    },
    {
        "source_key": "tool_suggestion",
        "display_name": "Software & Tools Suggestions",
        "source_type": "ai_assisted",
        "base_url": None,
        "notes": "Prototype tool suggestion source for RCAABUT Software & Tools category.",
    },
]


def seed_super_admin(db: Session) -> None:
    existing = db.query(User).filter(User.email == settings.seed_super_admin_email.lower()).first()
    if existing:
        return
    user = User(
        full_name=settings.seed_super_admin_name,
        email=settings.seed_super_admin_email.lower(),
        password_hash=hash_password(settings.seed_super_admin_password),
        role="super_admin",
        is_active=True,
    )
    db.add(user)
    db.commit()


def seed_default_sources(db: Session) -> None:
    for item in DEFAULT_SOURCES:
        existing = db.query(SourceDatabase).filter(SourceDatabase.source_key == item["source_key"]).first()
        if existing:
            continue
        db.add(SourceDatabase(**item, is_enabled=True))
    db.commit()
