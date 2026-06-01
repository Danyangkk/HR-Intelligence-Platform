from datetime import date, datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, Float, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


class Category(Base):
    __tablename__ = "category"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("category.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Template(Base):
    __tablename__ = "template"

    l3_id: Mapped[str] = mapped_column(String(32), ForeignKey("category.id"), primary_key=True)
    columns: Mapped[list] = mapped_column(JSONB, nullable=False)
    filters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unique_key: Mapped[list] = mapped_column(JSONB, nullable=False)


class DataRecord(Base):
    __tablename__ = "data_record"
    __table_args__ = (UniqueConstraint("l3_id", "uk_hash", name="uq_data_record_l3_uk"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    l3_id: Mapped[str] = mapped_column(String(32), ForeignKey("category.id"), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    uk_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    l3_id: Mapped[str] = mapped_column(String(32), ForeignKey("category.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    doc_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    index_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    uploader: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    chunks: Mapped[list["DocChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocChunk(Base):
    __tablename__ = "doc_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("document.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    title_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1024), nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class FeishuSync(Base):
    __tablename__ = "feishu_sync"

    l3_id: Mapped[str] = mapped_column(String(32), ForeignKey("category.id"), primary_key=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="idle", nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    l3_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class AgentRunLog(Base):
    __tablename__ = "agent_run_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    replan_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    plan: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    trace: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tools_used: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    replan_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_feedback: Mapped[str | None] = mapped_column(String(8), nullable=True)
    auto_badcase: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    badcase_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    node_traces: Mapped[list["AgentNodeTrace"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    feedback_entries: Mapped[list["AgentFeedback"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AgentNodeTrace(Base):
    __tablename__ = "agent_node_trace"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(String(32), nullable=False)
    agent: Mapped[str] = mapped_column(String(32), nullable=False)
    skills_loaded: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tools_called: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="node_traces")


class AgentFeedback(Base):
    __tablename__ = "agent_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="feedback_entries")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="staff")
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    payroll_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PayrollGrantLog(Base):
    __tablename__ = "payroll_grant_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class PayrollAccessLog(Base):
    __tablename__ = "payroll_access_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    entry: Mapped[str] = mapped_column(String(64), nullable=False)
    fields: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ImprovementTicket(Base):
    __tablename__ = "improvement_ticket"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content_biz: Mapped[str] = mapped_column(Text, nullable=False)
    draft_changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    change_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_run_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee: Mapped[str] = mapped_column(String(64), nullable=False, default="tech_super_admin")
    # 工单来源关联：从复盘报告采纳建议生成 / 手动创建
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_report_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_finding_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_suggestion_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class EvalRun(Base):
    __tablename__ = "eval_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layer1_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layer1_pass: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layer2_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layer2_pass: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layer3_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layer3_scored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layer3_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer3_correctness_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer3_completeness_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer3_citation_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer3_compliance_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    weakness_summary: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    case_results: Mapped[list["EvalCaseResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvalCaseResult(Base):
    __tablename__ = "eval_case_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    layer: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expected: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    actual: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    violations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    run: Mapped[EvalRun] = relationship(back_populates="case_results")
