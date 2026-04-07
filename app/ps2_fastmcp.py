"""FastMCP HTTP server: Auth0 OIDC proxy auth, tier/scope auth, tools, resources, prompts."""

from __future__ import annotations

import base64
import json
from typing import Any

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from pydantic import PrivateAttr, ValidationError

from fastmcp import FastMCP
from fastmcp.prompts import Message, PromptResult
from fastmcp.resources import ResourceContent, ResourceResult
from fastmcp.server.auth import AuthContext as FastMCPAuthContext
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools.base import Tool, ToolResult

from app.auth.access_control import enforce_contract_access
from app.core.config import settings
from app.core.contracts import (
    MCPResourceContract,
    MCPPromptContract,
    MCPToolContract,
    PROMPT_CONTRACTS,
    RESOURCE_CONTRACTS,
    SCOPES,
    TOOL_CONTRACTS,
)
import httpx
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import ForbiddenError, RateLimitExceededError, UpstreamError
from app.models.domain import AuthContext
from app.services.mcp_service import MCPService

TIER_CLAIM = "https://ps2.example.com/tier"

_service: MCPService | None = None


def _jwt_payload_unverified(jwt_str: str) -> dict[str, Any]:
    """Decode JWT payload without verifying (upstream already validated the token)."""
    try:
        parts = jwt_str.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        pad = "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        return json.loads(raw.decode())
    except Exception:
        return {}


def _rbac_claims(token: Any) -> dict[str, Any]:
    """Merge id_token claims with Auth0 API access-token claims for RBAC.

    With ``OIDCProxy(verify_id_token=True)``, ``token.claims`` reflects the id_token.
    Tier and RBAC ``permissions`` are often present only on the API access JWT.
    """
    merged = dict(token.claims)
    bearer = getattr(token, "token", None)
    if not bearer or not isinstance(bearer, str):
        return merged
    api = _jwt_payload_unverified(bearer)
    if not api:
        return merged
    if TIER_CLAIM in api:
        merged[TIER_CLAIM] = api[TIER_CLAIM]
    if isinstance(api.get("permissions"), list):
        merged["permissions"] = api["permissions"]
    return merged


def _token_to_auth(token: Any) -> AuthContext:
    """Build a domain AuthContext from the current request's FastMCP AccessToken."""
    if token is None:
        raise McpError(ErrorData(code=-32003, message="Not authenticated", data={}))
    claims = _rbac_claims(token)
    return AuthContext(
        sub=claims.get("sub", ""),
        tier=claims.get(TIER_CLAIM, "free"),
        scopes=_extract_scopes(token),
        exp=int(claims.get("exp", 0)),
        aud=str(claims.get("aud", "")),
    )


def _current_auth() -> AuthContext:
    """Convenience: get_access_token() -> domain AuthContext."""
    return _token_to_auth(get_access_token())


def _extract_scopes(token: Any) -> set[str]:
    """Combine OAuth scopes, Auth0 RBAC permissions, and JWT `scope` / `scp` claims."""
    scopes = set(token.scopes)
    merged = _rbac_claims(token)
    permissions = merged.get("permissions")
    if isinstance(permissions, list):
        scopes.update(permissions)
    bearer = getattr(token, "token", None)
    if isinstance(bearer, str):
        api = _jwt_payload_unverified(bearer)
        for key in ("scope", "scp"):
            val = api.get(key)
            if isinstance(val, str):
                scopes.update(val.split())
            elif isinstance(val, list):
                scopes.update(val)
    return scopes


def _make_tier_auth_check(allowed_tiers: set[str]):
    """Gate MCP tool/resource/prompt *visibility* by subscription tier only.

    Auth0 tokens often omit some API permissions even when the user should use a tool;
    requiring every ``required_scopes`` here hides premium/analyst tools in the client.
    Scopes are enforced at execution time via ``enforce_contract_access``.
    """
    def check(ctx: FastMCPAuthContext) -> bool:
        if ctx.token is None:
            return False
        tier = _rbac_claims(ctx.token).get(TIER_CLAIM, "free")
        return tier in allowed_tiers
    return check


