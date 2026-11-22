# Conversation Agent V1：受约束 ReAct 架构与工具合同

> 版本：v1.2（2026-11-22，PR #2 工程审查修订）；状态：**设计规范，Agent 业务代码尚未实现**。  
> GitHub：GB412/bearing_agent_system，设计 PR #2；PR-00 #1 仍在评审。  
> 依据：[项目总控](../00_MASTER_PLAN.md) · [动态交互验收](CONVERSATION_AGENT_V1_ACCEPTANCE.md) · [RoBAS PR-00 审计](../pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md) · [DGBDesignBrief/v1 字段合同](DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md) · [324 字段矩阵](../parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)。  
> 本文件**替代**原有「interpret → validate → assess → choose_next_action → compose」固定流程及旧五动作路由，不新增平行架构。

## 0. 项目负责人：一页看懂 V1

**目标**：通过一个 Conversation Agent 与用户多轮对话，获取、澄清、解释、推荐和确认深沟球轴承（DGB）的设计需求，生成版本化的 `DGBDesignBrief/v1`，供未来五变量优化及 RoBAS 拟静力学输入适配使用。

**架构**：一个自主决策的 Conversation Agent，最多暴露 **5 个工具**。模型自主决定「问什么、怎么问、何时查知识、何时推荐、是否继续调用工具」；确定性程序决定「什么值能写入、来源是否可信、哪些字段缺失、方案是否符合审核规则、何时可宣称交付完成」。不用 Supervisor、多专业 Agent、复杂通用规则引擎。

**工具**：
1. `update_design_brief`：唯一受信写入，保存/修改用户明确提供的参数或接受已展示的推荐。
2. `get_design_status`：**简单状态查询**，只读当前已知、缺失、待确认、冲突；**不替模型决定提问顺序**。
3. `lookup_engineering_knowledge`：查询专业解释依据、型号/材料/润滑/游隙/配合资料；区分模型一般知识与可追溯的工程数值。
4. `recommend_engineering_config`：读取当前受信设计任务，按经审核的工程规则筛选材料/保持架、润滑或游隙/配合组合，生成**待确认提案**。
5. `finalize_design_brief`：检查用户层需求是否完整和一致，并返回/导出版本化 DesignBrief、未决项及交付状态。

**不设置**：独立 `confirm_recommendation`（并入工具①）、`check_solver_compatibility`（用户决定 V1 暂不设）、`question_planner`、独立搜索 Agent、求解器运行工具和 CAD 工具。

**本阶段不做**：Dw/Z/Dpw/fi/fo 的优化、RoBAS EXE 求解、CAD、多轴承类型、多工况设计、自动工程批准。PR-00 已记录 43 条 DATA / 324 字段，但工程协议冻结仍 **BLOCKED**。

## 1. 需求范围、字段合同和阶段准入

用户层参数不是一张任意可增字段的 JSON。**PR-01 先冻结 [DGBDesignBrief/v1 字段合同](DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md)**，它是工具①的字段/类型白名单、工具②的缺项依据和工具⑤的需求层完整性依据；RoBAS 43/324 是**不同层级**的协议目录，不能混用。

| 类别 | 典型字段 | 当前规则 |
|---|---|---|
| 固定设计边界 | d、D、B；内外圈 rpm；单轴承 Fr/Fa；假定工作温度 | 需要明确语义、单位、来源；范围/估计不得静默当固定值 |
| 用户选择的工程配置 | 内外圈/钢球/保持架材料、保持架类型、润滑、初始游隙、内外圈配合 | 用户直接指定或接受审核推荐；数据来源可靠性与用户接受分开 |
| 条件项 | 轴/座尺寸、力矩/错位、方向、特殊装配 | 由条件性规则判断是否需要，不将全部底层字段做用户问卷 |
| 用户目标和限制 | 最低寿命、功耗偏好、D 的上限等 | 以结构化约束/偏好记录，不假装已成为优化器可计算指标 |
| 五个优化槽 | Dw、Z、Dpw、fi、fo | 默认 `optimize/null`，允许用户设置上下限或锁定值 |
| 工程数据/求解器配置 | 材料物性、派生几何、Solver profile | 由未来可信数据源/审核映射提供，不混成用户事实 |

**参数目录必须可执行，而不只是自然语言列表**：每个字段定义 canonical path、类型、单位、R 必需 / C 条件必需 / O 可选 / OPT 优化 / SYS 系统、可接受的值形状、跨字段检查，以及用户层 `brief_complete` 判定条件。V1 的条件判断用简单函数，没必要建立复杂规则引擎。

