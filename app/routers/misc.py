import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, PlainTextResponse, Response

from app.api.responses import LicenseEntry, VersionResponse
from app.version import VERSION

router = APIRouter()

_licenses_path = Path(__file__).parent.parent / "licenses.json"
_third_party_licenses: list[dict[str, str]] = json.loads(_licenses_path.read_text()) if _licenses_path.exists() else []


@router.get("/api/version")
async def version() -> VersionResponse:
    """Return the application version."""
    return VersionResponse(version=VERSION)


@router.get("/api/licenses")
async def licenses() -> list[LicenseEntry]:
    """Return third-party dependency licenses."""
    return [LicenseEntry(**e) for e in _third_party_licenses]


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Serve the favicon."""
    return FileResponse("app/static/images/favicon.ico")


@router.get("/manifest.json", include_in_schema=False)
async def manifest() -> FileResponse:
    """Serve the PWA manifest."""
    return FileResponse("app/static/manifest.json", media_type="application/manifest+json")


@router.get("/sw.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    """Serve the service worker script."""
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots() -> str:
    """Return the robots.txt content."""
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
    """Return the XML sitemap."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://status.fribbe-beach.de/</loc>
        <changefreq>always</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")
