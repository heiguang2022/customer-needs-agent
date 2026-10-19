"""连接入口层、Agent 和仓储的应用服务。"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from customer_needs_agent.agent import CustomerNeedsAgent
from customer_needs_agent.models import AnalysisRequest, AnalysisResponse, ConversationView
from customer_needs_agent.repository import ConversationRepository

logger = logging.getLogger(__name__)


class AnalysisService:
    """一个请求对应一个短生命周期的应用用例。"""

    def __init__(self, repository: ConversationRepository, agent: CustomerNeedsAgent) -> None:
        self._repository = repository
        self._agent = agent

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        started = time.perf_counter()
        state = self._repository.get_or_create(request.conversation_id)
        self._repository.add_message(state.conversation_id, "user", request.message)
        history = self._repository.get_history(state.conversation_id)
        result = self._agent.run(state.conversation_id, history, state.requirements)
        self._repository.save_analysis(
            result.response,
            tool_name=result.tool_name,
            tool_arguments=result.tool_arguments,
            tool_result=result.tool_result,
        )
        logger.info(
            "analysis_completed",
            extra={
                "conversation_id": str(state.conversation_id),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "status": result.response.status.value,
                "error_code": result.response.error.code if result.response.error else None,
                "tool_name": result.tool_name,
            },
        )
        return result.response

    def get_conversation(self, conversation_id: UUID) -> ConversationView:
        return self._repository.get_view(conversation_id)

    def healthy(self) -> bool:
        return self._repository.ping()
