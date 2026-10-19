"""领域模型、工具参数和对外接口模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """禁止未声明字段，避免模型输出悄悄绕过契约。"""

    model_config = ConfigDict(extra="forbid")


class AnalysisStatus(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    COMPLETED = "completed"
    FAILED = "failed"


class Urgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Budget(StrictModel):
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("预算下限不能高于预算上限")
        return self


class Requirements(StrictModel):
    business_type: str | None = Field(default=None, min_length=1, max_length=80)
    budget: Budget = Field(default_factory=Budget)
    urgency: Urgency | None = None
    needs: list[str] = Field(default_factory=list, max_length=20)

    @property
    def missing_fields(self) -> list[str]:
        """返回启动产品查询前必须补齐的字段。"""

        missing: list[str] = []
        if not self.business_type:
            missing.append("business_type")
        if self.budget.max is None:
            missing.append("budget")
        if self.urgency is None:
            missing.append("urgency")
        return missing


class RequirementExtraction(StrictModel):
    """模型每轮提取的合并后需求及建议追问。"""

    requirements: Requirements
    clarification_question: str | None = Field(default=None, max_length=300)


class QueryProductsArgs(StrictModel):
    business_type: str = Field(min_length=1, max_length=80)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float = Field(ge=0)
    urgency: Urgency
    required_capabilities: list[str] = Field(default_factory=list, max_length=20)


class Product(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    category: str
    annual_price: float = Field(gt=0)
    industries: list[str]
    capabilities: list[str]
    delivery_days: int = Field(gt=0)
    suitable_company_sizes: list[str]
    limitations: list[str] = Field(default_factory=list)


class ProductMatch(StrictModel):
    product: Product
    score: float = Field(ge=0)
    matched_capabilities: list[str] = Field(default_factory=list)


class Recommendation(StrictModel):
    product_id: str
    name: str
    estimated_price: float = Field(ge=0)
    fit_reasons: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class RecommendationDraft(StrictModel):
    recommendations: list[Recommendation] = Field(min_length=1, max_length=3)


class ErrorDetail(StrictModel):
    code: str
    message: str
    retryable: bool = False


class AnalysisRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class AnalysisResponse(StrictModel):
    conversation_id: UUID
    status: AnalysisStatus
    requirements: Requirements
    clarification_question: str | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status == AnalysisStatus.NEEDS_CLARIFICATION and (
            not self.clarification_question or self.recommendations
        ):
            raise ValueError("待澄清响应必须包含追问且不能包含推荐")
        if self.status == AnalysisStatus.COMPLETED and not self.recommendations:
            raise ValueError("完成响应必须至少包含一条推荐")
        if self.status == AnalysisStatus.FAILED and self.error is None:
            raise ValueError("失败响应必须包含错误详情")
        return self


class MessageView(StrictModel):
    role: str
    content: str
    created_at: datetime


class ToolCallView(StrictModel):
    tool_name: str
    arguments: dict[str, object]
    result: dict[str, object]
    created_at: datetime


class ConversationView(StrictModel):
    conversation_id: UUID
    status: AnalysisStatus
    requirements: Requirements
    messages: list[MessageView]
    tool_calls: list[ToolCallView]
    result: AnalysisResponse | None
    created_at: datetime
    updated_at: datetime
