from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import api_keys, audit_log, auth, consoles, imports, jobs, public_api, settings, stats, system, users, vehicles

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_app() -> FastAPI:
    app = FastAPI(title="UniFi Fabric License Plate Importer", docs_url="/api/docs", openapi_url="/api/openapi.json")

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

    for module in (auth, users, system, settings, audit_log, consoles, vehicles, imports, jobs, stats, api_keys, public_api):
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
