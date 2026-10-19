# 测试策略

## 为什么默认不调用真实模型

在线模型输出会变化，还会受限流、费用和网络影响。默认测试使用实现相同 `LLMClient` 协议的确定性替身，验证的是我们真正能控制的部分：状态转换、工具参数、硬约束、事实回填和错误契约。

真实接口只做人工冒烟测试，用来确认所选模型当前支持 Tool Calling 和 Structured Outputs。

## 测试层次

- `test_models.py`：字段和跨字段不变量。
- `test_product_tool.py`：预算、交付、能力和稳定排序。
- `test_agent_acceptance.py`：20 条输入和模型失败。
- `test_service_and_api.py`：SQLite 多轮恢复、工具轨迹、HTTP 接口。
- `test_cli.py`：CLI JSON 输出和退出码。
- `test_docs.py`：必需文档及内部链接目标。

## 20 条验收输入

验收矩阵包含：

- 6 条完整正常需求。
- 5 条缺少行业、预算、紧急程度或多个字段的需求。
- 3 条状态合并相关输入，其中一条通过服务层执行真实多轮恢复。
- 2 条小数预算或口语预算输入。
- 2 条预算或交付约束导致无匹配的输入。
- 2 条模型临时失败输入。

每条响应都会重新通过 `AnalysisResponse` 验证。测试还故意让模型替身返回错误产品名称和价格，确认 Agent 会用目录事实覆盖它们。

## 运行方式

```bash
uv run pytest
uv run pytest tests/test_agent_acceptance.py
uv run pytest tests/test_service_and_api.py::test_multi_turn_conversation_is_persisted
```

失败时加 `-vv` 查看具体参数；日志默认写入 `logs/agent.jsonl`，但测试会将 API 日志放入临时目录。

## 人工在线冒烟步骤

1. 配置真实密钥和支持所需能力的模型 ID。
2. 启动 API 并确认 `/health` 为 `ok`。
3. 提交一条缺少预算的需求，确认没有工具轨迹。
4. 使用同一个 `conversation_id` 补充预算和上线周期。
5. 确认状态为 `completed`，产品存在于目录，查询历史包含一次工具调用。
6. 查看日志，确认不包含 API Key 和供应商堆栈。

