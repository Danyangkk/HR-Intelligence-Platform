from __future__ import annotations

import pytest

from src.services.rbac import (
    can_read_l3,
    can_sync_feishu,
    can_view_audit,
    can_write_data,
    mask_row,
    pii_check,
)


def test_pii_check_masks_sensitive_fields_for_viewer():
    access = pii_check("viewer", "l3-2-2-1", ["姓名", "身份证号", "工号"])
    assert access["姓名"] == "allow"
    assert access["身份证号"] == "mask"
    assert access["工号"] == "allow"


def test_pii_check_hr_admin_allows_all():
    access = pii_check("hr_admin", "l3-4-1-1", ["实发合计", "姓名"])
    assert access["实发合计"] == "allow"
    assert access["姓名"] == "allow"


def test_viewer_blocked_from_salary_detail_table():
    assert can_read_l3("viewer", "l3-4-1-1") is False
    assert can_read_l3("hr_admin", "l3-4-1-1") is True


def test_mask_row_redacts_sensitive_values():
    row = mask_row("viewer", "l3-2-2-1", {"姓名": "张三", "身份证号": "110101199001011234"})
    assert row is not None
    assert row["姓名"] == "张三"
    assert row["身份证号"] == "***"


def test_mask_row_preserves_locator_metadata():
    locator = [{"field": "工号", "value": "A0145"}]
    row = mask_row("viewer", "l3-5-1-1", {"姓名": "李四", "工号": "A0145", "_locator": locator})
    assert row is not None
    assert row["_locator"] == locator


def test_role_permissions():
    assert can_write_data("viewer") is False
    assert can_write_data("hr_specialist") is True
    assert can_sync_feishu("viewer") is False
    assert can_sync_feishu("hr_admin") is True
    assert can_view_audit("viewer") is False
    assert can_view_audit("hr_admin") is True
