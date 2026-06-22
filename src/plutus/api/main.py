from __future__ import annotations

from fastapi import Depends, FastAPI

from plutus.api import accumulation, shared, swing
from plutus.api.deps import get_app_settings
from plutus.api.errors import register_error_handlers
from plutus.api.schemas.shared import HealthOut, VersionOut
from plutus.config.settings import Settings


def create_app() -> FastAPI:
    app = FastAPI(title="Plutus v2 API", version="2.0.0")
    register_error_handlers(app)

    @app.get("/healthz", response_model=HealthOut, tags=["meta"])
    def healthz() -> HealthOut:
        return HealthOut(ok=True)

    @app.get("/version", response_model=VersionOut, tags=["meta"])
    def version(settings: Settings = Depends(get_app_settings)) -> VersionOut:
        return VersionOut(version="2.0.0")

    app.include_router(shared.router)
    app.include_router(swing.router)
    app.include_router(accumulation.router)
    return app


app = create_app()
