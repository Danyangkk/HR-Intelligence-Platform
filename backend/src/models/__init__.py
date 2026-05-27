from datetime import date, datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
