from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from app.auth.jwt_validator import Auth0JWTValidator
from app.core.contracts import MCPPromptContract, MCPResourceContract, MCPToolContract
from app.core.errors import ForbiddenError, UnauthorizedError
from app.models.domain import AuthContext

validator = Auth0JWTValidator()


def _www_auth_header(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    metadata_url = f"{base}/.well-known/oauth-protected-resource"
    return f'Bearer realm="ps2-mcp", resource_metadata="{metadata_url}"'


def _raise_401(request: Request, detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": _www_auth_header(request)},
    )


async def require_auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthContext:
    if not authorization:
        _raise_401(request, "Missing bearer token")
    if not authorization.lower().startswith("bearer "):
        _raise_401(request, "Malformed bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return validator.validate(token)
    except UnauthorizedError as exc:
        _raise_401(request, str(exc))
    raise RuntimeError("Unreachable")


def enforce_contract_access(auth: AuthContext, contract: MCPToolContract | MCPResourceContract | MCPPromptContract) -> None:
    if auth.tier not in contract.allowed_tiers:
        raise ForbiddenError("Tier is not allowed for this operation")
    missing = [scope for scope in contract.required_scopes if scope not in auth.scopes]
    if missing:
        raise ForbiddenError(f"insufficient_scope: missing {', '.join(sorted(missing))}")
