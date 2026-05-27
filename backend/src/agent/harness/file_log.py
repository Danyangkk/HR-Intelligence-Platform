"""Human-readable harness log file — easy for operators to tail/read."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
_LOG_FILE = _LOG_DIR / "agent-run.log"
_LOCK = threading.Lock()
_HEADER = """# 人力超级智能体 · 运行日志（Agent Harness）
# 本文件只记录运行元信息，不含问题原文、薪资、文档正文等敏感内容。
# 查看最新：tail -f backend/logs/agent-run.log
# 说明文档：backend/logs/README.txt
#
"""

_initialized = False


def log_file_path() -> Path:
    return _LOG_FILE


def _ensure_log_file() -> None:
    global _initialized
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not _LOG_FILE.exists():
        _LOG_FILE.write_text(_HEADER, encoding="utf-8")
        _initialized = True
    elif not _initialized:
        _initialized = True


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append(lines: str) -> None:
    _ensure_log_file()
    with _LOCK:
        with _LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(lines)
            if not lines.endswith("\n"):
                fh.write("\n")


def _format_decision(decision: dict[str, Any] | None) -> str:
    if not decision:
        return "—"
    return json.dumps(decision, ensure_ascii=False, separators=(",", ":"))


def log_run_start(
    *,
    run_id: str,
    session_id: str,
    role: str,
    question_hash: str,
    actor: str | None = None,
) -> None:
    actor_line = f"  操作者       : {actor}\n" if actor else ""
    _append(
        f"\n{'=' * 78}\n"
        f"[{_now()}] ▶ 新问答开始\n"
        f"  运行 run_id  : {run_id}\n"
        f"  会话 session : {session_id}\n"
        f"  角色 role    : {role}\n"
        f"{actor_line}"
        f"  问题指纹     : {question_hash[:16]}…（SHA-256，不存原文）\n"
        f"{'-' * 78}\n"
    )


def log_node(
    *,
    run_id: str,
    seq: int,
    node: str,
    agent: str,
    status: str,
    attempt: int,
    duration_ms: int,
    intent: str = "",
    decision: dict[str, Any] | None = None,
    error_type: str | None = None,
) -> None:
    status_icon = {
        "ok": "✓",
        "retry": "↻",
        "failed": "✗",
        "timeout": "⏱",
        "skipped": "−",
    }.get(status, "·")
    attempt_note = f" · 第{attempt}次尝试" if attempt > 1 else ""
    err_note = f" · 错误={error_type}" if error_type else ""
    intent_note = f" · intent={intent}" if intent else ""
    _append(
        f"[{_now()}] {status_icon} 节点 #{seq} {node} ({agent}) · {status.upper()}"
        f" · {duration_ms}ms{attempt_note}{intent_note}{err_note}\n"
        f"  判定 meta   : {_format_decision(decision)}\n"
    )


def log_run_end(
    *,
    run_id: str,
    outcome: str,
    intent: str,
    total_ms: int,
    node_count: int,
    replan_count: int,
    reject_reason: str | None = None,
) -> None:
    outcome_label = {
        "success": "成功",
        "reject": "拒答",
        "clarify": "澄清",
        "timeout": "超时",
        "error": "异常",
        "running": "未完成",
    }.get(outcome, outcome)
    extra = ""
    if reject_reason:
        extra = f"\n  原因         : {reject_reason[:120]}"
    _append(
        f"[{_now()}] ■ 问答结束 · {outcome_label} ({outcome})"
        f" · 总耗时 {total_ms}ms · 节点 {node_count} 个 · replan {replan_count} 次\n"
        f"  最终 intent  : {intent or '—'}\n"
        f"  run_id       : {run_id}{extra}\n"
        f"{'=' * 78}\n"
    )
