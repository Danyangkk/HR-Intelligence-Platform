from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_db
from src.models import User
from src.services.rbac import can_sync_feishu, can_view_audit, can_write_data, normalize_role

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    username: str
    role: str
    display_name: str | None = None
    authenticated: bool = False


def _decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        return CurrentUser(username="anonymous", role="viewer", authenticated=False)

    try:
        payload = _decode_token(credentials.credentials)
        username = str(payload.get("sub") or "")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    result = await db.execute(select(User).where(User.username == username, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

    return CurrentUser(
        username=user.username,
        role=normalize_role(user.role),
        display_name=user.display_name,
        authenticated=True,
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if not credentials:
        return CurrentUser(username="anonymous", role="viewer", authenticated=False)
    return await get_current_user(credentials, db)


def resolve_role(user: CurrentUser, requested_role: str | None = None) -> str:
    if user.authenticated:
        return user.role
    return normalize_role(requested_role)


def require_write(user: CurrentUser) -> None:
    if not can_write_data(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无写入权限")


def require_sync(user: CurrentUser) -> None:
    if not can_sync_feishu(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无飞书同步权限")


def require_audit_view(user: CurrentUser) -> None:
    if not can_view_audit(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无审计查看权限")