例如 `D≤52 mm` 应进入 `requirements.geometric_bounds[]`，不能把 `dimensions.D_mm` 写成已确定的 52；`CN/C3` 游隙组是区间，不得擅自视作唯一初始/工作游隙值。`operating.temperature_c` 明确是选定的分析工作温度，不能直接由环境温度替代。

PR-00 工程审计未冻结的事项仍阻断后续真实 RoBAS 模板就绪，但**不阻断单纯的用户层字段模型和对话能力开发（须经项目负责人批准 PR）**。

## 2. 系统架构

```text
用户消息 + session_id
       │
       ▼
Conversation API ──► 加载当前 DesignBrief / 提案 / 精简状态摘要
       │
       ▼
Conversation Agent（一个 LLM，ReAct 决策循环）
       ├── tool① update_design_brief ─────┐
       ├── tool② get_design_status ───────┤
       ├── tool③ lookup_engineering_knowledge
       ├── tool④ recommend_engineering_config
       └── tool⑤ finalize_design_brief ──┤
       ▲                                 │
       └──── 工具结果 / 新状态摘要 ◄──────┘
       │
       └── 决定回复用户 → 保存回合记录 → END
```

**背后的普通服务，不额外包装为 Agent：**
- `DesignBriefStore`：单一受信写入、版本/幂等、用户证据核实、用户已确认值与推荐提案分开管理；
- `RequirementChecker`：按 V1 参数目录、条件必需项和基本约束生成简洁状态及缺项；
- `KnowledgeRepository`：结构化型号/材料/润滑/规则/审核配置，只读版本化数据；
- `RecommendationService`：规则筛选、适用性检查、提案建立；
- `FinalizationService`：需求完成性和交付版本检查；
- `RoBASAdapter`：**PR-06 后续实现**，不纳入当前 ReAct 工具五的判定责任。

建议 Python 3.11+、Pydantic、单进程、SQLite 存业务数据，LLM 支持 tool calling。编排用最小 LangGraph/等价原生 agent loop；选库前锁定实际依赖版本，不为了 ReAct 名称而新增 Supervisor、自定义 planning graph 或多个状态副本。

## 3. 每轮 ReAct 自主工具循环与安全收尾

```text
START / 收到一条用户消息（turn_id、client_expected_revision）
  ↓
加载受信 DesignBrief、会话、有效提案、精简需求状态
  ↓
Conversation Agent（LLM）
  ├─ 选择一个或多个工具 → guarded_tools 校验、执行、刷新状态
  │                              ↓
  │                         工具结果返回 LLM
  │                              └────→ 同一 Agent 再次自主决策
  └─ 回复用户/提问 → finalize_response 校验 → 保存回合 → END
```

**ReAct 负责**自主选择提问、解释、知识查询、工程推荐、记录用户事实或请求交付。**程序负责**工具调用的许可、受信写入、数据完整性、幂等、必要状态刷新和最终回复真实性；不是固定问卷，也不设置独立 Planning Agent。

**预算与终止**：建议首版每轮约 5–6 次业务工具调用上限（配置项，不是必须用完）、模型调用次数上限、重复调用检测和工具超时。已能回答、需要用户补充或确认、资料不可信、工具失败或预算耗尽时应回复并结束本轮。不能通过不断查询解决用户没有提供的载荷等信息。

**最小调用原则**：同一消息的多个明确参数优先一次批量工具①调用。工具①写入后自动返回最新需求摘要；通常不必再调用工具②。工具④内部从受信状态和知识仓检索，不强迫 LLM 先调用工具③。工具⑤用于用户要求检查/交付或需求汇总，不能在每轮无理由调用。

**写入顺序**：写入与依赖本次写入的查询/推荐串行；只读请求仅在同一业务 revision 且相互独立时才可并行。模型不可在旧 revision 上推荐新工况，也不能忽略版本冲突后宣称成功。

### 3.1 三类 ID：解决 ReAct 单轮多次写入冲突（PR-01 必须实现）

