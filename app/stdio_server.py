from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx
from pydantic import ValidationError
from app.auth.access_control import enforce_contract_access
from app.auth.jwt_validator import Auth0JWTValidator
from app.core.config import settings
from app.core.contracts import PROMPT_CONTRACTS, RESOURCE_CONTRACTS, SCOPES, TIERS, TOOL_CONTRACTS
from app.core.errors import ForbiddenError, RateLimitExceededError, UnauthorizedError, UpstreamError
from app.models.domain import AuthContext
from app.services.mcp_service import MCPService

MCP_PROTOCOL_VERSION = "2025-11-25"


def _log(message: str) -> None:
    # MCP stdio transport requires stdout to contain only protocol messages.
    print(f"[ps2-mcp-stdio] {message}", file=sys.stderr, flush=True)


def _resolve_resource_contract(uri: str, user_id: str):
    for candidate in RESOURCE_CONTRACTS:
        if "{user_id}" not in candidate.uri_template and candidate.uri_template == uri:
            return candidate
        if candidate.uri_template.startswith("portfolio://{user_id}/"):
            expected = candidate.uri_template.replace("{user_id}", user_id)
            if uri == expected:
                return candidate
    return None


def _auth0_base_url() -> str:
    domain = settings.auth0_domain.strip()
    if not domain or domain in {"example.us.auth0.com", "your-tenant.us.auth0.com"}:
        raise UnauthorizedError("AUTH0_DOMAIN is not configured")
    return f"https://{domain}"


def _auth0_device_scope() -> str:
    scope_env = os.getenv("MCP_AUTH0_SCOPES", "").strip()
    if scope_env:
        return scope_env
    return " ".join(sorted(SCOPES))


def _request_device_code(client: httpx.Client, base_url: str, client_id: str, audience: str, scope: str) -> dict[str, Any]:
    response = client.post(
        f"{base_url}/oauth/device/code",
        data={
            "client_id": client_id,
            "audience": audience,
            "scope": scope,
        },
    )
    if response.status_code >= 400:
        detail = response.text.strip()
        raise UnauthorizedError(f"Failed to start Auth0 device flow: {response.status_code} {detail}")
    payload = response.json()
    if not payload.get("device_code"):
        raise UnauthorizedError("Auth0 device flow response missing device_code")
    return payload


def _poll_device_token(client: httpx.Client, base_url: str, client_id: str, device_code: str, interval: int, expires_in: int) -> str:
    deadline = time.monotonic() + max(30, int(expires_in))
    poll_interval = max(1, int(interval))

    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        response = client.post(
            f"{base_url}/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": client_id,
            },
        )

        if response.status_code == 200:
            access_token = response.json().get("access_token")
            if access_token:
                return str(access_token)
            raise UnauthorizedError("Auth0 token response missing access_token")

        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        error = str(payload.get("error", "unknown_error"))
        description = str(payload.get("error_description", "")).strip()

        if error == "authorization_pending":
            continue
        if error == "slow_down":
            poll_interval += 5
            continue
        if error == "access_denied":
            raise UnauthorizedError("Auth0 login was denied")
        if error in {"expired_token", "expired_device_code"}:
            raise UnauthorizedError("Auth0 device code expired before login completed")
        raise UnauthorizedError(f"Auth0 token exchange failed: {error} {description}".strip())

    raise UnauthorizedError("Timed out waiting for Auth0 login completion")


def _build_auth0_context() -> AuthContext:
    validator = Auth0JWTValidator()
    client_id = settings.auth0_client_id.strip()
    if not client_id:
        raise UnauthorizedError("AUTH0_CLIENT_ID is not configured")
    audience = settings.auth0_audience.strip()
    if not audience:
        raise UnauthorizedError("AUTH0_AUDIENCE is not configured")

    base_url = _auth0_base_url()
    scope = _auth0_device_scope()

    with httpx.Client(timeout=20.0) as client:
        device_payload = _request_device_code(client, base_url, client_id, audience, scope)
        verification_url = device_payload.get("verification_uri_complete") or device_payload.get("verification_uri")
        user_code = device_payload.get("user_code", "")
        _log(f"Authenticate at: {verification_url}")
        if user_code:
            _log(f"User code: {user_code}")
        token = _poll_device_token(
            client=client,
            base_url=base_url,
            client_id=client_id,
            device_code=str(device_payload["device_code"]),
            interval=int(device_payload.get("interval", 5)),
            expires_in=int(device_payload.get("expires_in", 900)),
        )

    auth = validator.validate(token)
    if auth.tier not in TIERS:
        raise UnauthorizedError(f"Tier claim '{auth.tier}' is invalid")
    return auth


