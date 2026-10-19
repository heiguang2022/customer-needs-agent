# Agent Loop 与工具调用

## System Prompt 的组成

System Prompt 位于 `src/customer_needs_agent/prompts.py`，分为四部分：

1. **角色**：企业软件需求分析助手。
2. **任务**：提取需求、追问、调用查询工具、解释候选产品。
3. **边界**：不能猜测、不能虚构产品、不能替客户作采购承诺。
4. **完成条件**：需求完整、工具成功调用、最终输出符合 Schema。

它是给模型的行为说明，不是唯一安全边界。真正的产品白名单、预算过滤和状态校验均由 Python 执行。

## 每一轮使用的状态

Agent 接收：

- `conversation_id`：会话标识。
- `history`：按顺序保存的用户和助手消息。
- `previous`：上一轮已经确认的结构化需求。

模型必须返回合并后的完整需求，而不是只返回本轮新增字段。这使得持久化状态明确可见，也便于审计。

## 循环阶段

| 阶段 | 模型做什么 | 程序做什么 |
|---|---|---|
| Extract | 理解完整对话 | 用 `RequirementExtraction` 校验 |
| Clarify | 生成一个追问 | 判断必填字段并阻止工具调用 |
| Tool call | 生成查询参数 | 校验 `QueryProductsArgs` 并执行工具 |
| Compose | 撰写匹配理由 | 回填目录事实并校验最终响应 |

`max_agent_steps` 默认是 4。当前正常完成路径使用三个阶段，保留一个恢复空间。

## Tool Calling 消息形态

提供给模型的工具定义来自 `QueryProductsArgs.model_json_schema()`：

```json
{
  "type": "function",
  "function": {
    "name": "query_products",
    "description": "根据已确认的客户需求查询本地企业软件产品目录。",
    "parameters": {
      "type": "object",
      "properties": {
        "business_type": {"type": "string"},
        "budget_max": {"type": "number"},
        "urgency": {"enum": ["low", "medium", "high", "critical"]},
        "required_capabilities": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["business_type", "budget_max", "urgency"]
    }
  }
}
```

运行时强制选择 `query_products`，但仍由模型根据自然语言生成参数。收到参数后必须再次经过 Pydantic；JSON 格式正确不代表业务上可接受。

## 结构化输出与修复

需求提取和推荐草稿使用 `response_format.type=json_schema`。处理顺序是：

1. 生成 Pydantic JSON Schema。
2. 将 Schema 发送给模型。
3. 用 `model_validate_json` 验证响应。
4. 如果失败，附上原响应并要求只返回修正后的 JSON。
5. 第二次仍失败则返回 `INVALID_MODEL_OUTPUT`。

修复只有一次，防止错误模型或不兼容模型导致无限重试。

## 终止和错误

- 缺少必填信息：`needs_clarification`。
- 推荐成功：`completed`。
- 无匹配产品：`failed / NO_MATCH`。
- 模型暂时不可用：`failed / LLM_TEMPORARY_ERROR`，`retryable=true`。
- 工具参数无效：`failed / INVALID_TOOL_ARGUMENTS`。
- 超过步骤：`failed / AGENT_STEP_LIMIT`。

以上失败都会保存到会话中，用户可以查询轨迹；供应商堆栈不会返回给调用者。

