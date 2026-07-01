from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Core Settings
    PROJECT_NAME: str = "Sitemap-Based Domain Inventory Crawler"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key-change-in-production-at-least-32-chars-long"

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000"

    @field_validator("CORS_ORIGINS")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        raise ValueError(v)

    # Database Settings
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "crawler_db"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/crawler_db"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # JWT Authentication
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Crawler Settings
    CRAWLER_MAX_WORKERS: int = 32
    CRAWLER_TIMEOUT_SECONDS: int = 30
    CRAWLER_RESPECT_ROBOTS_TXT: bool = True
    CRAWLER_FOLLOW_REDIRECTS: bool = True

    # Sitemap Discovery & Parsing
    SITEMAP_DISCOVERY_TIMEOUT: int = 10
    SITEMAP_MAX_DEPTH: int = 10
    SITEMAP_MAX_URLS_PER_SITEMAP: int = 50000

    # Storage Settings
    STORAGE_TYPE: str = "local"  # local, s3, r2
    STORAGE_LOCAL_PATH: str = "./storage"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_S3_REGION: str = "us-east-1"

    # Prometheus
    PROMETHEUS_MULTIPROC_DIR: str = ""

settings = Settings()