| 标识 | 来源/含义 | 使用方式 |
|---|---|---|
| `turn_id`（或 API `request_id`） | 服务端记录的一条用户消息 | 整轮去重和恢复，不得直接把它当成“一轮只允许一次业务写入”的键 |
| `tool_call_id` / 规范化 `operation_key` | 当前轮内一次具体工具操作 | 操作级幂等：相同逻辑操作的重试只执行一次，**同一轮不同操作均允许执行** |
| `brief_revision` | DesignBrief 已提交快照版本 | 每次有效原子变更递增；后续调用从实际最新版本读取/校验 |

工具调用的操作键应由服务端结合 `session/turn`、操作类型、规范化 payload（含 proposal、接受范围）计算或登记。不能仅用整轮 `request_id` 去重每次写入，也不能只信模型自报的 `tool_call_id`。重放相同操作返回上次结果；对同一字段重复提交同样数值应为无变更；有冲突/不同值时要求重新检查，不悄悄覆盖。

客户端 `expected_revision` 用于新用户轮次的并发校验；一轮内部第一次写入后，后续受信调用使用**服务端已经提交的最新 revision**，并再次检查是否有外部并发修改。若有竞争性修改，拒绝过期写入并刷新上下文，不能静默重试覆盖他人变更。

### 3.2 防漏提取与回复一致性

**模型可直接回复普通概念问题，但不得只用一句“已记录”代替必要的工具①写入。** 凡当前用户消息明确提供/修订/接受设计参数，应先提出受信更新工具调用。对同轮多字段优先批量写入，工具拒绝字段时必须如实反馈。

`finalize_response` 是普通确定性收尾函数，至少校验：回复声称“已保存/已确认”的字段在本轮真实成功工具操作或当前状态中有依据；“需求已完成”必须有工具⑤的检查结果；“RoBAS 输入可计算”不能源自工具⑤。模型不能用自然语言推翻工具错误结果。

但**只核对工具记录不能证明模型没有漏识别原话中的参数**。PR-02 应安排有人工标注的多字段抽取测试；如果漏提取显著，可以先增加轻量的数值/字段候选扫描与“可能未处理”提醒（不是第二个 Agent，也不替代 LLM 语义解释），而不是立即增加第二次模型调用。

`tool_trace_summary` 记录调用名、操作键、变更摘要、错误原因、来源、耗时与次数，不记录私有推理过程或把旧对话历史当业务事实。

## 4. 五个工具：输入输出、权限、失败条件

### 4.1 工具① `update_design_brief`（唯一受信写入）

它是**一个工具、四类操作**，不能再创建独立确认工具：

| operation | 场景 | 写入内容 |
|---|---|---|
| `set` | 用户提供原先未知的参数 | 一个或多个合法字段与用户证据 |
| `replace` | 用户明确纠正/修改已知参数 | 对应字段更新、来源、依赖失效 |
| `accept_proposal` | 用户接受当前展示的材料/润滑等推荐 | 仅接受 `accepted_paths` 范围、当前有效的方案 |
| **`accept_brief`** | 用户明确接受已展示的整份需求摘要 | 对该 **revision/summary_id** 记录整体确认，不改变参数值 |

工具调用建议为**判别联合类型**，不是在一个宽松 JSON 中同时混用 `changes` 和 `proposal_id`：

```json
{
  "operation": "replace",
  "changes": [{"path":"operating.inner_speed_rpm","raw_value":"18000转","evidence_span":"内圈转速改为18000转"}]
}
```

```json
{
  "operation": "accept_proposal",
  "proposal_id": "materials-A",
  "accepted_paths": ["engineering.materials.inner_ring_id","engineering.materials.ball_id"]
}
```

```json
{
  "operation": "accept_brief",
  "brief_revision": 12,
  "summary_id": "summary-12-digest"
}
```

**来源保护**：真实 `session_id/turn_id/message_id`、用户原始消息、当前 revision、调用操作键由服务器注入或验证，不能相信 LLM 自填。模型不得设置 `confirmed=true`、伪造用户来源或替用户确认。原文片段存在不是充分授权；工具必须检查语义明确、数值/单位、适用范围和提案引用，不能仅靠字符串包含判断同意。

**整份确认保护**：`summary_id` 应关联工具⑤生成的指定版 **DesignBrief 内容摘要/哈希** 和实际已向用户展示的摘要记录；必须核对当前修订与用户当前明确接受表达。只说“确认”但有多个不同摘要候选时先澄清。调用 `accept_brief` 后若后续 revision 变化，整体确认自动不适用于新 revision。

