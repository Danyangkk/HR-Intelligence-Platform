from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_db
from src.models import User
from src.services.payroll_access import validate_confirm_token
from src.services.rbac import normalize_role

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    username: str
    role: str
    display_name: str | None = None
    employee_id: str | None = None
    payroll_access: bool = False
    must_change_password: bool = False
    authenticated: bool = False
    payroll_confirmed: bool = False


def _decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
    x_payroll_confirm: str | None = Header(None, alias="X-Payroll-Confirm"),
) -> CurrentUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        return CurrentUser(username="anonymous", role="staff", authenticated=False)

    try:
        payload = _decode_token(credentials.credentials)
        username = str(payload.get("sub") or "")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    result = await db.execute(select(User).where(User.username == username, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

    role = normalize_role(user.role)
    
    # Debug: 打印收到的薪资确认header
    import sys
    print(f"[get_current_user] X-Payroll-Confirm header: {x_payroll_confirm[:8] if x_payroll_confirm else None}...", file=sys.stderr)
    
    confirmed = validate_confirm_token(username, x_payroll_confirm)
    
    print(f"[get_current_user] username={username}, role={role}, confirmed={confirmed}", file=sys.stderr)
    
    # 新规格：业务超管的薪资权是角色自带
    effective_payroll_access = (role == "biz_super_admin")
    return CurrentUser(
        username=user.username,
        role=role,
        display_name=user.display_name,
        employee_id=user.employee_id,
        payroll_access=effective_payroll_access,
        must_change_password=bool(user.must_change_password),
        authenticated=True,
        payroll_confirmed=confirmed,
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
    x_payroll_confirm: str | None = Header(None, alias="X-Payroll-Confirm"),
) -> CurrentUser:
    if not credentials:
        return CurrentUser(username="anonymous", role="staff", authenticated=False)
    return await get_current_user(credentials, db, x_payroll_confirm)


def resolve_role(user: CurrentUser, requested_role: str | None = None) -> str:
    if user.authenticated:
        return normalize_role(user.role)
    return normalize_role(requested_role)


def require_write(user: CurrentUser) -> None:
    from src.services.rbac import can_write_data

    if not can_write_data(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无写入权限")


def require_sync(user: CurrentUser) -> None:
    from src.services.rbac import can_sync_feishu

    if not can_sync_feishu(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无飞书同步权限")


def require_audit_view(user: CurrentUser) -> None:
    from src.services.rbac import can_view_audit

    if not can_view_audit(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无审计查看权限")
