"""FastAPI HTTP 入口。"""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException, status

from customer_needs_agent.bootstrap import build_service
from customer_needs_agent.config import Settings, get_settings
from customer_needs_agent.logging_config import configure_logging
from customer_needs_agent.models import AnalysisRequest, AnalysisResponse, ConversationView
from customer_needs_agent.repository import ConversationNotFoundError
from customer_needs_agent.service import AnalysisService


def create_app(
    service: AnalysisService | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """创建应用；显式依赖参数让 API 测试完全不访问真实模型。"""

    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level, runtime_settings.log_file)
    runtime_service = service or build_service(runtime_settings)

    application = FastAPI(
        title="客户需求分析 Agent",
        version="0.1.0",
        description="提取企业软件采购需求、主动追问并调用本地产品查询工具。",
    )

    @application.post("/v1/analyses", response_model=AnalysisResponse)
    def analyze(request: AnalysisRequest) -> AnalysisResponse:
        try:
            return runtime_service.analyze(request)
        except ConversationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="指定的会话不存在。",
            ) from exc

    @application.get("/v1/conversations/{conversation_id}", response_model=ConversationView)
    def get_conversation(conversation_id: UUID) -> ConversationView:
        try:
            return runtime_service.get_conversation(conversation_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="指定的会话不存在。",
            ) from exc

    @application.get("/health")
    def health() -> dict[str, object]:
        database_ok = runtime_service.healthy()
        llm_configured = runtime_settings.llm_configured
        return {
            "status": "ok" if database_ok and llm_configured else "degraded",
            "database": "ok" if database_ok else "error",
            "llm_configured": llm_configured,
        }

    return application