**操作结果**：`applied_changes`、`rejected_changes`、`revision`、`invalidated_proposals`、`design_status`；`accept_brief` 另返回 `brief_user_accepted_revision`。无实际变更不必增 revision；同一轮可以先修改转速再接受不受其影响的提案，但需要两个独立、幂等的操作键；具体提案有效性按依赖快照检查，而非简单看全局 revision。

用户明确的近似值可保留 `precision=approximate, confirmed=false`；用户后续明确“就以 18000 rpm 作为本次分析假定值”时才能记录可用于固定工况的确定分析输入，并保存这一假设的用户依据。不要将近似观测当成已验证的物理真值。

### 4.2 工具② `get_design_status`（简单只读）

**职责只限于客观状态，不替模型规划问题。**

```json
{
  "known": {
    "dimensions.d_mm": 25,
    "dimensions.D_mm": 52,
    "dimensions.B_mm": 15,
    "operating.inner_speed_rpm": 18000,
    "operating.outer_speed_rpm": 0
  },
  "missing": [
    "operating.radial_load_n",
    "operating.axial_load_n",
    "operating.temperature_c",
    "engineering.materials",
    "engineering.lubrication",
    "engineering.clearance_and_fits"
  ],
  "pending_confirmation": [],
  "conflicts": []
}
```

这是**示例状态**，不表示 d/D/B 会自动从无来源型号中补出。字段可以附简单单位/不确定性/状态，不建立复杂的「责任归属、优先级打分、预生成问题列表、处理动作」系统。已确实标记为非适用的条件项不列为 `missing`；近似值、上限与确定值的区别不能被扁平化隐藏。

工具返回以后：
- **模型负责判断问哪一个、问几个、怎么用自然语言问**；
- 一般先处理用户当前意图，再关注关键工况和推荐前置条件，但**不是固定问卷**；
- 用户表示不知道材料时，可调用工具④或工具③，不重复问材料名；
- 对话历史帮助避免刚刚问过又马上重复；如果用户只想了解知识，先解释而不是强制继续填表；
- 模型不得仅因为“自己觉得不重要”便把 `missing` 从检查器中删掉。

工具①更新成功后已经附精简状态。用户单纯要求查看进度，或 LLM 真正需要刷新状态时，才主动调用工具②。

### 4.3 工具③ `lookup_engineering_knowledge`（只读知识）

建议输入 `{ "topic": "clearance | fit | bearing_model | material | lubrication | terminology", "query": "...", "context_revision": 8 }`。返回 `summary`、`facts[]`、`source_refs[]`、`applicability`、`limitations`、`evidence_level`，无结果明确 `NOT_FOUND/UNVERIFIED`。

知识来源按证据强度分层：
1. **模型内在知识**：理解用户问题、解释公认的通用概念、组织语言，不作为未经核验的具体材料物性/公差/标准数值来源；
2. **本地结构化数据**：RoBAS SQLite 型号与几何、CSV 材料/润滑（原始值均需质量核验）、有来源的标准表、人工审核配置；标识数据版本/哈希、单位、适用范围；
3. **可选外部检索**：当本地缺少来源、用户明确要求依据时，使用可信标准/厂家手册获取证据；**V1 不把联网搜索变成强制默认步骤**，网页内容仅为候选证据，未经审核不得成为可计算的系统配置。

V1 不建大规模 RAG；结构化数据 + 少量审核规则优先。用户问“CN 与 C3 的含义”可以根据已知知识先解释；问“本尺寸游隙具体数值范围”必须查可追溯依据。没有证据时直接告知，不填造数字。

### 4.4 工具④ `recommend_engineering_config`（筛选、建立提案）

建议输入：
```json
{"config_type":"materials_and_cage | lubrication | clearance_and_fits","design_revision":8}
```
工具**自己读取当前受信 DesignBrief**，不让模型重复传 d/D/B/转速等工况，以免传旧值。若 `design_revision` 不匹配当前版本，拒绝创建旧工况提案。

规则：检查推荐所需前提 → 查询有限的**已审核**候选组合 → 校验已知适用条件、来源及必要属性 → 形成少量备选 → 返回证据和限制。**工具内部使用工具③底层同一数据仓/规则，不要求模型另行先调工具③。**

