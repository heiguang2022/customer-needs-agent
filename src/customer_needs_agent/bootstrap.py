"""集中装配运行时依赖。"""

from customer_needs_agent.agent import CustomerNeedsAgent
from customer_needs_agent.catalog import load_catalog
from customer_needs_agent.config import Settings
from customer_needs_agent.llm import SiliconFlowClient, UnconfiguredLLMClient
from customer_needs_agent.repository import ConversationRepository
from customer_needs_agent.service import AnalysisService


def build_service(settings: Settings) -> AnalysisService:
    """建立生产依赖；测试可直接传入自己的仓储和模型替身。"""

    repository = ConversationRepository(settings.database_url)
    repository.initialize()
    llm = SiliconFlowClient(settings) if settings.llm_configured else UnconfiguredLLMClient()
    agent = CustomerNeedsAgent(llm, load_catalog(), max_steps=settings.max_agent_steps)
    return AnalysisService(repository, agent)
