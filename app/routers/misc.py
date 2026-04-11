import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, PlainTextResponse, Response

from app.api.Responses import LicenseEntry, VersionResponse
from app.version import VERSION

router = APIRouter()

_licenses_path = Path(__file__).parent.parent / "licenses.json"
_third_party_licenses: list[dict[str, str]] = json.loads(_licenses_path.read_text()) if _licenses_path.exists() else []


@router.get("/api/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(version=VERSION)


@router.get("/api/licenses", response_model=list[LicenseEntry])
async def licenses() -> list[LicenseEntry]:
    return [LicenseEntry(**e) for e in _third_party_licenses]


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse("app/static/images/favicon.ico")


@router.get("/sw.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots() -> str:
    return """User-agent: *
Allow: /$
Allow: /sitemap.xml
Disallow: /api/
Disallow: /preview/
Disallow: /notification-create
Disallow: /static/

Sitemap: https://status.fribbe-beach.de/sitemap.xml"""


@router.get("/sitemap.xml", response_class=Response, include_in_schema=False)
def sitemap() -> Response:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://status.fribbe-beach.de/</loc>
        <changefreq>always</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")
