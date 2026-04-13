from typing import Any

from fastapi import FastAPI


def requires_auth_extra() -> dict[str, Any]:
    """Return OpenAPI security metadata for authenticated endpoints."""
    return {"security": [{"APIKeyHeader": []}, {"SessionCookie": [], "CSRFTokenHeader": []}]}


def update_openapi_schema(app: FastAPI) -> None:
    """Register custom security schemes in the OpenAPI schema."""
    openapi_schema = app.openapi_schema or app.openapi()

    # 2. Ensure 'components' exists
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}

    # 3. Ensure 'securitySchemes' exists
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}

    # 4. Only add if not already present
    if "APIKeyHeader" not in openapi_schema["components"]["securitySchemes"]:
        openapi_schema["components"]["securitySchemes"]["APIKeyHeader"] = {
            "type": "apiKey",
            "name": "api_key",
            "in": "header",
        }

    if "SessionCookie" not in openapi_schema["components"]["securitySchemes"]:
        openapi_schema["components"]["securitySchemes"]["SessionCookie"] = {
            "type": "apiKey",
            "name": "session",
            "in": "cookie",
        }

    if "CSRFTokenHeader" not in openapi_schema["components"]["securitySchemes"]:
        openapi_schema["components"]["securitySchemes"]["CSRFTokenHeader"] = {
            "type": "apiKey",
            "name": "x-csrf-token",
            "in": "header",
            "description": "Required when authenticating via session cookie. Read the value from the 'csrftoken' browser cookie.",
        }

    app.openapi_schema = openapi_schema
