"""Architecture guardrails that import-linter cannot express (work package A1).

Import-direction rules live in `[tool.importlinter]` in pyproject.toml and run as `lint-imports`.
"""

import ast
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.main import create_app

APP_DIR = Path(__file__).resolve().parents[1] / "app"
PROVIDER_FILE = APP_DIR / "ai" / "provider.py"
LOGGING_CONFIG_FILE = APP_DIR / "logging_config.py"
CONFIG_FILE = APP_DIR / "config.py"
AUTH_DEPENDENCY_NAME = "get_current_user"

# The ONLY place that lists routes allowed to be reachable without an authenticated user.
# Adding a route here is a security decision: justify it in the PR.
PUBLIC_ROUTE_ALLOWLIST: dict[str, str] = {
    "/api/health": "liveness probe for the host; returns no data",
    "/api/health/ready": "post-deploy smoke test; returns only ok/unavailable",
    "/api/categories": "static category list; contains no user data",
    "/api/auth/register": "creates the session, so it cannot require one",
    "/api/auth/login": "creates the session, so it cannot require one",
    "/docs": "Swagger UI, disabled in production",
    "/docs/oauth2-redirect": "Swagger UI helper, disabled in production",
    "/openapi.json": "API schema, disabled in production",
}


def python_files() -> Iterator[Path]:
    yield from (p for p in sorted(APP_DIR.rglob("*.py")) if "__pycache__" not in p.parts)


def parse(source: str) -> ast.Module:
    return ast.parse(source)


def imports_module(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            a.name == name or a.name.startswith(f"{name}.") for a in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and (node.module == name or node.module.startswith(f"{name}."))
        ):
            return True
    return False


def calls_builtin(tree: ast.Module, name: str) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
        for n in ast.walk(tree)
    )


def calls_attribute(tree: ast.Module, owner: str, attr: str) -> bool:
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == attr
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == owner
        for n in ast.walk(tree)
    )


def reads_environment(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in {"environ", "getenv", "putenv"}
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "os"
            and any(a.name in {"environ", "getenv"} for a in node.names)
        ):
            return True
    return False


def offenders(check, exempt: set[Path]) -> list[str]:  # type: ignore[no-untyped-def]
    found = []
    for path in python_files():
        if path not in exempt and check(parse(path.read_text(encoding="utf-8"))):
            found.append(str(path.relative_to(APP_DIR)))
    return found


def has_dependency(dependant: Dependant, name: str) -> bool:
    for sub in dependant.dependencies:
        if getattr(sub.call, "__name__", None) == name or has_dependency(sub, name):
            return True
    return False


def flatten_routes(routes: Sequence[Any]) -> Iterator[Any]:
    """Yield leaf routes. Recent FastAPI wraps `include_router` results in a group object that
    exposes the real routes through `effective_route_contexts()`."""
    for route in routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is None:
            yield route
        else:
            yield from contexts()


def unprotected_routes() -> list[str]:
    missing = []
    for route in flatten_routes(create_app().routes):
        path = route.path
        if path in PUBLIC_ROUTE_ALLOWLIST:
            continue
        dependant = getattr(route, "dependant", None)
        if dependant is None or not has_dependency(dependant, AUTH_DEPENDENCY_NAME):
            missing.append(path)
    return missing


# --- the project code ---------------------------------------------------------------------------


def test_only_the_provider_module_imports_openai() -> None:
    assert offenders(lambda t: imports_module(t, "openai"), {PROVIDER_FILE}) == []


def test_every_route_outside_the_allowlist_requires_an_authenticated_user() -> None:
    assert unprotected_routes() == []


def test_no_print_calls_in_app() -> None:
    assert offenders(lambda t: calls_builtin(t, "print"), set()) == []


def test_logging_is_configured_only_in_logging_config() -> None:
    check = lambda t: calls_attribute(t, "logging", "basicConfig")  # noqa: E731
    assert offenders(check, {LOGGING_CONFIG_FILE}) == []


def test_environment_is_read_only_in_config() -> None:
    assert offenders(reads_environment, {CONFIG_FILE}) == []


# --- the checkers themselves: they must detect violations -------------------------------------


def test_checker_detects_openai_imports() -> None:
    assert imports_module(parse("import openai"), "openai")
    assert imports_module(parse("from openai import OpenAI"), "openai")
    assert imports_module(parse("from openai.types import X"), "openai")
    assert not imports_module(parse("import openai_helpers"), "openai")


def test_checker_detects_print_basicconfig_and_environ() -> None:
    assert calls_builtin(parse("print('x')"), "print")
    assert calls_attribute(parse("import logging\nlogging.basicConfig()"), "logging", "basicConfig")
    assert reads_environment(parse("import os\nos.getenv('X')"))
    assert reads_environment(parse("import os\nx = os.environ['X']"))
    assert reads_environment(parse("from os import environ"))
    assert not reads_environment(parse("import os\nos.path.join('a')"))


def test_route_check_flags_a_route_without_the_auth_dependency() -> None:
    from typing import Annotated

    from fastapi import Depends, FastAPI

    def get_current_user() -> str:
        return "u"

    app = FastAPI()

    @app.get("/guarded")
    def guarded(user: Annotated[str, Depends(get_current_user)]) -> str:
        return user

    @app.get("/open")
    def open_route() -> str:
        return "x"

    by_path = {r.path: r for r in app.routes if isinstance(r, APIRoute)}
    assert has_dependency(by_path["/guarded"].dependant, AUTH_DEPENDENCY_NAME)
    assert not has_dependency(by_path["/open"].dependant, AUTH_DEPENDENCY_NAME)