返回：
```json
{
  "status": "PROPOSAL_READY",
  "proposal_id": "material-A",
  "design_revision": 8,
  "items": [{"path":"engineering.ring_material","value":"reviewed_material_id"}],
  "source_refs": ["reviewed-rule:..."],
  "depends_on": ["operating.inner_speed_rpm","operating.temperature_c"],
  "limitations": [],
  "review_status": "REVIEWED"
}
```
若缺少前置条件，则返回 `NEED_INPUT` 与缺哪些条件；无审核数据返回 `NO_VERIFIED_CONFIGURATION`；当前 RoBAS 模型兼容性尚未证明的候选**不得宣称可运行**。在 PR-04 不单独开发 `check_solver_compatibility` 工具：推荐适用性筛选只检查当前**有证据的**条件，底层模型未知保持 UNKNOWN，不假装已验证。

推荐是一个 **proposal**，不是 DesignBrief 中的用户已确认值。推荐可能同时包含材料、钢球、保持架材料；允许用户整套或部分接受。模型负责解释推荐，不得创造没有返回的工程数字或冒充“最优方案”。

### 4.5 工具⑤ `finalize_design_brief`（最终检查与导出）

输入：
```json
{"mode":"check | export","expected_revision":8}
```
`check` 不修改业务状态，只报告设计需求是否完整；`export` 导出**指定修订版本**的需求文档（完整或标记为草案）。若用户希望将整个 Brief 标记为「已确认」，必须已经明确看过当前摘要并接受**该版本**；这项证据在受信状态层验证，不能由模型以 `mode=export` 代替用户同意。

```json
{
  "revision": 8,
  "brief_complete": false,
  "missing": ["engineering.lubrication"],
  "unconfirmed": ["engineering.clearance_and_fits"],
  "conflicts": [],
  "can_export_draft": true,
  "can_export_complete": false,
  "deliverable": null,
  "robas_template_ready": "NOT_ASSESSED"
}
```

检查项：d/D/B、套圈转速、真实单轴承 Fr/Fa、分析温度；需要用户确认的材料/润滑/游隙和配合；条件项与自相矛盾参数；偏好与约束记录；来源和 revision；五优化槽保留为待优化或明确锁定。

**特别边界**：工具⑤是 **用户层需求完整性与交付检查**，不是当前就检查 RoBAS 324 字段的求解输入完整性。V1 暂不实现独立 Solver Compatibility 工具。未来 PR-06 的确定性 RoBASAdapter 有自己的协议 gate，只有那时经过审核才能产生 `TEMPLATE_READY`；工具⑤只能返回 `robas_template_ready: NOT_ASSESSED` 或后续接收适配器的独立结果，**不得因 brief_complete=true 自称 DATA 可运行**。

模式分支：用户随时能导出标记为 INCOMPLETE 的草案；只有 `brief_complete=true` 且没有阻断时才允许作为完成版需求导出。需要保存确认摘要、版本和生成文件/内容的可追溯 ID，不能从不匹配 revision 的旧内容导出。

## 5. Agent 如何决定「下一个问什么、怎么问」

这不设专门工具，也没有五动作硬路由。模型可根据：
- 当前用户明确意图：直接回答其问题、优先处理修改或推荐请求；
- `get_design_status.missing`：哪些**客观必需项**尚未明确；
- 当前 DesignBrief 的已知值与近似值、范围、冲突；
- 专业推荐的已知前置条件与工具返回的 `NEED_INPUT`；
- 会话历史：用户是否已回答、已表示不知道、暂不想回答；
- 交互负担：优先问 1–2 组相关问题，不每次逐项点名。

**模型有权决定提问的时机、对象和表达，但无权更改哪些字段是必要输入。** 不生成「优先级分数」「下一步动作计划」作为工具②职责。普通顺序可倾向：固定尺寸/型号 → 明确套圈转速 → Fr/Fa → 温度 → 推荐与确认工程配置；但可被用户意图打断，不得硬编码为固定问卷。

案例：已知 d/D/B、转速而 Fr/Fa 缺失，模型可询问“轴承实际承受的径向载荷与轴向载荷分别是多少？没有轴向载荷可以说明为零”。如果用户要求先了解 C3，则先解释，保持缺项不变。如果用户说「不知道材料」，调用工具④或说明缺哪些推荐前置条件，不反复问“材料是什么”。

**语言质量检查**：不重复问已明确的参数，不把“电机转速”自动认作内圈转速，不把装置总载荷视为单轴承载荷；解释为什么需要专业参数，不用用户无法理解的 RoBAS rec 编号向其追问。

## 6. DesignBrief 与状态管理

