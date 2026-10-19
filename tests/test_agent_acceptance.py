from uuid import uuid4

import pytest
from conftest import HeuristicFakeLLM

from customer_needs_agent.agent import CustomerNeedsAgent
from customer_needs_agent.catalog import load_catalog
from customer_needs_agent.llm import LLMError
from customer_needs_agent.models import AnalysisStatus, Requirements

CASES = [
    ("我们是零售公司，预算3万，两周上线，需要客户管理", AnalysisStatus.COMPLETED),
    ("电商企业预算5万，一周上线，需要在线客服和工单管理", AnalysisStatus.COMPLETED),
    ("金融企业预算25万，一个月上线安全运营平台", AnalysisStatus.COMPLETED),
    ("专业服务公司预算10万，不着急，需要销售预测", AnalysisStatus.COMPLETED),
    ("互联网公司预算6万，两周上线，需要数据看板", AnalysisStatus.COMPLETED),
    ("贸易公司预算4万，一个月上线，需要库存管理", AnalysisStatus.COMPLETED),
    ("预算3万，两周上线，需要客户管理", AnalysisStatus.NEEDS_CLARIFICATION),
    ("零售公司两周上线，需要客户管理", AnalysisStatus.NEEDS_CLARIFICATION),
    ("零售公司预算3万，需要客户管理", AnalysisStatus.NEEDS_CLARIFICATION),
    ("零售公司预算不确定，两周上线，需要客户管理", AnalysisStatus.NEEDS_CLARIFICATION),
    ("想买一套企业软件", AnalysisStatus.NEEDS_CLARIFICATION),
    ("制造企业预算20万，不着急，需要生产计划", AnalysisStatus.COMPLETED),
    ("医疗机构预算5万，一个月上线，需要文档协作", AnalysisStatus.COMPLETED),
    ("互联网公司预算2.6万，一周上线，需要库存管理", AnalysisStatus.COMPLETED),
    ("零售公司预算 3.5 万，两周上线，需要客户管理", AnalysisStatus.COMPLETED),
    ("金融公司暂不清楚预算，一个月上线，需要安全运营", AnalysisStatus.NEEDS_CLARIFICATION),
    ("制造企业预算30万，一周上线，需要生产计划", AnalysisStatus.FAILED),
    ("金融企业预算1万，一周上线，需要安全运营", AnalysisStatus.FAILED),
]


@pytest.mark.parametrize(("message", "expected"), CASES)
def test_acceptance_cases_have_stable_schema(message: str, expected: AnalysisStatus) -> None:
    agent = CustomerNeedsAgent(HeuristicFakeLLM(), load_catalog())
    result = agent.run(uuid4(), [{"role": "user", "content": message}], Requirements())
    assert result.response.status == expected
    assert result.response.model_validate(result.response.model_dump()) == result.response


class FailingFakeLLM(HeuristicFakeLLM):
    def extract_requirements(self, history, previous):  # type: ignore[no-untyped-def]
        raise LLMError("LLM_TEMPORARY_ERROR", "模型服务暂时不可用。", retryable=True)


@pytest.mark.parametrize("attempt", range(2))
def test_model_failures_are_stable_failed_responses(attempt: int) -> None:
    agent = CustomerNeedsAgent(FailingFakeLLM(), load_catalog())
    result = agent.run(
        uuid4(),
        [{"role": "user", "content": f"第 {attempt} 次请求"}],
        Requirements(),
    )
    assert result.response.status == AnalysisStatus.FAILED
    assert result.response.error is not None
    assert result.response.error.retryable is True


def test_model_cannot_change_catalog_facts() -> None:
    agent = CustomerNeedsAgent(HeuristicFakeLLM(), load_catalog())
    result = agent.run(
        uuid4(),
        [{"role": "user", "content": "零售公司预算3万，两周上线，需要客户管理"}],
        Requirements(),
    )
    assert result.response.recommendations[0].name == "启航 CRM"
    assert result.response.recommendations[0].estimated_price == 18_000