def _resolve_resource_contract(uri: str, user_id: str) -> MCPResourceContract | None:
    for candidate in RESOURCE_CONTRACTS:
        if "{user_id}" not in candidate.uri_template and candidate.uri_template == uri:
            return candidate
        if candidate.uri_template.startswith("portfolio://{user_id}/"):
            expected = candidate.uri_template.replace("{user_id}", user_id)
            if uri == expected:
                return candidate
    return None


class PS2ContractTool(Tool):
    """Tool registered from a contract; auth is resolved per-request."""

    _service: MCPService = PrivateAttr()
    _contract: MCPToolContract = PrivateAttr()

    def __init__(self, contract: MCPToolContract, service: MCPService) -> None:
        auth_check = _make_tier_auth_check(contract.allowed_tiers)
        super().__init__(
            name=contract.name,
            description=contract.description,
            parameters=contract.input_schema,
            output_schema=contract.output_schema,
            auth=auth_check,
            meta={
                "requiredScopes": sorted(contract.required_scopes),
                "allowedTiers": sorted(contract.allowed_tiers),
            },
        )
        self._service = service
        self._contract = contract

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        auth = _current_auth()
        try:
            enforce_contract_access(auth, self._contract)
            response = await self._service.execute_tool(auth, self.name, arguments)
        except ForbiddenError as exc:
            raise McpError(
                ErrorData(code=-32003, message="insufficient_scope", data={"detail": str(exc)})
            ) from exc
        except RateLimitExceededError as exc:
            raise McpError(
                ErrorData(code=-32029, message="rate_limited", data={"retry_after": exc.retry_after_seconds})
            ) from exc
        except UpstreamError as exc:
            raise McpError(ErrorData(code=-32050, message="upstream_failure", data={"detail": str(exc)})) from exc
        except ValidationError as exc:
            raise McpError(ErrorData(code=-32602, message="Invalid params", data={"detail": str(exc)})) from exc

        return ToolResult(
            structured_content={
                "data": response.data,
                "citations": response.citations,
                "disclaimer": response.disclaimer,
            },
            meta={"citations": response.citations, "disclaimer": response.disclaimer},
        )


def _tool_response_to_prompt_result(
    payload: dict[str, Any], citations: list[dict[str, Any]], disclaimer: str
) -> PromptResult:
    body = {"data": payload, "citations": citations, "disclaimer": disclaimer}
    return PromptResult(
        Message(json.dumps(body, ensure_ascii=True)),
        meta={"citations": citations, "disclaimer": disclaimer},
    )


def _register_portfolio_resource(
    mcp: FastMCP, service: MCPService, rc: MCPResourceContract
) -> None:
    suffix = rc.uri_template.replace("portfolio://{user_id}/", "")
    uri_template = f"portfolio://{{user_id}}/{suffix}"
    auth_check = _make_tier_auth_check(rc.allowed_tiers)

    @mcp.resource(uri_template, mime_type="application/json", description=rc.description, auth=auth_check)
    async def portfolio_dynamic(user_id: str) -> ResourceResult:
        auth = _current_auth()
        if user_id != auth.sub:
            raise McpError(ErrorData(code=-32602, message="Resource unavailable for this user", data={}))
        enforce_contract_access(auth, rc)
        uri = f"portfolio://{user_id}/{suffix}"
        tr = await service.read_resource(auth, uri)
        return ResourceResult(
            ResourceContent(tr.data, mime_type="application/json"),
            meta={"citations": tr.citations, "disclaimer": tr.disclaimer},
        )


