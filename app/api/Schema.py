from typing import Any

from fastapi import FastAPI


def requires_auth_extra() -> dict[str, Any]:
    return {"security": [{"APIKeyHeader": []}, {"SessionCookie": []}]}


def update_openapi_schema(app: FastAPI):
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

    app.openapi_schema = openapi_schema
