import json
from pathlib import Path
from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "Talk Tamila Stories & Auth API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "mysql+pymysql://root:1234@localhost:3306/talktamila"
    # Path to the database provider's CA certificate (e.g. Aiven's ca.pem). When set,
    # the server certificate and hostname are verified.
    DATABASE_SSL_CA: str = ""

    SECRET_KEY: str = "dev_secret_key_change_in_production_jwt_9348572849"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Talk Tamila"

    # Required in production to create the first admin account. Never hard-code it.
    ADMIN_BOOTSTRAP_PASSWORD: str = ""

    # Brevo (transactional email) - used for OTP emails
    BREVO_API_KEY: str = ""

    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = ""

    # Publishes scheduled posts when their time arrives.
    POST_SCHEDULER_ENABLED: bool = True
    # Add a few example posts when the database has no posts yet (development only).
    SEED_DEMO_POSTS: bool = True
    POST_SCHEDULER_INTERVAL_SECONDS: int = 30

    # Login / OTP throttling.
    RATE_LIMIT_ENABLED: bool = True

    # Show /docs, /redoc and the OpenAPI file. Defaults to on outside production.
    ENABLE_DOCS: Optional[bool] = None

    BACKEND_CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.0.72:3000",
        "http://192.168.0.45:3000",
        "http://localhost:5173",
        "https://talktamila-adminpanel-s8pg.vercel.app",
    ]

    CORS_ORIGIN_REGEX: str = r"^http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+$"

    @field_validator("BACKEND_CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return [str(origin).strip() for origin in parsed if str(origin).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def reject_default_secret_in_production(cls, v: str, info) -> str:
        insecure_default = "dev_secret_key_change_in_production_jwt_9348572849"
        env = (info.data.get("ENVIRONMENT") or "development").lower()
        if env == "production" and (v == insecure_default or len(v) < 32):
            raise ValueError(
                "SECRET_KEY must be set to a strong, unique value via the SECRET_KEY "
                "environment variable when ENVIRONMENT=production."
            )
        return v


    @model_validator(mode="after")
    def reject_dev_database_in_production(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production" and "root:1234@" in self.DATABASE_URL:
            raise ValueError("Set DATABASE_URL to your real database when ENVIRONMENT=production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def docs_enabled(self) -> bool:
        return (not self.is_production) if self.ENABLE_DOCS is None else self.ENABLE_DOCS


settings = Settings()