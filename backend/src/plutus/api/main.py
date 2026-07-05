from __future__ import annotations

from fastapi import Depends, FastAPI

from plutus.api import accumulation, ai, shared, swing
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

    from plutus.api.auth import require_token

    @app.post("/auth/verify", tags=["auth"])
    def verify_token(_: None = Depends(require_token)) -> dict[str, bool]:
        """Token verification endpoint for the React login screen.

        Returns 200 {"ok": true} when the bearer token is valid.
        Returns 401 when token is missing or invalid.
        """
        return {"ok": True}

    app.include_router(shared.router)
    app.include_router(swing.router)
    app.include_router(accumulation.router)
    app.include_router(ai.router)
    return app


app = create_app()
