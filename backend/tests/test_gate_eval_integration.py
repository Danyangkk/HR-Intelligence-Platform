"""Gate eval integration — diff, verdict, ticket flow."""

from __future__ import annotations

import pytest

from src.db.session import AsyncSessionLocal
from src.eval.baseline import get_released_baseline_run_id, set_released_baseline_run_id
from src.eval.set_version import get_eval_set_version, get_pipeline_version
from src.models import EvalCaseResult, EvalRun, ImprovementTicket
from src.services.eval_service import (
    compute_gate_diff,
    compute_gate_verdict,
    resolve_gate_l1_threshold,
)
from src.eval.case_draft import (
    build_eval_case_yaml_draft,
    find_stub_eval_case_ids,
    is_stub_eval_case,
)
from src.services.improvement_tickets import (
    TicketTransitionError,
    _serialize_ticket,
    accept_ticket,
    confirm_ticket_release,
    trigger_gate_run,
    update_ticket_new_case_ids,
)


def _cr(case_id: str, *, passed: bool) -> EvalCaseResult:
    return EvalCaseResult(run_id=1, case_id=case_id, layer=1, passed=passed)


def test_compute_gate_diff_categories():
    baseline_rows = [_cr("c1", passed=True), _cr("c2", passed=False)]
    current_rows = [
        _cr("c1", passed=False),
        _cr("c2", passed=True),
        _cr("c3", passed=True),
    ]
    cats = compute_gate_diff(
        current_rows=current_rows,
        baseline_rows=baseline_rows,
        new_case_ids=["c3"],
        all_case_ids={"c1", "c2", "c3"},
    )
    assert cats["c1"] == "new_fail"
    assert cats["c2"] == "fixed"
    assert cats["c3"] == "newly_added"


def test_compute_gate_diff_no_baseline():
    current_rows = [_cr("c1", passed=True), _cr("c2", passed=False)]
    cats = compute_gate_diff(
        current_rows=current_rows,
        baseline_rows=[],
        new_case_ids=["c1"],
        has_baseline=False,
        all_case_ids={"c1", "c2"},
    )
    assert cats["c1"] == "newly_added"
    assert cats["c2"] == "no_baseline"


@pytest.fixture
async def eval_run_ids():
    ids: list[int] = []
    yield ids
    if not ids:
        return
    async with AsyncSessionLocal() as db:
        for run_id in ids:
            row = await db.get(EvalRun, run_id)
            if row:
                await db.delete(row)
        await db.commit()


@pytest.fixture
async def ticket_ids():
    ids: list[int] = []
    yield ids
    if not ids:
        return
    async with AsyncSessionLocal() as db:
        for tid in ids:
            row = await db.get(ImprovementTicket, tid)
            if row:
                await db.delete(row)
        await db.commit()


@pytest.mark.asyncio
async def test_gate_verdict_requires_new_cases_pass(eval_run_ids):
    async with AsyncSessionLocal() as db:
        run = EvalRun(
            version="gate-test",
            trigger="ticket_gate",
            status="done",
            run_type="gate",
            layer1_total=10,
            layer1_pass=10,
            total_cases=10,
        )
        db.add(run)
        await db.flush()
        eval_run_ids.append(run.id)
        cats = {"e-new-1": "newly_added", "e-old-1": "unchanged"}
        for cid, cat in cats.items():
            db.add(
                EvalCaseResult(
                    run_id=run.id,
                    case_id=cid,
                    layer=1,
                    passed=(cid != "e-new-1"),
                    diff_category=cat,
                )
            )
        await db.commit()
        verdict, detail = await compute_gate_verdict(
            db, run, new_case_ids=["e-new-1"], categories=cats
        )
        assert verdict == "fail"
        assert detail["new_case_failures"] == ["e-new-1"]
        assert any("工单新增用例未全过" in r for r in detail["reasons"])


