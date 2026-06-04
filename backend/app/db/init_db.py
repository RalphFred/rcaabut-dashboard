from sqlalchemy.orm import Session

from app import models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.demo_seed import seed_demo_data
from app.db.session import SessionLocal, engine
from app.services.bootstrap import seed_default_sources, seed_super_admin


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        seed_super_admin(db)
        seed_default_sources(db)
        if settings.seed_demo_data:
            seed_demo_data(db)
    finally:
        db.close()


def main() -> None:
    init_database()
    print("Database tables and seed data are ready.")


if __name__ == "__main__":
    main()
