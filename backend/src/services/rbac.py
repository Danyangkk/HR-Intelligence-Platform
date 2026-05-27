from __future__ import annotations

from typing import Any, Literal

FieldAccess = Literal["allow", "mask", "deny"]

ROLES = frozenset({"super_admin", "hr_admin", "hr_specialist", "viewer", "agent"})

WRITE_ROLES = frozenset({"super_admin", "hr_admin", "hr_specialist"})
SYNC_ROLES = frozenset({"super_admin", "hr_admin"})
ADMIN_ROLES = frozenset({"super_admin", "hr_admin"})

# 个人薪资明细表 — viewer/agent 不可访问
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
    }
)

# 内部元数据字段，非 PII，需保留供溯源定位
INTERNAL_META_FIELDS = frozenset({"_locator"})

MASK_TOKEN = "***"


def normalize_role(role: str | None) -> str:
    value = (role or "viewer").strip()
    return value if value in ROLES else "viewer"


def can_read_l3(role: str, l3_id: str) -> bool:
    role = normalize_role(role)
    if role in ADMIN_ROLES:
        return True
    if l3_id in BLOCKED_L3_IDS and role in {"viewer", "agent"}:
        return False
    return True


def can_write_data(role: str) -> bool:
    return normalize_role(role) in WRITE_ROLES


def can_sync_feishu(role: str) -> bool:
    return normalize_role(role) in SYNC_ROLES


def can_view_audit(role: str) -> bool:
    return normalize_role(role) in ADMIN_ROLES


def pii_check(role: str, l3_id: str, fields: list[str]) -> dict[str, FieldAccess]:
    role = normalize_role(role)
    if not can_read_l3(role, l3_id):
        return {field: "deny" for field in fields}

    if role in ADMIN_ROLES:
        return {field: "allow" for field in fields}

    result: dict[str, FieldAccess] = {}
    for field in fields:
        if field in INTERNAL_META_FIELDS:
            result[field] = "allow"
        elif field in SENSITIVE_FIELDS or field.startswith("_"):
            result[field] = "mask"
        else:
            result[field] = "allow"
    return result


def mask_row(role: str, l3_id: str, row: dict[str, Any]) -> dict[str, Any] | None:
    if not can_read_l3(role, l3_id):
        return None
    access = pii_check(role, l3_id, list(row.keys()))
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


def mask_items(role: str, l3_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not can_read_l3(role, l3_id):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in items:
        masked = mask_row(role, l3_id, item)
        if masked is not None:
            cleaned.append(masked)
    return cleaned


def guard_evidence_blocks(evidence: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
    role = normalize_role(role)
    if role in ADMIN_ROLES:
        return evidence

    cleaned: list[dict[str, Any]] = []
    for block in evidence:
        l3_id = str(block.get("l3_id") or "")
        if l3_id and not can_read_l3(role, l3_id):
            continue
        rows = block.get("rows") or []
        if rows and l3_id:
            block = {**block, "rows": mask_items(role, l3_id, rows)}
        cleaned.append(block)
    return cleaned
