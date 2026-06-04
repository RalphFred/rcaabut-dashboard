from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5434/rcaabut_dashboard",
        alias="DATABASE_URL",
    )
    jwt_secret_key: str = Field(default="change-this-before-deploy", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 8

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    max_compact_upload_mb: int = Field(default=20, alias="MAX_COMPACT_UPLOAD_MB")

    frontend_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="FRONTEND_ORIGINS",
    )
    seed_super_admin_email: str = Field(default="admin@rcaabut.local", alias="SEED_SUPER_ADMIN_EMAIL")
    seed_super_admin_password: str = Field(default="ChangeMe123!", alias="SEED_SUPER_ADMIN_PASSWORD")
    seed_super_admin_name: str = Field(default="RCAABUT Super Admin", alias="SEED_SUPER_ADMIN_NAME")
    seed_demo_data: bool = Field(default=False, alias="SEED_DEMO_DATA")

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql://", 1)
        return self.database_url

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
