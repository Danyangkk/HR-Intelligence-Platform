from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import User
from src.services.rbac import (
    BIZ_SUPER_ADMIN,
    TECH_SUPER_ADMIN,
    can_manage_users,
    normalize_role,
)

ROLE_LABELS = {
    TECH_SUPER_ADMIN: "技术超管",
    BIZ_SUPER_ADMIN: "业务超管",
    "staff": "普通员工",
}


def serialize_user(user: User) -> dict[str, Any]:
    """新规格：薪资权=业务超管角色自带，无需单独显示薪资权限状态。"""
    role = normalize_role(user.role)
    # 业务超管显示薪资徽章
    badge = " [🔑薪资]" if role == BIZ_SUPER_ADMIN else ""
    # 新规格：业务超管的薪资权是角色自带，固定返回 true；其他角色固定返回 false
    effective_payroll_access = (role == BIZ_SUPER_ADMIN)
    return {
        "username": user.username,
        "display_name": user.display_name or user.username,
        "employee_id": user.employee_id,
        "role": role,
        "role_label": ROLE_LABELS.get(role, role) + badge,
        "payroll_access": effective_payroll_access,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_by": user.created_by,
    }


async def list_users(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(select(User).order_by(User.id))
    return [serialize_user(u) for u in result.scalars().all()]


async def create_user(
    db: AsyncSession,
    *,
    actor: User,
    username: str,
    password: str,
    role: str,
    display_name: str,
    employee_id: str | None = None,
) -> dict[str, Any]:
    if not can_manage_users(actor.role):
        raise PermissionError("only tech_super_admin can create users")
    role = normalize_role(role)
    if role not in {TECH_SUPER_ADMIN, BIZ_SUPER_ADMIN, "staff"}:
        raise ValueError("invalid role")
    exists = await db.scalar(select(User.id).where(User.username == username))
    if exists:
        raise ValueError("username exists")
    must_change = role == BIZ_SUPER_ADMIN
    from passlib.context import CryptContext

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        username=username.strip(),
        password_hash=pwd.hash(password),
        role=role,
        display_name=display_name.strip(),
        employee_id=employee_id.strip() if employee_id else None,
        payroll_access=False,
        must_change_password=must_change,
        created_by=actor.username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return serialize_user(user)


async def update_user(
    db: AsyncSession,
    *,
    actor: User,
    username: str,
    role: str | None = None,
    display_name: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    if not can_manage_users(actor.role):
        raise PermissionError("only tech_super_admin can update users")
    user = await db.scalar(select(User).where(User.username == username))
    if not user:
        raise LookupError("user not found")
    if role is not None:
        user.role = normalize_role(role)
    if display_name is not None:
        user.display_name = display_name.strip()
    if is_active is not None:
        user.is_active = is_active
    await db.commit()
    return serialize_user(user)
