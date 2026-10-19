"""SQLite 会话持久化及仓储接口。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, select, text
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from customer_needs_agent.models import (
    AnalysisResponse,
    AnalysisStatus,
    ConversationView,
    MessageView,
    Requirements,
    ToolCallView,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ConversationRecord(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requirements_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    messages: Mapped[list[MessageRecord]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="MessageRecord.id"
    )
    tool_calls: Mapped[list[ToolCallRecord]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ToolCallRecord.id"
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    conversation: Mapped[ConversationRecord] = relationship(back_populates="messages")


class ToolCallRecord(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    arguments_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    conversation: Mapped[ConversationRecord] = relationship(back_populates="tool_calls")


class ConversationNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ConversationState:
    conversation_id: UUID
    status: AnalysisStatus
    requirements: Requirements


class ConversationRepository:
    """用短事务封装数据库细节，避免 Agent 依赖 SQLAlchemy。"""

    def __init__(self, database_url: str) -> None:
        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self._engine = create_engine(database_url, connect_args=connect_args)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self._engine)

    def ping(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def get_or_create(self, conversation_id: UUID | None) -> ConversationState:
        with self._sessions.begin() as session:
            if conversation_id is None:
                conversation_id = uuid4()
                requirements = Requirements()
                record = ConversationRecord(
                    id=str(conversation_id),
                    status=AnalysisStatus.NEEDS_CLARIFICATION.value,
                    requirements_json=requirements.model_dump_json(),
                )
                session.add(record)
                return ConversationState(
                    conversation_id=conversation_id,
                    status=AnalysisStatus.NEEDS_CLARIFICATION,
                    requirements=requirements,
                )

            existing_record = session.get(ConversationRecord, str(conversation_id))
            if existing_record is None:
                raise ConversationNotFoundError(str(conversation_id))
            return ConversationState(
                conversation_id=conversation_id,
                status=AnalysisStatus(existing_record.status),
                requirements=Requirements.model_validate_json(existing_record.requirements_json),
            )

    def add_message(self, conversation_id: UUID, role: str, content: str) -> None:
        with self._sessions.begin() as session:
            self._require_record(session, conversation_id)
            session.add(
                MessageRecord(conversation_id=str(conversation_id), role=role, content=content)
            )

    def get_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        with self._sessions() as session:
            statement = (
                select(MessageRecord)
                .where(MessageRecord.conversation_id == str(conversation_id))
                .order_by(MessageRecord.id)
            )
            return [
                {"role": item.role, "content": item.content}
                for item in session.scalars(statement).all()
            ]

    def save_analysis(
        self,
        response: AnalysisResponse,
        *,
        tool_name: str | None = None,
        tool_arguments: dict[str, object] | None = None,
        tool_result: dict[str, object] | None = None,
    ) -> None:
        with self._sessions.begin() as session:
            record = self._require_record(session, response.conversation_id)
            record.status = response.status.value
            record.requirements_json = response.requirements.model_dump_json()
            record.result_json = response.model_dump_json()
            record.updated_at = utc_now()
            session.add(
                MessageRecord(
                    conversation_id=record.id,
                    role="assistant",
                    content=response.model_dump_json(),
                )
            )
            if tool_name and tool_arguments is not None and tool_result is not None:
                session.add(
                    ToolCallRecord(
                        conversation_id=record.id,
                        tool_name=tool_name,
                        arguments_json=json.dumps(tool_arguments, ensure_ascii=False),
                        result_json=json.dumps(tool_result, ensure_ascii=False),
                    )
                )

    def get_view(self, conversation_id: UUID) -> ConversationView:
        with self._sessions() as session:
            record = self._require_record(session, conversation_id)
            # 在 session 内触发关系加载，避免对象离开事务后再访问数据库。
            messages = [
                MessageView(role=item.role, content=item.content, created_at=item.created_at)
                for item in record.messages
            ]
            tool_calls = [
                ToolCallView(
                    tool_name=item.tool_name,
                    arguments=json.loads(item.arguments_json),
                    result=json.loads(item.result_json),
                    created_at=item.created_at,
                )
                for item in record.tool_calls
            ]
            result = (
                AnalysisResponse.model_validate_json(record.result_json)
                if record.result_json
                else None
            )
            return ConversationView(
                conversation_id=UUID(record.id),
                status=AnalysisStatus(record.status),
                requirements=Requirements.model_validate_json(record.requirements_json),
                messages=messages,
                tool_calls=tool_calls,
                result=result,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )

    @staticmethod
    def _require_record(session: Session, conversation_id: UUID) -> ConversationRecord:
        record = session.get(ConversationRecord, str(conversation_id))
        if record is None:
            raise ConversationNotFoundError(str(conversation_id))
        return record
