# Meeting Memory System

> An AI-powered Long-term Memory System for Project Collaboration

基于 DeepSeek、SQLite 与 Streamlit 构建的会议长期记忆系统，通过 Human-in-the-loop、Memory Citation 与 Memory Impact Proof，实现项目知识沉淀、跨会议引用与长期价值验证。

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red)
![SQLite](https://img.shields.io/badge/SQLite-Database-green)
![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-purple)

## 1. 项目简介

Meeting Memory System（会议长期记忆系统）是一个面向项目协作场景的会议知识系统，用 DeepSeek API、SQLite 和 Streamlit 实现会议摘要生成、长期记忆提取、人工审核、跨会议引用和效果验证。

它不是单次会议纪要工具，而是围绕“项目长期记忆”构建的 AI Agent MVP：系统会从会议中提炼候选记忆，经人工确认后进入长期记忆库，并在后续会议中被注入、引用和验证。

## Highlights

- Human-in-the-loop 双层记忆审核机制
- Memory Citation 引用链路追踪
- Memory Impact Proof 记忆价值验证
- Reference Count 高频知识统计
- 长期记忆生命周期管理
- SQLite 本地知识存储

## 2. 项目背景与痛点

传统会议纪要工具通常只关注单次会议总结，能够回答“这次会议讲了什么”，但很难持续回答“这个项目过去做过什么决定、有哪些约束、哪些风险还没解决”。

在长期项目协作中，历史决策、需求变化、风险信号和待办事项很容易散落在多次会议记录里。随着会议数量增加，团队会反复讨论同类问题，或者遗忘之前已经确认过的上下文。这个项目尝试把会议内容转化为可沉淀、可审核、可引用、可验证的项目长期记忆。

## 3. 核心产品闭环

核心流程如下：

```text
会议输入
  -> DeepSeek 生成摘要与候选记忆
  -> Human-in-the-loop 审核
  -> Confirmed Memory 入库
  -> 后续会议注入历史记忆
  -> Memory Citation / Reference Count / Memory Impact Proof 验证记忆价值
```

这个闭环的重点不只是“生成内容”，而是让 AI 生成的知识经过人工确认、持续复用，并通过引用标记和对照生成证明其价值。

## 4. 系统架构

```mermaid
flowchart TD
    A["User Input"] --> B["DeepSeek Client"]
    B --> C["Meeting Summary"]
    B --> D["Candidate Memory"]
    D --> E["Human Review"]
    E --> F["Confirmed Memory"]
    C --> I["SQLite Storage"]
    F --> I
    I --> G["Memory Injection"]
    G --> B
    B --> H["Memory Citation"]
    H --> J["Reference Count"]
    C --> K["Memory Impact Proof"]
    J --> I
```

## 5. 核心功能

### 5.1 Human-in-the-loop 审核流

系统区分 Candidate Memory 和 Confirmed Memory。DeepSeek 或 Mock fallback 只能生成候选记忆，不能直接写入长期记忆库。

用户可以对候选记忆进行确认、合并或拒绝。这个设计把大模型输出放在“待审核层”，降低幻觉、低价值信息和重复内容污染长期知识库的风险。

### 5.2 Memory Citation

系统在生成会议摘要时会注入已确认的历史记忆，并要求模型在使用某条历史记忆时，通过 `[MEMORY_ID]` 标记引用来源。

例如摘要中出现 `[MEMORY_8]`，就表示该句内容受 memory_id 为 8 的长期记忆影响。这个机制让模型输出不只是“看起来合理”，而是可以追溯到具体历史知识。

### 5.3 Memory Impact Proof

系统支持对照验证：同一份会议内容会形成“无历史记忆版本摘要”和“有历史记忆版本摘要”。

通过对比两种结果，系统可以展示历史记忆是否真正影响了模型输出，并统计引用历史记忆数量、新增关键词数量，以及是否出现 Memory Citation。这是对长期记忆模块价值的一种轻量验证。

### 5.4 Reference Count

当摘要中出现 `[MEMORY_ID]` 引用标记时，系统会解析被引用的 memory_id，并在当前会话中统计对应长期记忆的引用次数。

项目记忆页可以按引用次数排序，用于识别被频繁复用的高价值知识资产。引用次数较高的记忆会被标记为“核心资产”。

### 5.5 低价值记忆过滤与历史垃圾扫描

系统在候选记忆入库前会过滤低价值内容，例如“暂无历史记忆”“无内容”“待补充”“测试会议”“DS_PROBE”等无信息量或测试性质文本。

同时，项目记忆页提供历史垃圾记忆扫描能力，可以扫描已确认长期记忆中的疑似低价值内容，并允许用户人工删除，避免 Memory Layer 被持续污染。

### 5.6 待办事项追踪

系统可以从会议内容和候选记忆中提取行动项，并保存到待办中心。

待办事项支持状态管理，包括 open、doing、done 和 overdue，用于把会议中的后续行动从文本记录转化为可跟踪任务。

## 6. 技术栈

- Python
- Streamlit
- SQLite
- DeepSeek API
- JSON Schema / Fallback / Session State

## 7. 项目亮点

- 不是单次会议总结，而是跨会议长期记忆系统
- 引入 Human-in-the-loop 控制大模型幻觉风险
- 用 Memory Citation 提高可解释性和可追溯性
- 用 Memory Impact Proof 验证记忆模块价值

## 8. Demo 截图

### 8.1 Dashboard

Dashboard 展示项目整体状态、长期记忆规模、候选记忆数量和最近会议情况。它用于快速判断当前项目知识沉淀是否健康，以及 Agent 最近是否发生了有效的记忆引用。

![Dashboard](docs/images/dashboard.png)

---

### 8.2 Long-term Memory Store

Long-term Memory Store 展示已确认长期记忆的存储、分类管理、搜索与治理能力。用户可以查看不同类型的项目记忆，并通过引用次数识别高价值知识资产。

![Long-term Memory Store](docs/images/project_memory.png)

---

### 8.3 Explainable Memory Retrieval

Explainable Memory Retrieval 展示 Agent 在会议开始前如何检索历史记忆，并给出每条记忆被选中的原因。页面会展示类型权重、历史引用次数、时间衰减等解释信息，让记忆注入过程可追踪。

![Explainable Memory Retrieval](docs/images/new_meeting_memory_retrieval.png)

---

### 8.4 Meeting Detail with Memory Citation

Meeting Detail with Memory Citation 展示历史记忆如何被注入当前会议，并通过 `[MEMORY_ID]` 影响最终摘要。该页面用于证明系统不是简单总结会议，而是在复用长期项目知识。

![Meeting Detail with Memory Citation](docs/images/meeting_detail.png)

---

### 8.5 Agent Execution Trace

Agent Execution Trace 展示完整工作流：Memory Retrieval → Memory Injection → Summary Generation → Action Extraction → Citation Tracking → Conflict Detection。它让用户和面试官能够看到 Agent 在一次会议生成过程中具体做了哪些决策和动作。

![Agent Execution Trace](docs/images/agent_execution_trace.png)

---

### 8.6 Action Item Tracking

Action Item Tracking 展示系统如何从会议中自动抽取待办事项，并在待办中心进行状态管理。它补充了会议长期记忆之外的执行跟踪能力。

![Action Item Tracking](docs/images/action_center.png)

---

### 8.7 Evaluation Dashboard

Evaluation Dashboard 展示长期记忆系统的引用率、候选记忆通过率、冲突检测率和影响验证覆盖率。它用于从产品评估角度证明长期记忆是否被使用、是否形成闭环，以及是否产生业务价值。

![Evaluation Dashboard](docs/images/evaluation_dashboard.png)

## 9. Demo Scenario

项目名称：AI会议知识助手

演示数据：

- 5 场会议
- 15 条长期记忆
- 11 条待办事项

已验证能力：

- 长期记忆沉淀
- 跨会议知识引用
- Memory Citation
- Human-in-the-loop
- Reference Count
- 生命周期管理

## 10. 如何运行

```bash
pip install -r requirements.txt
python scripts/init_db.py
python -m streamlit run app.py
```

首次启动会初始化本地 SQLite 数据库文件 `data/meeting_memory.db`。

如需使用 DeepSeek 真实生成链路，请在项目根目录创建 `.env` 并配置：

```bash
DEEPSEEK_API_KEY=your_api_key_here
```

未配置 API Key 或 DeepSeek 调用失败时，系统会自动回退到 Mock fallback，保证 MVP 可以继续运行。

## 11. 当前边界与 Roadmap

当前边界：

- 当前为 MVP 原型
- 当前主要使用 SQLite 和 Streamlit
- 当前未接入向量数据库，记忆规模扩大后计划接入 Top-K 语义召回
- 当前无多人协作与权限系统

后续规划：

- 向量检索 / Top-K Memory Retrieval
- 冲突记忆检测
- 主动召回提醒
- 更完整的评估指标体系

## Product Thinking

传统会议纪要工具解决的是“记录问题”。

Meeting Memory System 试图解决的是“知识遗忘问题”。

随着项目周期拉长，决策、约束、需求、风险和行动项会散落在多次会议中。团队成员往往需要反复检索历史记录，甚至重复讨论已经达成共识的问题。

因此，本项目尝试将会议内容沉淀为长期记忆资产，并通过 Human-in-the-loop、Memory Citation 与 Memory Impact Proof 构建“生成—审核—沉淀—引用—验证”的知识闭环。

目标不是生成一次会议纪要，而是帮助团队持续积累和复用项目知识。
