from __future__ import annotations

from app.core.contracts import MCPPromptContract, MCPResourceContract, MCPToolContract
from app.core.errors import ForbiddenError
from app.models.domain import AuthContext


def enforce_contract_access(auth: AuthContext, contract: MCPToolContract | MCPResourceContract | MCPPromptContract) -> None:
    if auth.tier not in contract.allowed_tiers:
        raise ForbiddenError("Tier is not allowed for this operation")
    missing = [scope for scope in contract.required_scopes if scope not in auth.scopes]
    if missing:
        raise ForbiddenError(f"insufficient_scope: missing {', '.join(sorted(missing))}")
