from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt as jose_jwt
from pydantic import BaseModel, ConfigDict, Field

from src.config import settings

_bearer = HTTPBearer(auto_error=False)


class TokenClaims(BaseModel):
    model_config = ConfigDict(extra="allow")

    sub: str | None = None
    exp: int | None = None
    tenant_id: str | None = None

    # M2M (client_credentials) fields
    grant_type: str | None = None
    scopes: list[str] = Field(default_factory=list)

    # Interactive user fields
    role: str | None = None


def get_current_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenClaims:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jose_jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenClaims(**payload)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_m2m_write(
    token: Annotated[TokenClaims, Depends(get_current_token)],
) -> TokenClaims:
    is_m2m = (
        token.grant_type == "client_credentials"
        and "inventory:write" in token.scopes
    )
    if not (is_m2m or token.role == "admin"):
        raise HTTPException(
            status_code=403,
            detail="Requires inventory:write scope (client_credentials) or admin role",
        )
    return token


def require_merchant_admin(
    token: Annotated[TokenClaims, Depends(get_current_token)],
) -> TokenClaims:
    if token.role != "merchant_admin":
        raise HTTPException(
            status_code=403,
            detail="Requires merchant_admin role",
        )
    return token


def verify_tenant_access(token: TokenClaims, tenant_id: str) -> None:
    if token.tenant_id is not None and token.tenant_id != tenant_id:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Token is scoped to tenant '{token.tenant_id}'; "
                f"cannot access tenant '{tenant_id}'"
            ),
        )
