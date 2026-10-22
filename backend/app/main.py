import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import api_keys, audit_log, auth, backup, consoles, dashboard, import_schedules, imports, jobs, public_api, security, settings, stats, system, users, vehicles
from .services import scheduler

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
log = logging.getLogger(__name__)

# The UI only loads its own files. Swagger UI (/api/docs) loads from a CDN and gets no policy.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def check_secret_key() -> None:
    settings = get_settings()
    if settings.secret_key_ok:
        return
    if settings.secret_key == "change-me" and not settings.database_url.startswith("sqlite"):
        raise RuntimeError("LPR_SECRET_KEY is not set. Set a long random value in /etc/lpr-importer/lpr-importer.env.")
    log.warning("LPR_SECRET_KEY is short or the example value; stored passwords and tokens are poorly protected")


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_secret_key()
    scheduler.start()
    yield
    scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="UniFi Fabric License Plate Importer", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Browsers cannot send this header cross-site without a CORS preflight,
        # which this app never allows, so it blocks cross-site form posts.
        # The external REST API (/api/v1) authenticates with a bearer key, never a cookie.
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/v1/") and request.method not in SAFE_METHODS:
            if request.headers.get("x-requested-with") != "XMLHttpRequest":
                return JSONResponse({"detail": "csrf_check_failed"}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        path = request.url.path
        if not path.startswith(("/api/docs", "/api/redoc")):
            response.headers.setdefault("Content-Security-Policy", CSP)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if get_settings().cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    for module in (auth, users, system, settings, audit_log, consoles, vehicles, import_schedules, imports, jobs, dashboard, stats, api_keys, backup, security, public_api):
        app.include_router(module.router)

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    dist = get_settings().frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            file = (dist / path).resolve()
            if path and file.is_file() and dist.resolve() in file.parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
