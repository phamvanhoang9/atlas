"""Authentication helpers for API and WebSocket requests."""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request, WebSocket


def configured_auth_token() -> Optional[str]:
    """Return the configured bearer token, if auth is enabled.

    Returns:
      The stripped value of the `ATLAS_AUTH_TOKEN` env var, or None if it
      is unset or empty (in which case auth is disabled for local dev).
    """
    token = os.getenv("ATLAS_AUTH_TOKEN")
    if token:
        return token.strip()
    return None


def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Parse a bearer token from an Authorization header.

    Args:
      authorization: The raw `Authorization` header value, e.g.
        "Bearer abc123", or None if the header was absent.

    Returns:
      The token string, or None if the header is missing, the scheme
      is not "bearer" (case-insensitive), or no token follows it.
    """
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def is_valid_token(token: Optional[str]) -> bool:
    """Validate a token against the configured shared secret.

    Args:
      token: The token to check, or None if none was supplied.

    Returns:
      True if auth is disabled (no token configured) or the given token
      matches the configured secret using a constant-time comparison;
      False otherwise.
    """
    expected = configured_auth_token()
    if expected is None:
        return True
    if token is None:
        return False
    return secrets.compare_digest(token, expected)


async def require_api_auth(request: Request) -> None:
    """FastAPI dependency for REST authentication.

    Accepts the token from either the `Authorization: Bearer <token>`
    header or a `?token=` query parameter, preferring the header.

    Args:
      request: The incoming request to authenticate.

    Raises:
      HTTPException: With status 401 if auth is enabled and the supplied
        token is missing or does not match the configured secret.
    """
    header_token = extract_bearer_token(request.headers.get("authorization"))
    query_token = request.query_params.get("token")
    if not is_valid_token(header_token or query_token):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def require_websocket_auth(websocket: WebSocket) -> bool:
    """Authenticate a WebSocket before normal handling.

    Accepts the token from either the `Authorization` header or a
    `?token=` query parameter, preferring the header. On failure, the
    socket must still be accepted before it can be closed with a reason
    (ASGI requires accept-before-close), so this sends a 1008 policy
    violation close frame rather than raising.

    Args:
      websocket: The WebSocket connection to authenticate.

    Returns:
      True if the token is valid and the caller should proceed with
      normal handling. False if auth failed; the socket has already
      been accepted and closed with code 1008, and the caller must
      return without further use of the connection.
    """
    header_token = extract_bearer_token(websocket.headers.get("authorization"))
    query_token = websocket.query_params.get("token")
    if is_valid_token(header_token or query_token):
        return True

    # ASGI requires accept() before close() can carry a code/reason.
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
