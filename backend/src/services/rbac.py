from __future__ import annotations

from typing import Any, Literal

FieldAccess = Literal["allow", "mask", "deny"]

# 新权限模型 3 角色 + agent 服务账号
ROLES = frozenset({"tech_super_admin", "biz_super_admin", "staff", "agent"})

# 旧角色 → 新角色（兼容 JWT / 历史数据）
LEGACY_ROLE_MAP = {
    "super_admin": "tech_super_admin",
    "hr_admin": "biz_super_admin",
    "hr_specialist": "staff",
    "admin": "staff",
    "viewer": "staff",
}

TECH_SUPER_ADMIN = "tech_super_admin"
BIZ_SUPER_ADMIN = "biz_super_admin"
STAFF = "staff"
AGENT = "agent"

BUSINESS_WRITE_ROLES = frozenset({BIZ_SUPER_ADMIN, STAFF})
SYNC_ROLES = frozenset({TECH_SUPER_ADMIN, BIZ_SUPER_ADMIN})
REVIEW_VIEW_ROLES = frozenset({TECH_SUPER_ADMIN, BIZ_SUPER_ADMIN})
TICKET_TRACK_ROLES = frozenset({BIZ_SUPER_ADMIN})
TICKET_WORK_ROLES = frozenset({TECH_SUPER_ADMIN})

PAYROLL_L3_PREFIX = "l3-4-"
PAYROLL_CATEGORY_ID = "l1-4"

BLOCKED_L3_IDS = frozenset(
    {
        "l3-4-1-1",
        "l3-4-1-5",
        "l3-4-1-6",
        "l3-4-1-8",
    }
)

SENSITIVE_FIELDS = frozenset(
    {
        "实发合计",
        "应发合计",
        "基本工资",
        "岗位工资",
        "绩效工资",
        "个税",
        "社保(个人)",
        "公积金(个人)",
        "身份证号",
        "银行账号",
        "银行卡号",
        "实发",
        "应发",
        "实发金额",
        "基本薪金",
    }
)

INTERNAL_META_FIELDS = frozenset({"_locator"})
MASK_TOKEN = "***"


def normalize_role(role: str | None) -> str:
    value = (role or STAFF).strip()
    value = LEGACY_ROLE_MAP.get(value, value)
    return value if value in ROLES else STAFF


def is_payroll_l3(l3_id: str) -> bool:
    return str(l3_id or "").startswith(PAYROLL_L3_PREFIX)


def is_tech_super_admin(role: str) -> bool:
    return normalize_role(role) == TECH_SUPER_ADMIN


def has_effective_payroll_access(role: str, payroll_access: bool = False) -> bool:
    """新规格：薪资权=业务超管角色自带。技术超管、普通员工、agent 永久无薪资权。
    
    payroll_access 参数保留用于向后兼容，但实际判断只看角色。
    """
    role = normalize_role(role)
    if role == TECH_SUPER_ADMIN:
        return False
    if role == AGENT:
        return False
    if role == STAFF:
        return False
    if role == BIZ_SUPER_ADMIN:
        return True
    return False


def can_grant_payroll_access(role: str) -> bool:
    """新规格：薪资权岗位自带，无需授予。此函数保留用于向后兼容，始终返回 False。"""
    return False


def can_manage_users(role: str) -> bool:
    return normalize_role(role) == TECH_SUPER_ADMIN


def can_view_payroll_audit(role: str) -> bool:
    return normalize_role(role) in {TECH_SUPER_ADMIN, BIZ_SUPER_ADMIN}


def can_view_review_reports(role: str) -> bool:
    return normalize_role(role) in REVIEW_VIEW_ROLES


def can_decide_review_suggestions(role: str) -> bool:
    """复盘建议采纳/驳回/存疑：仅业务超管（决策者）。"""
    return normalize_role(role) == BIZ_SUPER_ADMIN


def can_view_eval_center(role: str) -> bool:
    """Eval 评测中心：仅技术超管（质量指标，业务超管不可见）。"""
    return normalize_role(role) == TECH_SUPER_ADMIN


def can_track_tickets(role: str) -> bool:
    return normalize_role(role) in TICKET_TRACK_ROLES


def can_operate_tickets(role: str) -> bool:
    return normalize_role(role) in TICKET_WORK_ROLES


def can_view_payroll_category(role: str, payroll_access: bool = False) -> bool:
    """新规格：只有业务超管可看薪资分类导览。"""
    role = normalize_role(role)
    if role == BIZ_SUPER_ADMIN:
        return True
    return False


