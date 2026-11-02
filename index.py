from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from klod import __version__
from klod.mesh import api as mesh_api


app = FastAPI(title="GPU Mesh Core", version=__version__)
app.include_router(mesh_api.router, prefix="/v1/mesh")
WEB_ROOT = Path(__file__).resolve().parent / "src" / "klod" / "web"


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/mesh", include_in_schema=False)
def mesh_dashboard():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/healthz", include_in_schema=False)
def healthz():
    stores = (
        mesh_api.auth_store,
        mesh_api.registry,
        mesh_api.quota_ledger,
        mesh_api.task_store,
        mesh_api.job_store,
    )
    try:
        for store in stores:
            with store._connect() as connection:
                connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    return {"status": "ok", "version": __version__}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "font-src 'self' data:; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    return response
