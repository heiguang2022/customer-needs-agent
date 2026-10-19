from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from customer_needs_agent.agent import CustomerNeedsAgent
from customer_needs_agent.catalog import load_catalog
from customer_needs_agent.llm import ChatMessage
from customer_needs_agent.models import (
    Budget,
    ProductMatch,
    QueryProductsArgs,
    Recommendation,
    RecommendationDraft,
    RequirementExtraction,
    Requirements,
    Urgency,
)
from customer_needs_agent.repository import ConversationRepository
from customer_needs_agent.service import AnalysisService


class HeuristicFakeLLM:
    """测试专用确定性替身，不模拟模型质量，只验证编排契约。"""

    def extract_requirements(
        self, history: list[ChatMessage], previous: Requirements
    ) -> RequirementExtraction:
        text = " ".join(item["content"] for item in history if item["role"] == "user")
        requirements = previous.model_copy(deep=True)

        industries = ["制造", "零售", "电商", "金融", "医疗", "专业服务", "互联网", "贸易"]
        for industry in industries:
            if industry in text:
                requirements.business_type = industry
                break

        if "预算不确定" not in text and "暂不清楚预算" not in text:
            match = re.search(r"(?:预算|最多|不超过)?\s*(\d+(?:\.\d+)?)\s*万", text)
            if match:
                requirements.budget = Budget(max=float(match.group(1)) * 10_000)
            else:
                match = re.search(r"(?:预算|最多|不超过)\s*(\d+)\s*元", text)
                if match:
                    requirements.budget = Budget(max=float(match.group(1)))

        urgency_patterns = [
            (Urgency.CRITICAL, ["一周", "7天", "马上"]),
            (Urgency.HIGH, ["两周", "14天", "尽快"]),
            (Urgency.MEDIUM, ["一个月", "30天"]),
            (Urgency.LOW, ["不着急", "不急", "两个月"]),
        ]
        for urgency, words in urgency_patterns:
            if any(word in text for word in words):
                requirements.urgency = urgency
                break

        capabilities = [
            "客户管理",
            "销售预测",
            "生产计划",
            "库存管理",
            "文档协作",
            "在线客服",
            "工单管理",
            "终端防护",
            "安全运营",
            "数据看板",
            "自助分析",
        ]
        requirements.needs = [item for item in capabilities if item in text]
        missing = requirements.missing_fields
        question = f"请补充 {missing[0]}。" if missing else None
        return RequirementExtraction(requirements=requirements, clarification_question=question)

    def build_product_query(self, requirements: Requirements) -> QueryProductsArgs:
        assert requirements.business_type is not None
        assert requirements.budget.max is not None
        assert requirements.urgency is not None
        return QueryProductsArgs(
            business_type=requirements.business_type,
            budget_min=requirements.budget.min,
            budget_max=requirements.budget.max,
            urgency=requirements.urgency,
            required_capabilities=requirements.needs,
        )

    def compose_recommendations(
        self, requirements: Requirements, matches: list[ProductMatch]
    ) -> RecommendationDraft:
        return RecommendationDraft(
            recommendations=[
                Recommendation(
                    product_id=item.product.id,
                    name="模型可能写错的名称",
                    estimated_price=1,
                    fit_reasons=["覆盖客户明确提出的能力", "符合预算和交付周期"],
                    limitations=[],
                )
                for item in matches
            ]
        )


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[ConversationRepository]:
    repo = ConversationRepository(f"sqlite:///{tmp_path / 'test.db'}")
    repo.initialize()
    yield repo


@pytest.fixture
def service(repository: ConversationRepository) -> AnalysisService:
    agent = CustomerNeedsAgent(HeuristicFakeLLM(), load_catalog())
    return AnalysisService(repository, agent)
