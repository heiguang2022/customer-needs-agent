"""模型客户端抽象及硅基流动实现。"""

from __future__ import annotations

import json
from typing import Any, Protocol, TypeVar, cast

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from customer_needs_agent.config import Settings
from customer_needs_agent.models import (
    ProductMatch,
    QueryProductsArgs,
    RecommendationDraft,
    RequirementExtraction,
    Requirements,
)
from customer_needs_agent.prompts import SYSTEM_PROMPT

StructuredT = TypeVar("StructuredT", bound=BaseModel)
ChatMessage = dict[str, str]


class LLMError(RuntimeError):
    """对外隐藏供应商细节的模型调用错误。"""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LLMClient(Protocol):
    """Agent 依赖的最小模型能力，测试可用确定性替身实现。"""

    def extract_requirements(
        self,
        history: list[ChatMessage],
        previous: Requirements,
    ) -> RequirementExtraction: ...

    def build_product_query(self, requirements: Requirements) -> QueryProductsArgs: ...

    def compose_recommendations(
        self,
        requirements: Requirements,
        matches: list[ProductMatch],
    ) -> RecommendationDraft: ...


class UnconfiguredLLMClient:
    """让服务在缺少密钥时仍可启动，并返回可理解的业务错误。"""

    @staticmethod
    def _raise() -> None:
        raise LLMError(
            "LLM_NOT_CONFIGURED",
            "尚未配置 SILICONFLOW_API_KEY 或 SILICONFLOW_MODEL。",
        )

    def extract_requirements(
        self,
        history: list[ChatMessage],
        previous: Requirements,
    ) -> RequirementExtraction:
        self._raise()
        raise AssertionError("unreachable")

    def build_product_query(self, requirements: Requirements) -> QueryProductsArgs:
        self._raise()
        raise AssertionError("unreachable")

    def compose_recommendations(
        self,
        requirements: Requirements,
        matches: list[ProductMatch],
    ) -> RecommendationDraft:
        self._raise()
        raise AssertionError("unreachable")


class SiliconFlowClient:
    """通过 OpenAI 兼容协议调用硅基流动。"""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_configured:
            raise LLMError(
                "LLM_NOT_CONFIGURED",
                "尚未配置 SILICONFLOW_API_KEY 或 SILICONFLOW_MODEL。",
            )
        self._model = settings.siliconflow_model
        self._client = OpenAI(
            api_key=settings.siliconflow_api_key.get_secret_value(),
            base_url=settings.siliconflow_base_url,
            timeout=settings.request_timeout_seconds,
            max_retries=2,
        )

    def _structured_completion(
        self,
        messages: list[dict[str, Any]],
        output_type: type[StructuredT],
        schema_name: str,
    ) -> StructuredT:
        schema = output_type.model_json_schema()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=cast(Any, messages),
                response_format=cast(
                    Any,
                    {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "strict": True,
                            "schema": schema,
                        },
                    },
                ),
                temperature=0,
            )
            content = response.choices[0].message.content or ""
            try:
                return output_type.model_validate_json(content)
            except ValidationError:
                # 只允许一次格式修复，避免把不可控模型变成无限重试循环。
                repair = self._client.chat.completions.create(
                    model=self._model,
                    messages=cast(
                        Any,
                        [
                            *messages,
                            {"role": "assistant", "content": content},
                            {
                                "role": "user",
                                "content": "上一个响应不符合 Schema。请只返回修正后的 JSON。",
                            },
                        ],
                    ),
                    response_format=cast(
                        Any,
                        {
                            "type": "json_schema",
                            "json_schema": {
                                "name": schema_name,
                                "strict": True,
                                "schema": schema,
                            },
                        },
                    ),
                    temperature=0,
                )
                repaired = repair.choices[0].message.content or ""
                return output_type.model_validate_json(repaired)
        except LLMError:
            raise
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            retryable = status_code in {429, 500, 503, 504}
            code = "LLM_TEMPORARY_ERROR" if retryable else "LLM_REQUEST_FAILED"
            raise LLMError(code, "模型服务暂时不可用，请稍后重试。", retryable=retryable) from exc

    def extract_requirements(
        self,
        history: list[ChatMessage],
        previous: Requirements,
    ) -> RequirementExtraction:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    f"请结合完整对话返回合并后的需求。已有结构化状态：{previous.model_dump_json()}"
                ),
            },
            *history,
        ]
        return self._structured_completion(
            messages, RequirementExtraction, "requirement_extraction"
        )

    def build_product_query(self, requirements: Requirements) -> QueryProductsArgs:
        tool = {
            "type": "function",
            "function": {
                "name": "query_products",
                "description": "根据已确认的客户需求查询本地企业软件产品目录。",
                "parameters": QueryProductsArgs.model_json_schema(),
            },
        }
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=cast(
                    Any,
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "需求已经完整，请调用 query_products。需求："
                                f"{requirements.model_dump_json()}"
                            ),
                        },
                    ],
                ),
                tools=cast(Any, [tool]),
                tool_choice=cast(
                    Any,
                    {"type": "function", "function": {"name": "query_products"}},
                ),
                temperature=0,
            )
            calls = response.choices[0].message.tool_calls or []
            if not calls:
                raise LLMError("TOOL_CALL_MISSING", "模型没有生成必需的产品查询调用。")
            function_call = cast(Any, calls[0]).function
            if function_call.name != "query_products":
                raise LLMError("TOOL_CALL_MISSING", "模型没有生成必需的产品查询调用。")
            return QueryProductsArgs.model_validate_json(function_call.arguments)
        except LLMError:
            raise
        except (ValidationError, json.JSONDecodeError) as exc:
            raise LLMError("INVALID_TOOL_ARGUMENTS", "产品查询参数不符合约定。") from exc
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            retryable = status_code in {429, 500, 503, 504}
            raise LLMError(
                "LLM_TEMPORARY_ERROR" if retryable else "LLM_REQUEST_FAILED",
                "模型服务暂时不可用，请稍后重试。",
                retryable=retryable,
            ) from exc

    def compose_recommendations(
        self,
        requirements: Requirements,
        matches: list[ProductMatch],
    ) -> RecommendationDraft:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "根据需求和工具结果生成最多 3 条推荐。product_id、名称、价格和限制必须"
                    "严格来自工具结果，只解释匹配原因。\n需求："
                    f"{requirements.model_dump_json()}\n工具结果："
                    f"{json.dumps([item.model_dump(mode='json') for item in matches], ensure_ascii=False)}"  # noqa: E501
                ),
            },
        ]
        return self._structured_completion(messages, RecommendationDraft, "recommendations")
