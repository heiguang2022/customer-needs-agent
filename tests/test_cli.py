from typer.testing import CliRunner

from customer_needs_agent import cli
from customer_needs_agent.service import AnalysisService


def test_cli_analyze_outputs_json(monkeypatch, service: AnalysisService) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "_service", lambda: service)
    result = CliRunner().invoke(
        cli.app,
        ["analyze", "零售公司预算3万，两周上线，需要客户管理"],
    )
    assert result.exit_code == 0
    assert '"status": "completed"' in result.stdout
    assert '"product_id": "crm-starter"' in result.stdout


def test_cli_show_unknown_conversation_exits_nonzero(monkeypatch, service: AnalysisService) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "_service", lambda: service)
    result = CliRunner().invoke(
        cli.app,
        ["show", "f9fb9ff3-12b4-48a1-bd9c-e4b1df0696ee"],
    )
    assert result.exit_code == 1
    assert "会话不存在" in result.output
