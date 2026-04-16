"""Tests for app/api/schema.py — OpenAPI schema customisation."""

from typing import Any

from fastapi import FastAPI

from app.api.schema import update_openapi_schema


def test_update_openapi_schema_registers_security_schemes() -> None:
    app = FastAPI()

    update_openapi_schema(app)

    assert app.openapi_schema is not None
    schemes: dict[str, Any] = app.openapi_schema["components"]["securitySchemes"]
    assert "APIKeyHeader" in schemes
    assert schemes["APIKeyHeader"]["in"] == "header"
    assert "SessionCookie" in schemes
    assert schemes["SessionCookie"]["in"] == "cookie"


def test_update_openapi_schema_is_idempotent() -> None:
    app = FastAPI()

    update_openapi_schema(app)
    update_openapi_schema(app)

    assert app.openapi_schema is not None
    schemes: dict[str, Any] = app.openapi_schema["components"]["securitySchemes"]
    assert list(schemes.keys()).count("APIKeyHeader") == 1
    assert list(schemes.keys()).count("SessionCookie") == 1


def test_update_openapi_schema_works_when_schema_already_has_components() -> None:
    app = FastAPI()
    # Pre-populate openapi_schema with a components section but no securitySchemes
    app.openapi_schema = {"openapi": "3.1.0", "info": {}, "components": {"schemas": {}}}

    update_openapi_schema(app)

    assert "APIKeyHeader" in app.openapi_schema["components"]["securitySchemes"]
