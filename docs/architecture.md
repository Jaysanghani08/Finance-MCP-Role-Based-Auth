# Architecture Diagram

```mermaid
flowchart LR
  Client[MCPClient] -->|"PKCEAuthCodeFlow"| Auth0[Auth0AuthorizationServer]
  Auth0 -->|"JWTAccessToken"| Client
  Client -->|"BearerToken"| MCP[MCPResourceServer]
  MCP --> Meta[ProtectedResourceMetadataEndpoint]
  MCP --> AuthN[JWTSignatureExpAudScopeValidation]
  AuthN --> AuthZ[TierAndScopeEnforcement]
  AuthZ --> MCPPrimitives[ToolsResourcesPrompts]
  MCPPrimitives --> Risk[RiskEngine]
  MCPPrimitives --> Store[PortfolioAlertRiskPersistence]
  MCPPrimitives --> Subscriptions[ResourceSubscriptionService]
  MCPPrimitives --> RateLimit[TierRateLimiter]
  MCPPrimitives --> Cache[TTLCache]
  MCPPrimitives --> Audit[AuditLogger]
  Risk --> MarketAdapter[MarketDataAdapter]
  Risk --> NewsAdapter[NewsDataAdapter]
  Risk --> MacroAdapter[MacroDataAdapter]
  Risk --> MFAdapter[MutualFundAdapter]
```

## Components

- **MCP Resource Server**: FastAPI app exposing tools/resources/prompts.
- **AuthN/AuthZ**: Auth0 JWT validation, tier and scope checks, error semantics.
- **Risk Engine**: Portfolio analytics and cross-source reasoning.
- **Persistence**: User-scoped holdings, alerts, and risk score.
- **Subscriptions**: Event queue for subscribed resources.
- **Reliability controls**: Tier limits, upstream quota tracking, response caching.