建议七个用户层分组：
`bearing`、`dimensions`、`operating`、`engineering`、`requirements`、`optimization_slots`、`solver_context`。最后一组只放模式和审核身份/未来映射信息，不让未验证 profile 混入用户确认值。

`ParameterValue` 最小结构：
```json
{
  "value": 18000,
  "unit": "rpm",
  "confirmed": true,
  "source": {"kind":"user","message_id":"turn-004"},
  "precision": "exact",
  "note": null
}
```

- 业务确认只有 `confirmed`/`unconfirmed`；缺失 `value=null`；`precision` 可为 `exact/approximate/range/unknown`。模型不得写 `confirmed`。
- “无轴向载荷”可确认 Fa=0；未提 Fa 仍为 null。“约 15000 rpm”保留近似性，不直接当最终固定工况；尺寸上限与确定尺寸不同。
- 来源必须来自真实用户消息、受信资源/公式，不由 LLM 随意填写。
- 修改 d/D/B、转速、载荷、温度等后，失效相关派生结果和曾经推荐包的适用性；已确认的用户原始选择**不擅自覆盖**，而是报告原依据待核查。
- `PendingProposals` 独立于 DesignBrief 的 confirmed 值；只存提案 ID、内容、数据源、依赖 revision、展示证据、适用条件、过期信息。
- `ConversationHistory` 记录用户消息、模型输出、工具调用事实；**不是第二个可信参数真相来源**。
- `expected_revision` 和 `request_id` 防止并发覆盖、重复确认、工具调用重放。新用户修改导致完整 Brief 的先前接受版本失效，必须针对新 revision 重新接受。

会话/API 建议：
```json
{
  "session_id":"session-001",
  "request_id":"turn-0005",
  "expected_revision":4,
  "message":"转速改成18000转，我想了解脂润滑"
}
```
返回 `reply`、`revision`、本轮实际 `applied_changes`、精简 `design_status`、`tool_trace_summary`（工具名称/状态/耗时/来源，不含模型私有推理）、`deliverable`（若有）。模型不能先对用户声称写入成功再去调用工具写入。

## 7. 工程知识与推荐的证据原则

| 来源 | 可用处 | 不可直接推断 |
|---|---|---|
| LLM 自身知识 | 一般概念和交互解释 | 具体规范表值、材料物性、润滑参数、审批结论 |
| RoBAS 原版 CSV/SQLite | 查询材料/油料原始条目、型号尺寸 | 原版 CSV 存在 ≠ 数据完整、适用或材料已审核 |
| 有出处的标准/厂家资料 | 提供受版本约束的依据 | 不同标准/产品系列的数据可不核实混用 |
| 人工审核工程组合 | 按明确适用范围作实际推荐 | 超出审核工况后继续默认有效 |
| RoBAS 参考 DATA | 后续协议定位与研究 | 直接继承参考值当作用户确认或已验证工况 |

初期只审核 1–2 套有界场景的基础配置。异常 CSV 物性（见 PR-00）不直接进入推荐；润滑 CSV 与 DATA 牵引/油膜模型的映射未闭环，不允许把用户说“脂润滑”当作模型已具备完整参数。RoBAS 原版 getter/backing、游隙和分析保持架问题仍在审计报告中，不用提示词消除工程缺口。

## 8. 最终产物与阶段边界

**产物 A — DRAFT DesignBrief**：对话任意阶段可以保存；含已知、近似、未确认、缺失与来源。

**产物 B — Complete DesignBrief**：工具⑤确认用户层必要字段和工程配置已明确，并记录当前版本的整体确认；不代表计算可执行。

**产物 C — RoBASInputTemplate（未来 PR-06）**：43/324 位置级输入模板，除 Dw/Z/Dpw/fi/fo 及依赖项外，其他字段的来源及 profile 适用性经过独立审查；`TEMPLATE_READY` 是**未来适配器**给出的独立结果。

**产物 D — Runnable DATA.txt（本阶段不做）**：未来五变量已经给定、其派生量复算、DATA 协议通过后的产物；运行成功/收敛/工程合格还需独立证据。

不要把 `brief_complete`、`brief_user_accepted`、`TEMPLATE_READY`、`RUNNABLE_READY` 合并成单个布尔值。V1 `finalize_design_brief` 不暴露 RoBAS 求解能力。

## 9. 最小文件职责建议（不按名字强制拆空壳）

