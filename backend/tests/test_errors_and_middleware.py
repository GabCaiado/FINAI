import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import settings
from app.errors import AppError
from app.main import create_app


class Payload(BaseModel):
    password: str
    amount: int


@pytest.fixture
def app() -> FastAPI:
    application = create_app()

    @application.post("/api/_test/payload")
    def payload(body: Payload) -> dict[str, bool]:
        return {"ok": True}

    @application.get("/api/_test/app-error")
    def app_error() -> None:
        raise AppError("email_already_registered", "E-mail já cadastrado.", 409, {"field": "email"})

    @application.get("/api/_test/boom")
    def boom() -> None:
        raise RuntimeError("secret amount 12345 leaked")

    return application


@pytest.fixture
def api(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_app_error_has_stable_shape(api: TestClient):
    r = api.get("/api/_test/app-error")
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "email_already_registered"
    assert body["message"] == "E-mail já cadastrado."
    assert body["details"] == {"field": "email"}
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_validation_error_never_echoes_input(api: TestClient):
    r = api.post("/api/_test/payload", json={"password": "hunter2-super-secret", "amount": "abc"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert "hunter2-super-secret" not in r.text
    assert body["details"]["errors"][0]["field"] == "amount"


def test_unknown_route_uses_error_contract(api: TestClient):
    r = api.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_unhandled_exception_hides_details_and_logs_no_message(
    api: TestClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.ERROR, logger="finai.errors"):
        r = api.get("/api/_test/boom")
    assert r.status_code == 500
    assert r.json()["code"] == "internal_error"
    assert "12345" not in r.text
    assert "12345" not in caplog.text
    assert any(rec.error_type == "RuntimeError" for rec in caplog.records)  # type: ignore[attr-defined]


def test_request_id_is_generated_or_echoed_when_valid(api: TestClient):
    generated = api.get("/api/health").headers["X-Request-ID"]
    assert len(generated) == 32
    assert (
        api.get("/api/health", headers={"X-Request-ID": "abc-12345678"}).headers["X-Request-ID"]
        == "abc-12345678"
    )
    # Malformed ids (log injection attempts) are replaced.
    bad = api.get("/api/health", headers={"X-Request-ID": "bad id\nfake: log"})
    assert bad.headers["X-Request-ID"] != "bad id\nfake: log"


def test_security_headers_on_every_response_including_rejections(api: TestClient):
    ok = api.get("/api/health")
    assert ok.headers["X-Content-Type-Options"] == "nosniff"
    assert ok.headers["X-Frame-Options"] == "DENY"
    rejected = api.post("/api/_test/payload", headers={"Origin": "https://evil.example"})
    assert rejected.status_code == 403
    assert rejected.headers["X-Content-Type-Options"] == "nosniff"
    assert rejected.headers["X-Request-ID"]


def test_origin_check_blocks_foreign_origin_on_unsafe_methods(api: TestClient):
    body = {"password": "x", "amount": 1}
    foreign = api.post("/api/_test/payload", json=body, headers={"Origin": "https://evil.example"})
    assert foreign.status_code == 403
    assert foreign.json()["code"] == "forbidden_origin"
    ours = api.post("/api/_test/payload", json=body, headers={"Origin": settings.cors_origin})
    assert ours.status_code == 200
    no_origin = api.post("/api/_test/payload", json=body)  # non-browser client
    assert no_origin.status_code == 200


def test_origin_check_ignores_safe_methods(api: TestClient):
    r = api.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200


def test_access_log_has_no_query_string(api: TestClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger="finai.request"):
        api.get("/api/health?token=secret-token")
    assert "secret-token" not in caplog.text
    assert any(getattr(rec, "path", None) == "/api/health" for rec in caplog.records)
