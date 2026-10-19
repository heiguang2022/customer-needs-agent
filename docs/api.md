# HTTP API

启动服务：

```bash
uv run uvicorn customer_needs_agent.api:create_app --factory --reload
```

Swagger UI 位于 `/docs`，OpenAPI JSON 位于 `/openapi.json`。

## POST /v1/analyses

创建或继续一次分析。

```json
{
  "message": "零售企业需要客户管理，预算 3 万，希望两周上线",
  "conversation_id": null
}
```

`conversation_id` 省略或为 `null` 时创建新会话；继续回答追问时传回服务端返回的 UUID。

成功推荐示例：

```json
{
  "conversation_id": "93b985f0-79c4-45bd-a295-faa5347aa590",
  "status": "completed",
  "requirements": {
    "business_type": "零售",
    "budget": {"min": null, "max": 30000, "currency": "CNY"},
    "urgency": "high",
    "needs": ["客户管理"]
  },
  "clarification_question": null,
  "recommendations": [
    {
      "product_id": "crm-starter",
      "name": "启航 CRM",
      "estimated_price": 18000,
      "fit_reasons": ["覆盖客户管理需求", "可在两周内交付"],
      "limitations": ["不含复杂渠道管理", "标准版仅支持 30 个账号"]
    }
  ],
  "error": null
}
```

## GET /v1/conversations/{id}

返回当前结构化需求、全部消息、工具参数、工具结果和最后一次响应。未知 UUID 返回 HTTP 404。

## GET /health

返回数据库与模型配置状态：

```json
{
  "status": "ok",
  "database": "ok",
  "llm_configured": true
}
```

缺少模型配置时应用仍可启动，状态为 `degraded`；分析接口会返回固定的 `LLM_NOT_CONFIGURED` 业务错误。

## HTTP 状态和业务错误

- 200：请求已被正常处理，包括需要追问或业务级失败。
- 404：指定会话不存在。
- 422：请求体或 UUID 不符合 API Schema。
- 500：未被业务层捕获的程序错误。

业务错误通过响应中的 `error.code` 表达。调用方只应在 `retryable=true` 时自动重试，并使用有限退避。

