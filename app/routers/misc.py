import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, PlainTextResponse, Response

from app.api.responses import LicenseEntry, VersionResponse
from app.config import cfg

router = APIRouter()

_licenses_path = Path(__file__).parent.parent / "licenses.json"
_third_party_licenses: list[dict[str, str]] = json.loads(_licenses_path.read_text()) if _licenses_path.exists() else []


@router.get("/api/version")
async def version() -> VersionResponse:
    """Return the application version."""
    return VersionResponse(version=cfg.BUILD_VERSION)


@router.get("/api/version/content-hash")
async def version_content_hash() -> VersionResponse:
    """Return the content hash version."""
    return VersionResponse(version=cfg.CONTENT_HASH_VERSION)


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
    sitemap_line = f"\nSitemap: {cfg.APP_URL}/sitemap.xml"
    return f"""User-agent: *
Allow: /$
Allow: /sitemap.xml
Disallow: /api/
Disallow: /preview/
Disallow: /notification-create
Disallow: /static/{sitemap_line}"""


@router.get("/sitemap.xml", response_class=Response, include_in_schema=False)
def sitemap() -> Response:
    """Return the XML sitemap."""
    loc = f"{cfg.APP_URL}/"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{loc}</loc>
        <changefreq>always</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")