@pytest.mark.asyncio
async def test_gate_verdict_assert_rate_includes_layer2(eval_run_ids):
    async with AsyncSessionLocal() as db:
        run = EvalRun(
            version="gate-test",
            trigger="ticket_gate",
            status="done",
            run_type="gate",
            layer1_total=1,
            layer1_pass=1,
            total_cases=1,
        )
        db.add(run)
        await db.flush()
        eval_run_ids.append(run.id)
        cats = {"e-policy-1": "unchanged"}
        db.add(
            EvalCaseResult(
                run_id=run.id,
                case_id="e-policy-1",
                layer=1,
                passed=True,
                diff_category="unchanged",
            )
        )
        db.add(
            EvalCaseResult(
                run_id=run.id,
                case_id="e-policy-1",
                layer=2,
                passed=False,
                diff_category="unchanged",
            )
        )
        await db.commit()
        verdict, detail = await compute_gate_verdict(
            db, run, new_case_ids=[], categories=cats
        )
        assert verdict == "fail"
        assert detail["assert_pass_rate"] == 0.5
        assert any("断言通过率" in r for r in detail["reasons"])


@pytest.mark.asyncio
async def test_trigger_gate_validates_new_case_ids(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="in_progress",
            assignee="tech_super_admin",
            new_case_ids=["not-in-set"],
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        with pytest.raises(ValueError, match="不在评测集中"):
            await trigger_gate_run(db, ticket.id)


@pytest.mark.asyncio
async def test_trigger_gate_rejects_empty_new_case_ids(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="in_progress",
            assignee="tech_super_admin",
            new_case_ids=[],
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        with pytest.raises(ValueError, match="工单未声明评测用例"):
            await trigger_gate_run(db, ticket.id)


@pytest.mark.asyncio
async def test_release_moves_baseline_and_checks_version(eval_run_ids, ticket_ids):
    async with AsyncSessionLocal() as db:
        baseline_run = EvalRun(
            version="v1",
            trigger="manual",
            status="done",
            run_type="full",
            layer1_total=5,
            layer1_pass=5,
            total_cases=5,
        )
        gate_run = EvalRun(
            version="gate-工单#001",
            trigger="ticket_gate",
            status="done",
            run_type="gate",
            layer1_total=5,
            layer1_pass=5,
            total_cases=5,
            gate_verdict="pass",
        )
        db.add_all([baseline_run, gate_run])
        await db.flush()
        eval_run_ids.extend([baseline_run.id, gate_run.id])
        await set_released_baseline_run_id(db, baseline_run.id)

        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="gate_passed",
            assignee="tech_super_admin",
            linked_run_id=gate_run.id,
            gate_eval_set_version=get_eval_set_version(),
            gate_pipeline_version=get_pipeline_version(),
            new_case_ids=["e-policy-1"],
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)

        released = await confirm_ticket_release(db, ticket.id)
        assert released["status"] == "released"
        assert await get_released_baseline_run_id(db) == gate_run.id


@pytest.mark.asyncio
async def test_release_rejects_stale_eval_set_version(eval_run_ids, ticket_ids):
    async with AsyncSessionLocal() as db:
        run = EvalRun(
            version="gate",
            trigger="ticket_gate",
            status="done",
            run_type="gate",
            gate_verdict="pass",
            layer1_total=1,
            layer1_pass=1,
            total_cases=1,
        )
        db.add(run)
        await db.flush()
        eval_run_ids.append(run.id)
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="gate_passed",
            assignee="tech_super_admin",
            linked_run_id=run.id,
            gate_eval_set_version="stale-version",
            gate_pipeline_version=get_pipeline_version(),
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        with pytest.raises(ValueError, match="重新提测"):
            await confirm_ticket_release(db, ticket.id)


@pytest.mark.asyncio
async def test_accept_pending_to_in_progress(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="pending",
            assignee="tech_super_admin",
            new_case_ids=["e-policy-1"],
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        accepted = await accept_ticket(db, ticket.id)
        assert accepted["status"] == "in_progress"


@pytest.mark.asyncio
async def test_trigger_gate_rejects_pending_without_accept(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="pending",
            assignee="tech_super_admin",
            new_case_ids=["e-policy-1"],
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        with pytest.raises(TicketTransitionError, match="非法状态转移"):
            await trigger_gate_run(db, ticket.id)


@pytest.mark.asyncio
async def test_legacy_awaiting_gate_serializes_as_retest_pending():
    row = ImprovementTicket(
        title="t",
        content_biz="c",
        source="manual",
        status="awaiting_gate",
        assignee="tech_super_admin",
    )
    data = _serialize_ticket(row)
    assert data["status"] == "legacy_retest_pending"
    assert data["is_legacy_gate"] is True


@pytest.mark.asyncio
async def test_legacy_release_rejected_without_linked_run(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="awaiting_gate",
            assignee="tech_super_admin",
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        with pytest.raises(ValueError, match="未经过评测门禁"):
            await confirm_ticket_release(db, ticket.id)


@pytest.mark.asyncio
async def test_resolve_gate_l1_threshold_from_full_run(eval_run_ids):
    async with AsyncSessionLocal() as db:
        run = EvalRun(
            version="v1.4.0",
            trigger="manual",
            status="done",
            run_type="full",
            layer1_total=30,
            layer1_pass=26,
            total_cases=30,
        )
        db.add(run)
        await db.commit()
        eval_run_ids.append(run.id)
        threshold = await resolve_gate_l1_threshold(db)
        assert threshold == 0.85


def test_is_stub_eval_case_empty_expected():
    assert is_stub_eval_case({"id": "x", "expected": {}}) is True
    assert is_stub_eval_case({"id": "x", "expected": {"intent": "TODO"}}) is True
    assert is_stub_eval_case({"id": "x", "expected": {"intent": "policy", "answer_points": ["a"]}}) is False


def test_build_eval_case_yaml_draft_from_hint():
    text = build_eval_case_yaml_draft(
        ticket_id=12,
        draft_changes={"add_test_case": "aggregate 类用例 +1"},
        test_requirement=None,
        content_biz="让系统能正确回答「各部门成本」类汇总问题",
        source_phenomenon="含「成本」的部门级 aggregate 提问被 guardrail 拦截",
    )
    assert "e-tkt-012-1" in text
    assert "expected: {}" in text
    assert "guardrail" in text
    assert "aggregate" in text


def test_find_stub_eval_case_ids_on_repo_set():
    stubs = find_stub_eval_case_ids()
    assert stubs == []


@pytest.mark.asyncio
async def test_accept_does_not_prefill_new_case_ids(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="pending",
            assignee="tech_super_admin",
            new_case_ids=None,
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        accepted = await accept_ticket(db, ticket.id)
        assert accepted["status"] == "in_progress"
        assert accepted["new_case_ids"] == []
        assert accepted.get("eval_case_yaml_draft") is None


@pytest.mark.asyncio
async def test_in_progress_ticket_has_yaml_draft(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="in_progress",
            assignee="tech_super_admin",
            draft_changes={"add_test_case": "policy 类用例 +1"},
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        data = _serialize_ticket(ticket, role="tech_super_admin")
        assert data["eval_case_yaml_draft"]
        assert "e-tkt-" in data["eval_case_yaml_draft"]


@pytest.mark.asyncio
async def test_update_ticket_new_case_ids_validates_membership(ticket_ids):
    async with AsyncSessionLocal() as db:
        ticket = ImprovementTicket(
            title="t",
            content_biz="c",
            source="manual",
            status="in_progress",
            assignee="tech_super_admin",
        )
        db.add(ticket)
        await db.commit()
        ticket_ids.append(ticket.id)
        saved = await update_ticket_new_case_ids(db, ticket.id, ["e-policy-1"])
        assert saved["new_case_ids"] == ["e-policy-1"]
        with pytest.raises(ValueError, match="不在评测集中"):
            await update_ticket_new_case_ids(db, ticket.id, ["not-in-set"])


def test_no_runtime_eval_set_write_paths():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "eval_set.yaml" not in text and "EVAL_SET_PATH" not in text:
            continue
        if "write_text" in text and "eval_set.yaml" in text:
            offenders.append(str(path.relative_to(root.parent)))
        if "yaml.dump" in text and ("EVAL_SET_PATH" in text or "eval_set.yaml" in text):
            offenders.append(str(path.relative_to(root.parent)))
    assert offenders == []
