from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from plutus.api.deps import get_app_settings
from plutus.config.settings import Settings


def require_token(
    authorization: str = Header(default=""),
    settings: Settings = Depends(get_app_settings),
) -> None:
    """Single-operator bearer token. Applied to every domain router.

    /healthz and /version are the only unauthenticated routes.
    In dev/test with no api_token configured, authentication is bypassed.
    """
    token = settings.api_token
    if token is None:
        # No token configured — allow in dev/test; blocked in prod by Settings validator.
        return
    if authorization != f"Bearer {token.get_secret_value()}":
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")
