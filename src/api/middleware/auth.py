"""Authentication helpers for API and WebSocket requests."""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request, WebSocket


def configured_auth_token() -> Optional[str]:
    """Return the configured bearer token, if auth is enabled."""
    token = os.getenv("ATLAS_AUTH_TOKEN")
    if token:
        return token.strip()
    return None


def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Parse a bearer token from an Authorization header."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def is_valid_token(token: Optional[str]) -> bool:
    """Validate a token against the configured shared secret."""
    expected = configured_auth_token()
    if expected is None:
        return True
    if token is None:
        return False
    return secrets.compare_digest(token, expected)


async def require_api_auth(request: Request) -> None:
    """FastAPI dependency for REST authentication."""
    header_token = extract_bearer_token(request.headers.get("authorization"))
    query_token = request.query_params.get("token")
    if not is_valid_token(header_token or query_token):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def require_websocket_auth(websocket: WebSocket) -> bool:
    """Authenticate a WebSocket before normal handling."""
    header_token = extract_bearer_token(websocket.headers.get("authorization"))
    query_token = websocket.query_params.get("token")
    if is_valid_token(header_token or query_token):
        return True

    await websocket.accept()
    await websocket.close(code=1008, reason="Unauthorized")
    return False


__all__ = [
    "configured_auth_token",
    "extract_bearer_token",
    "is_valid_token",
    "require_api_auth",
    "require_websocket_auth",
]
