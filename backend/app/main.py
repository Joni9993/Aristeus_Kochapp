import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import admin, auth, plans, profile, recipes, stores
from .services.scheduler import start_scheduler, stop_scheduler

# Show INFO-level logs from our app logger in the terminal
_app_log = logging.getLogger("app")
_app_log.setLevel(logging.INFO)
if not _app_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s: %(name)s — %(message)s"))
    _app_log.addHandler(_h)
_app_log.propagate = False

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Aristeus Kochapp API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(stores.router)
app.include_router(plans.router)
app.include_router(recipes.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "aristeus-backend",
        "version": app.version,
        "env": settings.app_env,
        "time": datetime.now(timezone.utc).isoformat(),
    }
