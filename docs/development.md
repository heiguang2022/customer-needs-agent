# 开发与扩展

## 本地开发

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy src
```

配置复制自 `.env.example`。不要提交真实 `.env`、SQLite 文件或日志目录。

## 模块职责

- `models.py`：跨模块数据契约和业务不变量。
- `agent.py`：流程编排，不包含 HTTP 或数据库细节。
- `llm.py`：模型协议、供应商调用和格式修复。
- `product_tool.py`：纯函数形式的筛选评分。
- `repository.py`：SQLAlchemy 表和会话仓储。
- `service.py`：事务边界外的应用用例。
- `api.py` / `cli.py`：薄入口层。

新增行为时优先放到最内层可测试模块，不要在 API 路由中编写业务规则。

## 新增产品字段

1. 修改 `Product` Pydantic 模型。
2. 更新全部产品 JSON。
3. 根据业务需要调整 `query_products`。
4. 更新 `docs/data-model.md` 和相关测试。

目录会整体验证，任何漏填字段都会立即失败，而不是在某次查询中偶发出错。

## 新增工具

1. 为参数和结果定义独立 Pydantic 模型。
2. 实现不依赖模型的确定性函数。
3. 在 `LLMClient` 协议中暴露模型决策能力。
4. 在 Agent 中验证参数、执行工具并记录轨迹。
5. 为成功、参数错误、空结果和执行异常编写测试。

不要提供“执行任意 SQL”或“执行任意命令”之类权限过大的工具。

## 替换模型提供商

实现 `LLMClient` 的三个方法即可。Agent 不关心 SDK 和供应商。新实现必须支持或模拟：

- 基于 JSON Schema 的结构化需求提取。
- 函数工具调用。
- 结构化推荐输出。
- 稳定、脱敏的错误分类。

## 常见问题

### 健康检查显示 degraded

检查 `.env` 中是否同时设置 `SILICONFLOW_API_KEY` 和 `SILICONFLOW_MODEL`。

### 模型没有调用工具

确认模型本身支持 Tool Calling。项目已强制 `tool_choice=query_products`；不兼容模型会返回 `TOOL_CALL_MISSING` 或供应商错误。

### 结构化输出持续失败

确认模型支持 `response_format=json_schema`。项目只修复一次，避免无限调用和不可控费用。

### 产品明明存在却没有匹配

依次检查预算上限、紧急程度映射的交付天数、行业和能力关键词。工具是确定性的，可直接运行 `tests/test_product_tool.py` 定位。