def _register_static_resource(
    mcp: FastMCP, service: MCPService, rc: MCPResourceContract
) -> None:
    """Register a static (no URI params) resource with tier-based visibility."""
    auth_check = _make_tier_auth_check(rc.allowed_tiers)
    uri = rc.uri_template

    @mcp.resource(uri, mime_type="application/json", description=rc.description, auth=auth_check)
    async def static_resource() -> ResourceResult:
        auth = _current_auth()
        enforce_contract_access(auth, rc)
        tr = await service.read_resource(auth, uri)
        return ResourceResult(
            ResourceContent(tr.data, mime_type="application/json"),
            meta={"citations": tr.citations, "disclaimer": tr.disclaimer},
        )


def _register_prompt(
    mcp: FastMCP, service: MCPService, pc: MCPPromptContract
) -> None:
    """Register a prompt with tier-based visibility."""
    auth_check = _make_tier_auth_check(pc.allowed_tiers)

    @mcp.prompt(name=pc.name, description=pc.description, auth=auth_check)
    async def prompt_handler() -> PromptResult:
        auth = _current_auth()
        try:
            enforce_contract_access(auth, pc)
            resp = await service.execute_prompt(auth, pc.name)
        except (ForbiddenError, UpstreamError, ValidationError) as exc:
            raise McpError(ErrorData(code=-32603, message=str(exc), data={})) from exc
        return _tool_response_to_prompt_result(resp.data, resp.citations, resp.disclaimer)


def create_app() -> FastMCP:
    """Build and return the fully-wired FastMCP server with Auth0 OIDC proxy."""
    if not settings.auth0_client_id or not settings.auth0_client_secret:
        raise RuntimeError(
            "AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET must be set in .env. "
            "Create a Regular Web Application in Auth0 and copy the credentials."
        )
    all_scopes = ["openid"] + sorted(SCOPES)
    auth_provider = OIDCProxy(
        config_url=f"https://{settings.auth0_domain}/.well-known/openid-configuration",
        client_id=settings.auth0_client_id,
        client_secret=settings.auth0_client_secret,
        audience=settings.auth0_audience,
        base_url=f"http://localhost:{settings.port}",
        required_scopes=all_scopes,
        verify_id_token=True,
    )
    # OIDCProxy's verify_id_token post-init sets valid_scopes and
    # _default_scope_str to all_scopes (for advertising / DCR), but also
    # sets required_scopes which the bearer-auth middleware enforces on
    # EVERY request.  We only need "openid" at the transport level;
    # per-tool auth checks handle fine-grained scope + tier enforcement.
    auth_provider.required_scopes = ["openid"]
    global _service
    mcp = FastMCP(name="ps2-mcp", auth=auth_provider)
    service = MCPService()
    _service = service

    # --- Tools (all contracts; visibility gated by per-tool auth check) ---
    for contract in TOOL_CONTRACTS.values():
        mcp.add_tool(PS2ContractTool(contract, service))

    # --- Subscription helper tools ---
    any_subscribable = any(rc.subscribable for rc in RESOURCE_CONTRACTS)
    if any_subscribable:

        @mcp.tool(
            name="ps2_resource_subscribe",
            description="Subscribe to change notifications for a subscribable resource URI.",
            output_schema={"type": "object"},
        )
        async def ps2_resource_subscribe(uri: str) -> ToolResult:
            auth = _current_auth()
            contract = _resolve_resource_contract(uri, auth.sub)
            if not contract:
                raise McpError(ErrorData(code=-32602, message="Resource unavailable for this user", data={}))
            if not contract.subscribable:
                raise McpError(
                    ErrorData(code=-32003, message="insufficient_scope", data={"detail": "Resource is not subscribable"})
                )
            enforce_contract_access(auth, contract)
            payload = service.subs.subscribe(auth.sub, uri)
            return ToolResult(structured_content=payload, meta={})

        @mcp.tool(
            name="ps2_resource_unsubscribe",
            description="Unsubscribe from a resource URI.",
            output_schema={"type": "object"},
        )
        async def ps2_resource_unsubscribe(uri: str) -> ToolResult:
            auth = _current_auth()
            contract = _resolve_resource_contract(uri, auth.sub)
            if not contract:
                raise McpError(ErrorData(code=-32602, message="Resource unavailable for this user", data={}))
            enforce_contract_access(auth, contract)
            payload = service.subs.unsubscribe(auth.sub, uri)
            return ToolResult(structured_content=payload, meta={})

        @mcp.tool(
            name="ps2_resource_pull_events",
            description="Pull pending subscription events.",
            output_schema={"type": "object", "properties": {"events": {"type": "array"}}, "required": ["events"]},
        )
        async def ps2_resource_pull_events() -> ToolResult:
            auth = _current_auth()
            events = service.subs.pull_events(auth.sub)
            return ToolResult(structured_content={"events": events}, meta={})

    # --- Resources ---
    for rc in RESOURCE_CONTRACTS:
        if rc.uri_template.startswith("portfolio://{user_id}/"):
            _register_portfolio_resource(mcp, service, rc)
        else:
            _register_static_resource(mcp, service, rc)

    # --- Prompts ---
    for pc in PROMPT_CONTRACTS:
        _register_prompt(mcp, service, pc)

    return mcp


