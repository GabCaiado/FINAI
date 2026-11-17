"""Application settings: every value comes from the environment (or a dotenv file).

There are deliberately **no defaults** for environment-specific or tunable values: a missing
variable stops the application with a message naming it. The only optional values are secrets
(``JWT_SECRET``, ``LLM_API_KEY``, ``LLM_MODEL``), which are empty when unset. See
``backend/.env.example`` for the full list and ``.env.test`` for the test profile.
"""

import os
import secrets
from typing import Literal

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32
# Which dotenv file to read. Tests point it at ``.env.test`` so a developer's ``.env`` never
# leaks into them. Real environment variables always take precedence over the file.
ENV_FILE = os.environ.get("ENV_FILE", ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    environment: Literal["development", "test", "production"]
    log_level: str

    database_url: str

    # Optional. Empty outside production -> a random per-process secret is generated, so
    # sessions do not survive a restart: set one in .env for a stable local login.
    jwt_secret: str = ""
    jwt_expire_hours: int
    cookie_secure: bool
    cors_origin: str

    llm_provider: Literal["openai", "mock"]
    llm_api_key: str = ""  # optional: only needed with LLM_PROVIDER=openai
    llm_model: str = ""  # optional: only needed with LLM_PROVIDER=openai
    llm_timeout_s: int
    llm_concurrency: int
    daily_llm_rows_limit: int  # per user per day
    global_daily_llm_rows_limit: int  # all users, hard stop for cost

    max_upload_bytes: int
    max_import_rows: int
    import_stale_minutes: int  # a "processing" batch older than this is finalised as partial

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if not self.is_production:
            if not self.jwt_secret:
                self.jwt_secret = secrets.token_urlsafe(48)
            return self

        problems: list[str] = []
        if len(self.jwt_secret) < MIN_SECRET_LENGTH:
            problems.append(f"JWT_SECRET must have at least {MIN_SECRET_LENGTH} characters")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to Postgres, not SQLite")
        if self.cors_origin.startswith("http://"):
            problems.append("CORS_ORIGIN must be an https:// origin")
        if self.llm_provider == "openai" and not (self.llm_api_key and self.llm_model):
            problems.append("LLM_API_KEY and LLM_MODEL are required when LLM_PROVIDER=openai")
        if problems:
            raise ValueError("Invalid production configuration: " + "; ".join(problems))
        return self


def load_settings(env_file: str | None = ENV_FILE) -> Settings:
    """Load settings, turning a validation failure into one readable message.

    Only variable *names* and our own validation messages are reported, never the values.
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        missing, invalid, problems = set(), set(), []
        for err in exc.errors():
            if not err["loc"]:  # model-level validator: our own message, safe to show
                problems.append(err["msg"].removeprefix("Value error, "))
            elif err["type"] == "missing":
                missing.add(str(err["loc"][0]).upper())
            else:
                invalid.add(str(err["loc"][0]).upper())
        parts = []
        if missing:
            parts.append("missing variables: " + ", ".join(sorted(missing)))
        if invalid:
            parts.append("invalid values: " + ", ".join(sorted(invalid)))
        parts.extend(problems)
        raise RuntimeError(
            "Invalid configuration (" + "; ".join(parts) + "). "
            "Copy backend/.env.example to backend/.env and fill it in."
        ) from None


settings = load_settings()
