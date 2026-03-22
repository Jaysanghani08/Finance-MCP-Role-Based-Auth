from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.dependencies import enforce_contract_access, require_auth_context
from app.core.config import settings
from app.core.contracts import PROMPT_CONTRACTS, RESOURCE_CONTRACTS, SCOPES, TOOL_CONTRACTS
from app.core.errors import ForbiddenError, RateLimitExceededError, UpstreamError
from app.models.domain import AuthContext
from app.services.mcp_service import MCPService

app = FastAPI(title=settings.app_name, version="0.1.0")
service = MCPService()


class ToolInvokeRequest(BaseModel):
    arguments: dict = {}


class ResourceReadRequest(BaseModel):
    uri: str


class PromptInvokeRequest(BaseModel):
    name: str
    arguments: dict = {}


class SubscriptionRequest(BaseModel):
    uri: str


@app.exception_handler(ForbiddenError)
async def forbidden_handler(_: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "insufficient_scope", "detail": str(exc)},
        headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
    )


@app.exception_handler(RateLimitExceededError)
async def rate_limit_handler(_: Request, exc: RateLimitExceededError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "rate_limited", "detail": "Rate limit exceeded"},
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


@app.exception_handler(UpstreamError)
async def upstream_handler(_: Request, exc: UpstreamError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": "upstream_failure", "detail": str(exc)},
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource() -> dict:
    return {
        "resource": settings.auth0_audience,
        "authorization_servers": [f"https://{settings.auth0_domain}/"],
        "scopes_supported": sorted(list(SCOPES)),
        "bearer_methods_supported": ["header"],
    }


@app.get("/mcp/capabilities")
async def list_capabilities(auth: AuthContext = Depends(require_auth_context)) -> dict:
    return service.capability_discovery(auth)


@app.get("/mcp/contracts")
async def get_contracts(auth: AuthContext = Depends(require_auth_context)) -> dict:
    def _serialize(contract: object) -> dict:
        payload = {}
        for key, value in contract.__dict__.items():
            payload[key] = sorted(list(value)) if isinstance(value, set) else value
        return payload

    return {
        "tools": [_serialize(contract) for contract in TOOL_CONTRACTS.values() if auth.tier in contract.allowed_tiers],
        "resources": [_serialize(contract) for contract in RESOURCE_CONTRACTS if auth.tier in contract.allowed_tiers],
        "prompts": [_serialize(contract) for contract in PROMPT_CONTRACTS if auth.tier in contract.allowed_tiers],
    }


@app.post("/mcp/tools/{tool_name}")
async def invoke_tool(
    tool_name: str,
    body: ToolInvokeRequest,
    auth: AuthContext = Depends(require_auth_context),
) -> dict:
    contract = TOOL_CONTRACTS.get(tool_name)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")
    enforce_contract_access(auth, contract)
    response = await service.execute_tool(auth, tool_name, body.arguments)
    return response.model_dump()


@app.post("/mcp/resources/read")
async def read_resource(body: ResourceReadRequest, auth: AuthContext = Depends(require_auth_context)) -> dict:
    contract = None
    for candidate in RESOURCE_CONTRACTS:
        if candidate.uri_template == body.uri:
            contract = candidate
            break
        if candidate.uri_template == "portfolio://{user_id}/holdings" and body.uri == f"portfolio://{auth.sub}/holdings":
            contract = candidate
            break
        if candidate.uri_template == "portfolio://{user_id}/alerts" and body.uri == f"portfolio://{auth.sub}/alerts":
            contract = candidate
            break
        if candidate.uri_template == "portfolio://{user_id}/risk_score" and body.uri == f"portfolio://{auth.sub}/risk_score":
            contract = candidate
            break
    if not contract:
        raise HTTPException(status_code=404, detail="Resource unavailable for this user")
    enforce_contract_access(auth, contract)
    response = await service.read_resource(auth, body.uri)
    return response.model_dump()


@app.post("/mcp/resources/subscribe")
async def subscribe_resource(body: SubscriptionRequest, auth: AuthContext = Depends(require_auth_context)) -> dict:
    if auth.tier == "free":
        raise ForbiddenError("Free tier cannot subscribe to resources in PS2.")
    return service.subs.subscribe(auth.sub, body.uri)


@app.post("/mcp/resources/unsubscribe")
async def unsubscribe_resource(body: SubscriptionRequest, auth: AuthContext = Depends(require_auth_context)) -> dict:
    return service.subs.unsubscribe(auth.sub, body.uri)


@app.get("/mcp/resources/events")
async def pull_events(auth: AuthContext = Depends(require_auth_context)) -> dict:
    return {"events": service.subs.pull_events(auth.sub)}


@app.post("/mcp/prompts/invoke")
async def invoke_prompt(
    body: PromptInvokeRequest,
    auth: AuthContext = Depends(require_auth_context),
) -> dict:
    contract = next((p for p in PROMPT_CONTRACTS if p.name == body.name), None)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Unknown prompt: {body.name}")
    enforce_contract_access(auth, contract)
    response = await service.execute_prompt(auth, body.name)
    return response.model_dump()

