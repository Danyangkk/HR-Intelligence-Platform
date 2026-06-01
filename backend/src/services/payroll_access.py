from __future__ import annotations

import secrets
import time
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import PayrollAccessLog, PayrollGrantLog, User
from src.services.rbac import (
    can_grant_payroll_access,
    has_effective_payroll_access,
    is_tech_super_admin,
    normalize_role,
)

_CONFIRM_TTL_S = 1800  # 30分钟 TTL
_confirm_tokens: dict[str, dict[str, Any]] = {}


def _purge_expired_tokens() -> None:
    now = time.time()
    expired = [k for k, v in _confirm_tokens.items() if v.get("expires_at", 0) < now]
    for key in expired:
        _confirm_tokens.pop(key, None)


async def grant_payroll_access(
    db: AsyncSession,
    *,
    actor: User,
    target_username: str,
    reason: str,
) -> dict[str, Any]:
    if not can_grant_payroll_access(actor.role):
        raise PermissionError("only biz_super_admin can grant payroll_access")
    target = await db.scalar(select(User).where(User.username == target_username, User.is_active.is_(True)))
    if not target:
        raise LookupError("user not found")
    if is_tech_super_admin(target.role):
        raise ValueError("tech_super_admin cannot hold payroll_access")

    target.payroll_access = True
    db.add(
        PayrollGrantLog(
            target_username=target.username,
            action="grant",
            granted_by=actor.username,
            reason=reason.strip(),
        )
    )
    await db.commit()
    return {"username": target.username, "payroll_access": True}


async def revoke_payroll_access(
    db: AsyncSession,
    *,
    actor: User,
    target_username: str,
    reason: str | None = None,
) -> dict[str, Any]:
    if not can_grant_payroll_access(actor.role):
        raise PermissionError("only biz_super_admin can revoke payroll_access")
    target = await db.scalar(select(User).where(User.username == target_username, User.is_active.is_(True)))
    if not target:
        raise LookupError("user not found")
    target.payroll_access = False
    db.add(
        PayrollGrantLog(
            target_username=target.username,
            action="revoke",
            granted_by=actor.username,
            reason=(reason or "").strip() or None,
        )
    )
    await db.commit()
    return {"username": target.username, "payroll_access": False}


async def list_payroll_holders(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        select(User).where(User.payroll_access.is_(True), User.is_active.is_(True)).order_by(User.display_name)
    )
    items: list[dict[str, Any]] = []
    for user in result.scalars().all():
        grant = await db.scalar(
            select(PayrollGrantLog)
            .where(PayrollGrantLog.target_username == user.username, PayrollGrantLog.action == "grant")
            .order_by(desc(PayrollGrantLog.created_at))
            .limit(1)
        )
        items.append(
            {
                "username": user.username,
                "display_name": user.display_name or user.username,
                "employee_id": user.employee_id,
                "role": normalize_role(user.role),
                "granted_by": grant.granted_by if grant else "",
                "granted_at": grant.created_at.isoformat() if grant and grant.created_at else None,
                "grant_reason": grant.reason if grant else "",
            }
        )
    return items


async def log_payroll_access(
    db: AsyncSession,
    *,
    actor: str,  # username
    actor_display: str,  # 显示名称（姓名）
    employee_id: str | None,  # 工号
    target_ref: str,  # 访问对象：数据中台=表名，智能体=被查员工
    entry: str,  # 入口：数据中台 / 智能体
    fields: str,  # 实际访问的薪资字段
    reason: str,
) -> dict[str, Any]:
    """
    记录薪资访问审计（新规格）
    - actor: 访问人格式化为"姓名（工号）"，如"张HRD（HR0001）"
    - target_ref: 数据中台=表名（如"月度工资表"），智能体=被查员工（如"张三（A0123）"）
    - entry: "数据中台" 或 "智能体"
    - fields: 实际访问的薪资字段（如"工资""奖金"）
    - reason: 访问事由
    红线：永不记录薪资数值
    """
    # 格式化访问人：姓名（工号）
    if employee_id:
        formatted_actor = f"{actor_display}（{employee_id}）"
    else:
        formatted_actor = actor_display or actor
    
    row = PayrollAccessLog(
        actor=formatted_actor,  # 显示为"姓名（工号）"
        target_ref=target_ref,
        entry=entry,
        fields=fields,
        reason=reason.strip(),
    )
    db.add(row)
    await db.commit()
    return {"logged": True, "id": row.id}


async def create_confirm_token(
    db: AsyncSession,
    *,
    actor: User,
    target_ref: str,
    entry: str,
    fields: str,
    reason: str,
) -> dict[str, Any]:
    """
    创建薪资访问确认token并记录审计
    数据中台入口：target_ref=表名（如"月度工资表"），entry="数据中台"
    智能体入口：target_ref=被查员工（如"张三（A0123）"），entry="智能体"
    """
    if not has_effective_payroll_access(actor.role, actor.payroll_access):
        raise PermissionError("payroll_access required")
    
    await log_payroll_access(
        db,
        actor=actor.username,
        actor_display=actor.display_name or actor.username,
        employee_id=actor.employee_id,
        target_ref=target_ref,
        entry=entry,
        fields=fields,
        reason=reason,
    )
    _purge_expired_tokens()
    token = secrets.token_urlsafe(24)
    _confirm_tokens[token] = {
        "username": actor.username,
        "scope": entry,
        "expires_at": time.time() + _CONFIRM_TTL_S,
    }
    return {"confirm_token": token, "expires_in": _CONFIRM_TTL_S}


def validate_confirm_token(username: str, token: str | None) -> bool:
    """验证薪资确认token是否有效"""
    import sys
    
    print(f"[薪资Token验证] username={username}, token={token[:8] if token else None}...", file=sys.stderr)
    
    if not token:
        print(f"[薪资Token验证] ❌ token为空", file=sys.stderr)
        return False
    
    _purge_expired_tokens()
    payload = _confirm_tokens.get(token)
    
    if not payload:
        print(f"[薪资Token验证] ❌ token不存在于内存（可能已过期或未生成）", file=sys.stderr)
        print(f"[薪资Token验证] 当前内存中的tokens: {list(_confirm_tokens.keys())}", file=sys.stderr)
        return False
    
    if payload.get("username") != username:
        print(f"[薪资Token验证] ❌ username不匹配: payload={payload.get('username')}, request={username}", file=sys.stderr)
        return False
    
    print(f"[薪资Token验证] ✅ 验证通过! expires_at={payload.get('expires_at')}, now={time.time()}", file=sys.stderr)
    return True


async def list_payroll_access_logs(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    query = select(PayrollAccessLog)
    total = len((await db.scalars(query)).all())
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(desc(PayrollAccessLog.created_at)).offset(offset).limit(page_size))
    items = [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "actor": row.actor,
            "target_ref": row.target_ref,
            "entry": row.entry,
            "fields": row.fields,
            "reason": row.reason,
        }
        for row in result.scalars().all()
    ]
    return {"items": items, "total": total, "pagination": {"page": page, "page_size": page_size, "total": total}}