```text
src/bearing_agent_system/
  api.py              # 会话入口与结果
  conversation.py     # 单Agent有界ReAct循环/调用中间件
  models.py           # DesignBrief、提案、工具结果Pydantic
  parameter_catalog.py
  state_store.py      # 受信写入、版本、来源、依赖失效
  checks.py           # 简单已知/缺失/待确认/冲突及需求完成性
  knowledge.py        # 只读数据库、来源/审核规则
  recommendation.py   # 基于审核配置生成可追溯提案
  finalization.py     # 需求检查与版本化导出
tests/
  test_state_store.py
  test_requirement_checks.py
  test_tool_contracts.py
  test_react_loop.py
  test_knowledge.py
  test_recommendation.py
  test_finalization.py
  test_real_llm_dialogue.py
```

这些是**职责建议**而非项目必须拥有的文件数量；PR-01 不创建未来工具的空文件。只有实际实现代码后才写运行命令和真实 LLM 测试结果。RoBAS 适配器在 PR-06 开发且不作为第六个对话工具。

## 10. 开发路线与验收

| 阶段 | 内容 | 验收重点 | 不做 |
|---|---|---|---|
| 本设计 PR #2 | 替换旧流程、冻结五工具合同、更新测试和总控 | 文档互相一致，读者知道谁提问/谁校验/何时停止 | 不写业务代码 |
| PR-01 | DGB 参数目录、DesignBrief、唯一受信更新及简单缺项检查 | 无 LLM 批量保存、修改、幂等、拒绝伪造确认；不错误填零 | 不做 ReAct |
| PR-02 | ReAct loop，接入工具①②，用户意图响应和动态提问 | 真实 LLM 一轮内能自由决定更新/查询/回复，多轮处理修改和中途插问 | 不急于工程推荐 |
| PR-03 | 工具③工程知识查询、可追溯数据源、通用专业解释 | 知识回答/数值有来源、缺数据不乱编、必要时查证 | 不建全量 RAG |
| PR-04 | 工具④审核配置筛选、推荐包与工具①接受推荐 | 整套/部分接受；旧工况提案拒绝；不虚构配置适用性 | 不做独立兼容工具或优化 |
| PR-05 | 工具⑤最终需求检查、版本化确认及导出 | 能导出带缺项的 draft 与完整 Brief；需求完成不误报 DATA ready | 不生成可执行 DATA |
| PR-06（工程准入） | 未来独立 RoBASInputTemplate 适配 | 43/324 映射、五优化槽、来源/模型条件和 golden 对照 | 不自动运行优化/求解 |

PR-01～02 可以不依赖 RoBAS EXE 的工程冻结完成；PR-03/04 的具体工程数值和规则受数据审核约束；PR-06 完整模板就绪需要 PR-00 后续证据。每个 PR 单独分支、测试、审阅，未经用户批准不合并或开展下一个。

## 11. 验收场景和指标

详见 [验收矩阵](CONVERSATION_AGENT_V1_ACCEPTANCE.md)，至少覆盖：
- 批量提供参数、缺项追问、用户改变话题、已问参数避免重复；
- 一轮多工具调用及根据工具反馈改变行动；
- 模型不用工具即可解释一般术语、具体表值必须查询；
- 推荐前置条件缺失→模型自主追问；无可靠审核规则→不编造；
- 用户接受整套/部分提案；重设转速后旧提案不能冒充有效；
- 工具①唯一写入、revision 和 request_id、用户确认不可伪造；
- 用户任意时刻导出不完整草案；完整 Brief 不等于 RoBAS DATA ready；
- 调用预算耗尽、工具报错、重复调用时可解释地停止。

关键确定性不变式 100% 通过；真实 LLM 多轮成功率、错误类型、重复提问、工具调用次数与用户轮数单独报告。指标基线需通过首轮真实测试建立，不虚构效果。

## 12. 项目负责人如何掌握开发

每 PR 交付：改动文件与真实功能、关键数据流/工具时序、代表性用户对话、测试层级（mock/真实 LLM/真实 RoBAS 分别说明）、目前未实现的部分、是否有冗余抽象、下一 PR 前置条件。状态只按 NOT_STARTED/IN_PROGRESS/IMPLEMENTED/TESTED/ACCEPTED 管理，不将写完文档等同于功能完成。

**现在的实际状态**：仅完成设计规范和 PR-00 历史审计；Agent/优化/RoBAS 适配业务代码均未实现。PR #2 仍待用户验收，本文提交不代表批准合并或启动 PR-01。
