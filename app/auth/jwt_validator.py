from __future__ import annotations

import time
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.errors import UnauthorizedError
from app.models.domain import AuthContext


class Auth0JWTValidator:
    def __init__(self) -> None:
        jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
        self.jwks_client = PyJWKClient(jwks_url)

    def validate(self, token: str) -> AuthContext:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token).key
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=settings.auth0_audience,
                issuer=settings.auth0_issuer,
            )
        except Exception as exc:
            raise UnauthorizedError("Invalid bearer token") from exc

        now = int(time.time())
        exp = int(claims.get("exp", 0))
        if exp <= now:
            raise UnauthorizedError("Token is expired")

        scopes = set(str(claims.get("scope", "")).split())
        tier = claims.get("https://ps2.example.com/tier", "free")
        sub = claims.get("sub")
        aud = claims.get("aud")

        if not sub:
            raise UnauthorizedError("Token subject missing")

        return AuthContext(sub=sub, tier=tier, scopes=scopes, exp=exp, aud=str(aud))