class StdioMCPServer:
    def __init__(self) -> None:
        self.service = MCPService()
        self.auth = _build_auth0_context()

    @staticmethod
    def _rpc_error(req_id: str | int | None, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
                "data": data or {},
            },
        }

    @staticmethod
    def _rpc_result(req_id: str | int | None, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    @staticmethod
    def _tool_result_payload(data: dict[str, Any], citations: list[dict[str, Any]], disclaimer: str) -> dict[str, Any]:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(data, ensure_ascii=True),
                }
            ],
            "structuredContent": data,
            "_meta": {
                "citations": citations,
                "disclaimer": disclaimer,
            },
        }

    async def _handle_method(self, method: str, params: dict[str, Any], req_id: str | int | None) -> dict[str, Any]:
        if method == "initialize":
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": "ps2-mcp-stdio", "version": "0.1.0"},
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": True, "listChanged": True},
                    "prompts": {"listChanged": True},
                },
            }
            return self._rpc_result(req_id, result)

        if method in {"notifications/initialized", "initialized"}:
            return self._rpc_result(req_id, {})

        if method == "ping":
            return self._rpc_result(req_id, {})

        if method == "tools/list":
            tools = []
            for contract in TOOL_CONTRACTS.values():
                if self.auth.tier not in contract.allowed_tiers:
                    continue
                if not all(scope in self.auth.scopes for scope in contract.required_scopes):
                    continue
                tools.append(
                    {
                        "name": contract.name,
                        "description": contract.description,
                        "inputSchema": contract.input_schema,
                        "_meta": {
                            "requiredScopes": sorted(list(contract.required_scopes)),
                            "allowedTiers": sorted(list(contract.allowed_tiers)),
                        },
                    }
                )
            return self._rpc_result(req_id, {"tools": tools})

        if method == "tools/call":
            name = params.get("name")
            if not name:
                return self._rpc_error(req_id, -32602, "Missing required field: name")
            arguments = params.get("arguments", {})
            contract = TOOL_CONTRACTS.get(name)
            if not contract:
                return self._rpc_error(req_id, -32602, f"Unknown tool: {name}")
            enforce_contract_access(self.auth, contract)
            response = await self.service.execute_tool(self.auth, name, arguments)
            return self._rpc_result(req_id, self._tool_result_payload(response.data, response.citations, response.disclaimer))

        if method == "resources/list":
            resources = []
            for contract in RESOURCE_CONTRACTS:
                if self.auth.tier not in contract.allowed_tiers:
                    continue
                if not all(scope in self.auth.scopes for scope in contract.required_scopes):
                    continue
                resolved_uri = contract.uri_template.replace("{user_id}", self.auth.sub)
                item = {
                    "name": contract.uri_template,
                    "description": contract.description,
                    "mimeType": "application/json",
                    "uri": resolved_uri,
                }
                if "{user_id}" in contract.uri_template:
                    item["uriTemplate"] = contract.uri_template
                resources.append(item)
            return self._rpc_result(req_id, {"resources": resources})

        if method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return self._rpc_error(req_id, -32602, "Missing required field: uri")
            contract = _resolve_resource_contract(uri, self.auth.sub)
            if not contract:
                return self._rpc_error(req_id, -32602, "Resource unavailable for this user")
            enforce_contract_access(self.auth, contract)
            response = await self.service.read_resource(self.auth, uri)
            return self._rpc_result(
                req_id,
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(response.data, ensure_ascii=True),
                        }
                    ]
                },
            )

        if method == "resources/subscribe":
            uri = params.get("uri")
            if not uri:
                return self._rpc_error(req_id, -32602, "Missing required field: uri")
            contract = _resolve_resource_contract(uri, self.auth.sub)
            if not contract:
                return self._rpc_error(req_id, -32602, "Resource unavailable for this user")
            if not contract.subscribable:
                return self._rpc_error(req_id, -32003, "insufficient_scope", {"detail": "Resource is not subscribable"})
            enforce_contract_access(self.auth, contract)
            payload = self.service.subs.subscribe(self.auth.sub, uri)
            return self._rpc_result(req_id, payload)

        if method == "resources/unsubscribe":
            uri = params.get("uri")
            if not uri:
                return self._rpc_error(req_id, -32602, "Missing required field: uri")
            contract = _resolve_resource_contract(uri, self.auth.sub)
            if not contract:
                return self._rpc_error(req_id, -32602, "Resource unavailable for this user")
            enforce_contract_access(self.auth, contract)
            payload = self.service.subs.unsubscribe(self.auth.sub, uri)
            return self._rpc_result(req_id, payload)

        if method == "resources/events":
            events = self.service.subs.pull_events(self.auth.sub)
            return self._rpc_result(req_id, {"events": events})

        if method == "prompts/list":
            prompts = []
            for contract in PROMPT_CONTRACTS:
                if self.auth.tier not in contract.allowed_tiers:
                    continue
                if not all(scope in self.auth.scopes for scope in contract.required_scopes):
                    continue
                prompts.append(
                    {
                        "name": contract.name,
                        "description": contract.description,
                        "argumentsSchema": contract.arguments_schema,
                    }
                )
            return self._rpc_result(req_id, {"prompts": prompts})

        if method in {"prompts/call", "prompts/get"}:
            name = params.get("name")
            if not name:
                return self._rpc_error(req_id, -32602, "Missing required field: name")
            contract = next((p for p in PROMPT_CONTRACTS if p.name == name), None)
            if not contract:
                return self._rpc_error(req_id, -32602, f"Unknown prompt: {name}")
            enforce_contract_access(self.auth, contract)
            response = await self.service.execute_prompt(self.auth, name)
            return self._rpc_result(req_id, self._tool_result_payload(response.data, response.citations, response.disclaimer))

        return self._rpc_error(req_id, -32601, f"Method not found: {method}")

    async def handle_request(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        req_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})

        if payload.get("jsonrpc") != "2.0":
            return self._rpc_error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")
        if not isinstance(method, str) or not method:
            return self._rpc_error(req_id, -32600, "Invalid Request: missing method")
        if not isinstance(params, dict):
            return self._rpc_error(req_id, -32600, "Invalid Request: params must be an object")

        # Notifications do not require replies.
        if req_id is None:
            try:
                await self._handle_method(method, params, req_id)
            except Exception as exc:  # pragma: no cover - best-effort log path
                _log(f"Notification handler error: {exc}")
            return None

        try:
            return await self._handle_method(method, params, req_id)
        except ForbiddenError as exc:
            return self._rpc_error(req_id, -32003, "insufficient_scope", {"detail": str(exc)})
        except RateLimitExceededError as exc:
            return self._rpc_error(req_id, -32029, "rate_limited", {"retry_after": exc.retry_after_seconds})
        except UpstreamError as exc:
            return self._rpc_error(req_id, -32050, "upstream_failure", {"detail": str(exc)})
        except ValidationError as exc:
            return self._rpc_error(req_id, -32602, "Invalid params", {"detail": str(exc)})
        except Exception as exc:  # pragma: no cover - guard for unexpected failures
            _log(f"Unhandled request error: {exc}")
            return self._rpc_error(req_id, -32603, "Internal error")


def _write_message(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def main() -> None:
    try:
        server = StdioMCPServer()
    except UnauthorizedError as exc:
        _log(f"Auth0 authentication failed: {exc}")
        sys.exit(1)

    _log(f"Started with tier={server.auth.tier}, user={server.auth.sub}, scopes={len(server.auth.scopes)}")

    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            request = json.loads(stripped)
        except json.JSONDecodeError:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error", "data": {}},
                }
            )
            continue

        response = asyncio.run(server.handle_request(request))
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    main()
