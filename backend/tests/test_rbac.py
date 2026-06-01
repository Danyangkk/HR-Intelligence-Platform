from __future__ import annotations

import pytest

from src.services.rbac import (
    can_decide_review_suggestions,
    can_grant_payroll_access,
    can_manage_users,
    can_read_l3,
    can_view_payroll_category,
    can_write_data,
    has_effective_payroll_access,
    is_payroll_l3,
    mask_row,
    normalize_role,
    pii_check,
)


def test_legacy_role_mapping():
    assert normalize_role("hr_admin") == "biz_super_admin"
    assert normalize_role("viewer") == "staff"
    assert normalize_role("admin") == "staff"
    assert normalize_role("hr_specialist") == "staff"


def test_tech_super_admin_never_has_payroll():
    """新规格：技术超管永久无薪资权"""
    assert has_effective_payroll_access("tech_super_admin", True) is False
    assert has_effective_payroll_access("tech_super_admin", False) is False
    assert can_grant_payroll_access("tech_super_admin") is False


def test_biz_super_admin_has_payroll():
    """新规格：业务超管岗位自带薪资权"""
    assert has_effective_payroll_access("biz_super_admin", False) is True
    assert has_effective_payroll_access("biz_super_admin", True) is True
    assert can_grant_payroll_access("biz_super_admin") is False  # 新规格：无需授予


def test_staff_no_payroll():
    """新规格：普通员工永久薪资隔离"""
    assert can_write_data("staff") is True
    assert has_effective_payroll_access("staff", False) is False
    assert has_effective_payroll_access("staff", True) is False
    assert can_view_payroll_category("staff", False) is False
    assert can_view_payroll_category("staff", True) is False


def test_payroll_l3_requires_confirm_token():
    """业务超管访问薪资表需二次确认"""
    assert is_payroll_l3("l3-4-1-1") is True
    assert can_read_l3("biz_super_admin", "l3-4-1-1", payroll_access=True, payroll_confirmed=False) is False
    assert can_read_l3("biz_super_admin", "l3-4-1-1", payroll_access=False, payroll_confirmed=True) is True


def test_staff_blocked_from_payroll_l3():
    """普通员工永久无法访问薪资表"""
    assert can_read_l3("staff", "l3-4-1-1", payroll_access=False, payroll_confirmed=False) is False
    assert can_read_l3("staff", "l3-4-1-1", payroll_access=True, payroll_confirmed=True) is False


def test_tech_super_admin_non_payroll_read():
    """技术超管可读非薪资表（字段脱敏），永久不可读薪资表"""
    assert can_read_l3("tech_super_admin", "l3-2-4-1") is True
    assert can_read_l3("tech_super_admin", "l3-2-2-1") is True
    assert can_read_l3("tech_super_admin", "l3-4-1-1", payroll_confirmed=True) is False


def test_mask_row_non_payroll_staff():
    row = mask_row("staff", "l3-2-2-1", {"姓名": "张三", "身份证号": "110101199001011234"})
    assert row is not None
    assert row["姓名"] == "张三"
    assert row["身份证号"] == "***"


def test_pii_check_biz_with_payroll_confirmed():
    """业务超管二次确认后可查看薪资字段"""
    access = pii_check(
        "biz_super_admin",
        "l3-4-1-1",
        ["实发合计", "姓名"],
        payroll_access=False,  # 新规格：不看此参数
        payroll_confirmed=True,
    )
    assert access["实发合计"] == "allow"
    assert access["姓名"] == "allow"


def test_can_manage_users_only_tech():
    assert can_manage_users("tech_super_admin") is True
    assert can_manage_users("biz_super_admin") is False


def test_biz_problem_validator():
    from src.services.review_finding_validator import validate_biz_problem

    ok = validate_biz_problem("员工问年终奖怎么算，系统答不上来")
    assert ok["ok"] is True
    bad = validate_biz_problem("15例RAG 0命中集中在年终奖")
    assert bad["ok"] is False

    from src.services.review_finding_validator import validate_content_biz

    ok_sug = validate_content_biz("让系统能正确回答各部门成本类汇总问题")
    assert ok_sug["ok"] is True
    bad_sug = validate_content_biz("改 ROUTER §3 aggregate 判定")
    assert bad_sug["ok"] is False
    assert bad["issues"]


def test_suggestion_role_views():
    from src.services.improvement_tickets import MOCK_REVIEW_REPORTS
    from src.services.review_suggestions import enrich_review_report

    rep = dict(MOCK_REVIEW_REPORTS[1])
    biz = enrich_review_report(rep, role="biz_super_admin")
    tech = enrich_review_report(rep, role="tech_super_admin")
    bs = biz["suggestions"][1]
    ts = tech["suggestions"][1]
    assert "content_biz" in bs and "draft_changes" not in bs
    assert "各部门成本" in bs["content_biz"]
    assert "draft_changes" in ts and "content_biz" not in ts
    assert "ROUTER" in ts["draft_summary"]


def test_review_decision_only_biz():
    assert can_decide_review_suggestions("biz_super_admin") is True
    assert can_decide_review_suggestions("tech_super_admin") is False
    assert can_decide_review_suggestions("staff") is False


def test_ticket_track_only_biz():
    from src.services.rbac import can_track_tickets, can_operate_tickets

    assert can_track_tickets("biz_super_admin") is True
    assert can_track_tickets("tech_super_admin") is False
    assert can_operate_tickets("tech_super_admin") is True
    assert can_operate_tickets("biz_super_admin") is False
