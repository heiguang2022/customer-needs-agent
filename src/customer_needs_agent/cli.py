"""Typer 命令行入口。"""

from __future__ import annotations

import json
from uuid import UUID

import typer
from pydantic import BaseModel

from customer_needs_agent.bootstrap import build_service
from customer_needs_agent.config import get_settings
from customer_needs_agent.logging_config import configure_logging
from customer_needs_agent.models import AnalysisRequest
from customer_needs_agent.repository import ConversationNotFoundError
from customer_needs_agent.service import AnalysisService

app = typer.Typer(help="客户需求分析 Agent 命令行。", no_args_is_help=True)


def _service() -> AnalysisService:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file)
    return build_service(settings)


def _print_json(payload: object) -> None:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def analyze(message: str) -> None:
    """分析一条需求；需要追问时返回 conversation_id。"""

    response = _service().analyze(AnalysisRequest(message=message))
    _print_json(response)


@app.command()
def chat() -> None:
    """启动可持续追问的交互会话。"""

    service = _service()
    conversation_id: UUID | None = None
    typer.echo("请输入企业软件需求；输入 exit 结束。")
    while True:
        message = typer.prompt("你")
        if message.strip().casefold() in {"exit", "quit", "退出"}:
            break
        response = service.analyze(
            AnalysisRequest(message=message, conversation_id=conversation_id)
        )
        conversation_id = response.conversation_id
        _print_json(response)


@app.command()
def show(conversation_id: UUID) -> None:
    """查看已保存的会话、消息和工具轨迹。"""

    try:
        _print_json(_service().get_conversation(conversation_id))
    except ConversationNotFoundError:
        typer.echo("指定的会话不存在。", err=True)
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
