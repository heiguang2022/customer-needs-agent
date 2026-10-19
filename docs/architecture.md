# 架构说明

本文回答三个问题：系统由哪些部分组成、一次请求如何流动、哪些决定交给模型而哪些必须由程序控制。

## 系统上下文

```mermaid
flowchart TB
    User[咨询用户]
    Developer[开发者 / 运维]
    System[客户需求分析 Agent]
    SF[硅基流动 Chat Completions]
    DB[(SQLite)]
    Catalog[(本地产品 JSON)]

    User -->|HTTP 或 CLI| System
    Developer -->|环境变量和产品目录| System
    System -->|结构化输出与工具调用| SF
    System -->|会话、消息、轨迹| DB
    System -->|只读查询| Catalog
```

硅基流动只参与自然语言理解、工具参数生成和推荐理由撰写。产品是否存在、价格是否超预算、交付期是否满足等事实由本地代码判断。

## 模块与依赖方向

```mermaid
flowchart TD
    API[api.py / FastAPI] --> Service[service.py / AnalysisService]
    CLI[cli.py / Typer] --> Service
    Service --> Agent[agent.py / CustomerNeedsAgent]
    Service --> Repo[repository.py / ConversationRepository]
    Agent --> Protocol[llm.py / LLMClient Protocol]
    Agent --> Tool[product_tool.py]
    Agent --> Models[models.py]
    Protocol --> Silicon[SiliconFlowClient]
    Tool --> Catalog[catalog.py + products.json]
    Repo --> SQLite[(SQLite)]
```

依赖只向内指向应用服务和领域逻辑。`CustomerNeedsAgent` 不导入 FastAPI、Typer 或 SQLAlchemy，因此可以单独测试，也可以复用于未来的网页或企业微信入口。

## 完整请求时序

```mermaid
sequenceDiagram
    actor U as 用户
    participant E as API / CLI
    participant S as AnalysisService
    participant R as SQLite Repository
    participant A as Agent
    participant L as 硅基流动
    participant T as query_products

    U->>E: 输入自然语言需求
    E->>S: AnalysisRequest
    S->>R: 创建或恢复会话
    S->>R: 保存 user 消息
    S->>A: history + previous requirements
    A->>L: 结构化提取需求
    L-->>A: RequirementExtraction JSON
    alt 缺少必填信息
        A-->>S: needs_clarification
    else 信息完整
        A->>L: 要求生成 query_products 调用
        L-->>A: 类型化工具参数
        A->>T: Pydantic 校验后的参数
        T-->>A: 目录匹配结果
        alt 无匹配产品
            A-->>S: failed / NO_MATCH
        else 存在候选产品
            A->>L: 候选产品 + JSON Schema
            L-->>A: 推荐草稿
            A->>A: 用目录事实覆盖名称、价格和限制
            A-->>S: completed
        end
    end
    S->>R: 保存状态、响应和工具轨迹
    S-->>E: AnalysisResponse
    E-->>U: 固定 JSON
```

## Agent 状态图

```mermaid
stateDiagram-v2
    [*] --> Extracting
    Extracting --> NeedsClarification: 缺少业务类型/预算/紧急程度
    NeedsClarification --> Extracting: 用户补充并复用 conversation_id
    Extracting --> BuildingToolCall: 信息完整
    BuildingToolCall --> QueryingCatalog: 参数校验成功
    QueryingCatalog --> Failed: 没有满足硬约束的产品
    QueryingCatalog --> Composing: 找到候选产品
    Composing --> Completed: 输出通过校验
    Extracting --> Failed: 模型或 Schema 错误
    BuildingToolCall --> Failed: 工具参数错误
    Composing --> Failed: 修复后仍不合法
```

状态不是只存在于模型上下文中。`requirements_json` 和最终响应保存于 SQLite，因此进程重启后仍可继续会话。

## 数据流和边界

```text
自然语言
  → RequirementExtraction（Pydantic 校验）
  → Requirements（程序检查必填字段）
  → QueryProductsArgs（Pydantic 校验）
  → ProductMatch（确定性工具生成）
  → RecommendationDraft（Pydantic 校验）
  → Recommendation（目录事实回填）
  → AnalysisResponse（跨字段不变量校验）
```

### 交给模型的决定

- 从口语中识别行业、预算、紧急程度和能力需求。
- 信息不足时生成自然的追问。
- 把完整需求转换成工具参数。
- 在已知候选产品范围内撰写匹配理由。

### 由程序强制执行的规则

- 哪些字段是必填项。
- 工具参数的类型、范围和枚举值。
- 预算、行业和交付周期硬约束。
- 产品只能来自本地目录。
- 产品名称、价格和限制以目录为准。
- 状态与响应字段必须一致。
- 循环步数、格式修复次数和错误暴露范围。

这种混合架构比“让模型直接看目录然后自由推荐”更容易测试、审计和解释。

## 失败隔离

- 模型供应商错误被转换为稳定的业务错误码。
- 429、500、503、504标记为可重试；认证和参数错误不标记为可重试。
- 无匹配产品返回 `NO_MATCH`，不降低硬约束来凑答案。
- Pydantic 拒绝额外字段和非法枚举。
- Agent 最多执行配置指定的步骤数，结构化输出仅修复一次。
- 日志只保存请求标识和运行元数据，不保存 API Key。