def can_read_l3(role: str, l3_id: str, *, payroll_access: bool = False, payroll_confirmed: bool = False) -> bool:
    """读权限：薪资表仅业务超管+二次确认；非薪资表业务/技术超管/员工可读（技术超管走字段脱敏）。"""
    role = normalize_role(role)
    if is_payroll_l3(l3_id):
        if not has_effective_payroll_access(role, payroll_access):
            return False
        return payroll_confirmed
    if role == AGENT:
        return l3_id not in BLOCKED_L3_IDS
    return True


def can_write_data(role: str) -> bool:
    return normalize_role(role) in BUSINESS_WRITE_ROLES


def can_sync_feishu(role: str) -> bool:
    return normalize_role(role) in SYNC_ROLES


def can_view_audit(role: str) -> bool:
    return normalize_role(role) in {TECH_SUPER_ADMIN, BIZ_SUPER_ADMIN}


def should_reject_personal_salary_query(role: str, payroll_access: bool = False) -> bool:
    """新规格：普通员工/技术超管问个人薪资直接 reject；业务超管需二次确认（由上层处理）。
    
    返回 True = 应该 reject（普通员工/技术超管）
    返回 False = 不应 reject，但需二次确认（业务超管）
    """
    role = normalize_role(role)
    if role == BIZ_SUPER_ADMIN:
        return False
    return True


def pii_check(
    role: str,
    l3_id: str,
    fields: list[str],
    *,
    payroll_access: bool = False,
    payroll_confirmed: bool = False,
) -> dict[str, FieldAccess]:
    role = normalize_role(role)
    if not can_read_l3(role, l3_id, payroll_access=payroll_access, payroll_confirmed=payroll_confirmed):
        return {field: "deny" for field in fields}

    if is_payroll_l3(l3_id):
        if has_effective_payroll_access(role, payroll_access) and payroll_confirmed:
            return {field: "allow" for field in fields}
        return {field: "mask" for field in fields}

    if role in {TECH_SUPER_ADMIN, AGENT}:
        result: dict[str, FieldAccess] = {}
        for field in fields:
            if field in INTERNAL_META_FIELDS:
                result[field] = "allow"
            elif field in SENSITIVE_FIELDS or field.startswith("_"):
                result[field] = "mask"
            else:
                result[field] = "allow"
        return result

    result = {}
    for field in fields:
        if field in INTERNAL_META_FIELDS:
            result[field] = "allow"
        elif field in SENSITIVE_FIELDS or field.startswith("_"):
            result[field] = "mask"
        else:
            result[field] = "allow"
    return result


def mask_row(
    role: str,
    l3_id: str,
    row: dict[str, Any],
    *,
    payroll_access: bool = False,
    payroll_confirmed: bool = False,
) -> dict[str, Any] | None:
    if not can_read_l3(role, l3_id, payroll_access=payroll_access, payroll_confirmed=payroll_confirmed):
        return None
    access = pii_check(role, l3_id, list(row.keys()), payroll_access=payroll_access, payroll_confirmed=payroll_confirmed)
    masked: dict[str, Any] = {}
    for key, value in row.items():
        decision = access.get(key, "allow")
        if decision == "deny":
            continue
        if decision == "mask":
            masked[key] = MASK_TOKEN
        else:
            masked[key] = value
    return masked


def mask_items(
    role: str,
    l3_id: str,
    items: list[dict[str, Any]],
    *,
    payroll_access: bool = False,
    payroll_confirmed: bool = False,
) -> list[dict[str, Any]]:
    if not can_read_l3(role, l3_id, payroll_access=payroll_access, payroll_confirmed=payroll_confirmed):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in items:
        masked = mask_row(role, l3_id, item, payroll_access=payroll_access, payroll_confirmed=payroll_confirmed)
        if masked is not None:
            cleaned.append(masked)
    return cleaned


def guard_evidence_blocks(
    evidence: list[dict[str, Any]],
    *,
    role: str,
    payroll_access: bool = False,
    payroll_confirmed: bool = False,
) -> list[dict[str, Any]]:
    """二次脱敏闸：按角色 + payroll_confirmed 过滤/脱敏 evidence。

    业务超管确认后访问薪资表时必须传 payroll_confirmed=True，否则
    can_read_l3 会把整个薪资 block 过滤掉，导致 fan-out 查到的多张
    薪资表全部丢失。
    """
    role = normalize_role(role)
    cleaned: list[dict[str, Any]] = []
    for block in evidence:
        l3_id = str(block.get("l3_id") or "")
        if l3_id and not can_read_l3(
            role, l3_id, payroll_access=payroll_access, payroll_confirmed=payroll_confirmed
        ):
            continue
        rows = block.get("rows") or []
        if rows and l3_id:
            block = {
                **block,
                "rows": mask_items(
                    role, l3_id, rows,
                    payroll_access=payroll_access,
                    payroll_confirmed=payroll_confirmed,
                ),
            }
        cleaned.append(block)
    return cleaned
