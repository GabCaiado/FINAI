import pytest
from pydantic import ValidationError

from app.config import MIN_SECRET_LENGTH, Settings, load_settings

OPTIONAL = {"jwt_secret", "llm_api_key", "llm_model"}

# A complete, valid set of values for the tests below (the application itself has none).
VALUES: dict[str, object] = {
    "environment": "development",
    "log_level": "INFO",
    "database_url": "sqlite:///./x.db",
    "jwt_expire_hours": 24,
    "cookie_secure": False,
    "cors_origin": "http://localhost:5173",
    "password_min_length": 8,
    "login_rate_limit": "5/minute",
    "llm_provider": "mock",
    "llm_timeout_s": 15,
    "llm_concurrency": 4,
    "daily_llm_rows_limit": 200,
    "global_daily_llm_rows_limit": 3000,
    "max_upload_bytes": 2097152,
    "max_import_rows": 5000,
    "import_stale_minutes": 10,
}
PROD = {
    **VALUES,
    "environment": "production",
    "jwt_secret": "s" * MIN_SECRET_LENGTH,
    "cookie_secure": True,
    "database_url": "postgresql+psycopg://u:p@db.example.com/finai",
    "cors_origin": "https://finai.example.com",
}


def build(base: dict[str, object] = PROD, **overrides: object) -> Settings:
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def test_no_environment_specific_value_has_a_default_in_code():
    """Guards the rule: configuration comes from the environment, not from code."""
    with_default = {n for n, f in Settings.model_fields.items() if not f.is_required()}
    assert with_default == OPTIONAL


def test_missing_variables_are_named_without_values(monkeypatch: pytest.MonkeyPatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    with pytest.raises(RuntimeError) as exc:
        load_settings(env_file=None)
    message = str(exc.value)
    assert "DATABASE_URL" in message and "CORS_ORIGIN" in message
    assert ".env.example" in message


def test_invalid_value_is_reported_by_name_not_by_value(monkeypatch: pytest.MonkeyPatch):
    for name, value in VALUES.items():
        monkeypatch.setenv(name.upper(), str(value))
    monkeypatch.setenv("JWT_EXPIRE_HOURS", "not-a-number-secret-ish")
    with pytest.raises(RuntimeError) as exc:
        load_settings(env_file=None)
    assert "JWT_EXPIRE_HOURS" in str(exc.value)
    assert "not-a-number-secret-ish" not in str(exc.value)


def test_dev_without_secret_gets_a_random_one():
    a, b = build(VALUES), build(VALUES)
    assert len(a.jwt_secret) >= MIN_SECRET_LENGTH
    assert a.jwt_secret != b.jwt_secret


def test_valid_production_config_loads():
    assert build().is_production


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"jwt_secret": ""}, "JWT_SECRET"),
        ({"jwt_secret": "short"}, "JWT_SECRET"),
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"database_url": "sqlite:///./x.db"}, "Postgres"),
        ({"cors_origin": "http://finai.example.com"}, "https"),
        ({"llm_provider": "openai", "llm_api_key": "", "llm_model": ""}, "LLM_API_KEY"),
    ],
)
def test_production_refuses_unsafe_config(override: dict[str, object], fragment: str):
    with pytest.raises(ValidationError, match=fragment):
        build(**override)


def test_openai_in_production_needs_key_and_model():
    assert build(llm_provider="openai", llm_api_key="k", llm_model="m").llm_provider == "openai"
