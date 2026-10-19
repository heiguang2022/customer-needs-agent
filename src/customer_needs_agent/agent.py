"""Agent 编排：模型负责理解，程序负责不变量和工具执行。"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from pydantic import ValidationError

from customer_needs_agent.llm import ChatMessage, LLMClient, LLMError
from customer_needs_agent.models import (
    AnalysisResponse,
    AnalysisStatus,
    ErrorDetail,
    Product,
    ProductMatch,
    Recommendation,
    Requirements,
)
from customer_needs_agent.product_tool import query_products

CLARIFICATION_FALLBACKS = {
    "business_type": "请问贵公司的行业或主要业务类型是什么？",
    "budget": "这次软件采购可接受的年度预算上限是多少人民币？",
    "urgency": "期望在多长时间内完成上线？",
}


class AgentResult:
    """一次编排结果，附带可持久化的工具轨迹。"""

    def __init__(
        self,
        response: AnalysisResponse,
        *,
        tool_name: str | None = None,
        tool_arguments: dict[str, object] | None = None,
        tool_result: dict[str, object] | None = None,
    ) -> None:
        self.response = response
        self.tool_name = tool_name
        self.tool_arguments = tool_arguments
        self.tool_result = tool_result


class CustomerNeedsAgent:
    """执行最多四个阶段的需求分析流程。"""

    def __init__(self, llm: LLMClient, catalog: Sequence[Product], max_steps: int = 4) -> None:
        self._llm = llm
        self._catalog = tuple(catalog)
        self._max_steps = max_steps

    def run(
        self,
        conversation_id: UUID,
        history: list[ChatMessage],
        previous: Requirements,
    ) -> AgentResult:
        steps = 0
        current_requirements = previous
        try:
            extraction = self._llm.extract_requirements(history, previous)
            steps += 1
            requirements = extraction.requirements
            current_requirements = requirements
            missing = requirements.missing_fields
            if missing:
                question = extraction.clarification_question or CLARIFICATION_FALLBACKS[missing[0]]
                return AgentResult(
                    AnalysisResponse(
                        conversation_id=conversation_id,
                        status=AnalysisStatus.NEEDS_CLARIFICATION,
                        requirements=requirements,
                        clarification_question=question,
                    )
                )

            self._guard_step_budget(steps)
            query_args = self._llm.build_product_query(requirements)
            steps += 1
            matches = query_products(query_args, self._catalog)
            serialized_matches = [item.model_dump(mode="json") for item in matches]
            tool_arguments: dict[str, object] = query_args.model_dump(mode="json")
            tool_result: dict[str, object] = {"matches": serialized_matches}

            if not matches:
                return AgentResult(
                    AnalysisResponse(
                        conversation_id=conversation_id,
                        status=AnalysisStatus.FAILED,
                        requirements=requirements,
                        error=ErrorDetail(
                            code="NO_MATCH",
                            message="当前目录中没有同时满足行业、预算和上线周期约束的产品。",
                        ),
                    ),
                    tool_name="query_products",
                    tool_arguments=tool_arguments,
                    tool_result=tool_result,
                )

            self._guard_step_budget(steps)
            draft = self._llm.compose_recommendations(requirements, matches)
            steps += 1
            recommendations = self._sanitize_recommendations(draft.recommendations, matches)
            if not recommendations:
                raise LLMError("INVALID_RECOMMENDATIONS", "模型没有返回目录中的有效产品。")

            return AgentResult(
                AnalysisResponse(
                    conversation_id=conversation_id,
                    status=AnalysisStatus.COMPLETED,
                    requirements=requirements,
                    recommendations=recommendations,
                ),
                tool_name="query_products",
                tool_arguments=tool_arguments,
                tool_result=tool_result,
            )
        except (LLMError, ValidationError) as exc:
            code = getattr(exc, "code", "INVALID_MODEL_OUTPUT")
            retryable = bool(getattr(exc, "retryable", False))
            message = str(exc) if isinstance(exc, LLMError) else "模型输出不符合数据契约。"
            return AgentResult(
                AnalysisResponse(
                    conversation_id=conversation_id,
                    status=AnalysisStatus.FAILED,
                    requirements=current_requirements,
                    error=ErrorDetail(code=code, message=message, retryable=retryable),
                )
            )

    def _guard_step_budget(self, completed_steps: int) -> None:
        if completed_steps >= self._max_steps:
            raise LLMError("AGENT_STEP_LIMIT", "Agent 已达到最大执行步数。")

    @staticmethod
    def _sanitize_recommendations(
        recommendations: Sequence[Recommendation],
        matches: Sequence[ProductMatch],
    ) -> list[Recommendation]:
        """以工具结果覆盖模型给出的事实字段，彻底阻断产品和价格幻觉。"""

        allowed = {item.product.id: item.product for item in matches}
        cleaned: list[Recommendation] = []
        seen: set[str] = set()
        for recommendation in recommendations:
            product = allowed.get(recommendation.product_id)
            if product is None or product.id in seen:
                continue
            seen.add(product.id)
            cleaned.append(
                Recommendation(
                    product_id=product.id,
                    name=product.name,
                    estimated_price=product.annual_price,
                    fit_reasons=recommendation.fit_reasons,
                    limitations=product.limitations,
                )
            )
        return cleaned
