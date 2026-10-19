from uuid import uuid4

from fastapi.testclient import TestClient

from customer_needs_agent.api import create_app
from customer_needs_agent.config import Settings
from customer_needs_agent.models import AnalysisRequest, AnalysisStatus
from customer_needs_agent.service import AnalysisService


def test_multi_turn_conversation_is_persisted(service: AnalysisService) -> None:
    first = service.analyze(AnalysisRequest(message="我们是零售企业，需要客户管理"))
    assert first.status == AnalysisStatus.NEEDS_CLARIFICATION

    second = service.analyze(
        AnalysisRequest(
            message="预算3万，希望两周上线",
            conversation_id=first.conversation_id,
        )
    )
    assert second.status == AnalysisStatus.COMPLETED
    view = service.get_conversation(first.conversation_id)
    assert len(view.messages) == 4
    assert len(view.tool_calls) == 1
    assert view.requirements.business_type == "零售"


def test_api_create_continue_and_read(service: AnalysisService, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        siliconflow_api_key="test",
        siliconflow_model="fake",
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
        log_file=str(tmp_path / "api.log"),
    )
    with TestClient(create_app(service, settings)) as client:
        first = client.post("/v1/analyses", json={"message": "零售企业需要客户管理"})
        assert first.status_code == 200
        conversation_id = first.json()["conversation_id"]

        second = client.post(
            "/v1/analyses",
            json={"message": "预算3万，两周上线", "conversation_id": conversation_id},
        )
        assert second.status_code == 200
        assert second.json()["status"] == "completed"

        stored = client.get(f"/v1/conversations/{conversation_id}")
        assert stored.status_code == 200
        assert len(stored.json()["tool_calls"]) == 1


def test_api_unknown_conversation_returns_404(service: AnalysisService, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(log_file=str(tmp_path / "api.log"))
    with TestClient(create_app(service, settings)) as client:
        response = client.get(f"/v1/conversations/{uuid4()}")
    assert response.status_code == 404


def test_health_reports_configuration(service: AnalysisService, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(log_file=str(tmp_path / "api.log"))
    with TestClient(create_app(service, settings)) as client:
        response = client.get("/health")
    assert response.json() == {
        "status": "degraded",
        "database": "ok",
        "llm_configured": False,
    }