mcp = create_app()


# ── RFC 9728 Protected Resource Metadata ──────────────────────────────


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def _protected_resource_metadata(request: Request) -> JSONResponse:
    return JSONResponse({
        "resource": f"http://localhost:{settings.port}",
        "authorization_servers": [f"https://{settings.auth0_domain}"],
        "scopes_supported": sorted(SCOPES),
        "bearer_methods_supported": ["header"],
    })


# ── Health-check endpoint ─────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def _health_endpoint(request: Request) -> JSONResponse:
    checks: dict = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for label, url in [
            ("yahoo_finance", "https://query1.finance.yahoo.com/v7/finance/quote?symbols=RELIANCE.NS"),
            ("mfapi", "https://api.mfapi.in/mf/120503"),
            ("rbi_proxy", "https://api.allorigins.win/raw?url=https://www.rbi.org.in/"),
        ]:
            try:
                r = await client.get(url)
                checks[label] = {
                    "status": "ok" if r.status_code == 200 else "degraded",
                    "http_code": r.status_code,
                }
            except Exception as exc:
                checks[label] = {"status": "error", "detail": str(exc)}
    if settings.news_api_key:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": "test", "pageSize": 1, "apiKey": settings.news_api_key},
                )
                checks["newsapi"] = {
                    "status": "ok" if r.status_code == 200 else "degraded",
                    "http_code": r.status_code,
                }
        except Exception as exc:
            checks["newsapi"] = {"status": "error", "detail": str(exc)}
    else:
        checks["newsapi"] = {"status": "not_configured"}

    quotas: dict = {}
    if _service:
        for key, (limit, window) in _service.upstream_quota._limits.items():
            queue = _service.upstream_quota._events.get(key)
            used = len(queue) if queue else 0
            quotas[key] = {
                "limit": limit,
                "used": used,
                "remaining": limit - used,
                "window": str(window),
            }

    healthy = all(
        c.get("status") in ("ok", "not_configured") for c in checks.values()
    )
    return JSONResponse({
        "status": "ok" if healthy else "degraded",
        "upstream_apis": checks,
        "upstream_quotas": quotas,
        "server": {"name": "ps2-mcp-server", "version": "0.1.0"},
    })


# ── WWW-Authenticate middleware (RFC 9728 §3) ────────────────────────


class _WWWAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if response.status_code == 401:
            meta_url = (
                f"http://localhost:{settings.port}"
                "/.well-known/oauth-protected-resource"
            )
            response.headers["WWW-Authenticate"] = (
                f'Bearer resource_metadata="{meta_url}"'
            )
        return response


def main() -> None:
    """Entry point: run the PS2 MCP server over HTTP."""
    mcp.run(
        transport="http",
        host=settings.host,
        port=settings.port,
        middleware=[ASGIMiddleware(_WWWAuthMiddleware)],
    )


if __name__ == "__main__":
    main()
