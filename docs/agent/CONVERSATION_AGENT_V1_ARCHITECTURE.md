# Conversation Agent V1：受约束 ReAct 架构与工具合同

> 版本：v1.3（2026-11-22，PR #2 最小实现复杂度修订）；状态：**设计规范，Agent 业务代码尚未实现**。  
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

**参数目录必须可执行，而不只是自然语言列表**：每个用户层字段定义 canonical path、类型、单位、R 必需 / C 条件必需 / O 可选 / OPT 优化 / SYS 系统、可接受的值形状、基本跨字段检查，以及用户层 `brief_complete` 判定条件。V1 的条件判断仅用少量直接函数；**不建立针对 RoBAS 43/324 字段的动态工程规则系统**。底层字段映射、派生和协议适用性统一留给 PR-06 专业适配层。

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
- `DesignBriefStore`：单一受信写入、简单内容版本、用户证据核实、用户已确认值与推荐提案分开管理；操作级幂等按实际需要后续增加；
- `RequirementChecker`：按 V1 参数目录、条件必需项和基本约束生成简洁状态及缺项；
- `KnowledgeRepository`：结构化型号/材料/润滑/规则/审核配置，只读版本化数据；
- `RecommendationService`：规则筛选、适用性检查、提案建立；
- `FinalizationService`：需求完成性和交付版本检查；
- `RoBASAdapter`：**PR-06 后续实现**，不纳入当前 ReAct 工具五的判定责任。

建议 Python 3.11+、Pydantic、单进程、SQLite 存业务数据，LLM 支持 tool calling。**V1 每个会话的用户回合与状态写入按顺序处理，同一会话同时只执行一轮**。编排用最小 LangGraph/等价原生 agent loop；选库前锁定实际依赖版本，不引入分布式事务、消息队列、复杂恢复状态机、Supervisor、自定义 planning graph 或多个状态副本。

## 3. 每轮 ReAct 自主工具循环与安全收尾

```text
START / 收到一条用户消息（session_id、message；回合标识可由服务端生成）
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

**ReAct 负责**自主选择提问、解释、知识查询、工程推荐、记录用户事实或请求交付。**程序负责**工具调用的许可、受信写入、数据完整性、基础重复提交防护、必要状态刷新和最终回复真实性；不是固定问卷，也不设置独立 Planning Agent。

**预算与终止**：建议首版每轮约 5–6 次业务工具调用上限（配置项，不是必须用完）、模型调用次数上限、重复调用检测和工具超时。已能回答、需要用户补充或确认、资料不可信、工具失败或预算耗尽时应回复并结束本轮。不能通过不断查询解决用户没有提供的载荷等信息。

**最小调用原则**：同一消息的多个明确参数优先一次批量工具①调用。工具①写入后自动返回最新需求摘要；通常不必再调用工具②。工具④内部从受信状态和知识仓检索，不强迫 LLM 先调用工具③。工具⑤用于用户要求检查/交付或需求汇总，不能在每轮无理由调用。

**写入顺序**：同一会话的模型工具调用与写入全部串行执行；变更成功后后续工具读取最新 DesignBrief。不设计并行工具事务或跨客户端复杂并发控制。模型不可依据已过期的状态推荐新工况，也不能在写入失败后宣称成功。

### 3.1 最小会话和版本模型：三个概念分阶段落地

**当前执行模型：一个会话同一时间只处理一条用户消息，工具按顺序执行。** 不要求 PR-01 实现完整 `turn_id / operation_key / revision` 三层事务体系。

| 概念 | 作用 | 何时实现 |
|---|---|---|
| `brief_revision` | DesignBrief 内容有实际变更时递增，用于查看现有版本、识别旧摘要和旧推荐依据 | **PR-01 最小实现** |
| `turn_id` / `request_id` | 标识一条用户消息与其来源；如客户端可能重复提交，可在回合入口做简单重复请求识别 | **PR-02 随真实会话入口实现**；不要求 PR-01 建立完整回合恢复机制 |
| `operation_key` | 仅当同一 ReAct 回合可能发生多次独立写入且确有重复执行/重试风险时，区分同轮不同写入操作 | **PR-04 或实际出现需求时再实现**，不作为 PR-01 准入条件 |

首版工具①优先**一次批量提交一轮中明确的多个字段**。PR-02 的 ReAct 如果确有同轮多次不同写入，必须串行读取最新状态并分别提交；不得简单使用一个 `request_id` 当作“只允许整轮写一次”的开关。尚未实现操作级幂等时，不自动重放可能已成功的写入；重复值由保存层按无变化处理，无法确认结果时报告当前状态而不是盲目再执行。

`brief_revision` 是**内容版本**而非数据库事务计数：`set/replace/accept_proposal` 引起实际 DesignBrief 变化才递增；PR-05 的 `accept_brief` 仅记录当前 `revision/summary_id` 对应的接受，不递增内容版本。提案、日志、摘要不影响 Brief revision。

初期的保存仅需 SQLite 单进程短事务/原子批量写入；同一会话串行、工具失败给出可解释结果并结束本轮。**不实现分布式锁、跨节点 exactly-once、事务补偿、断点恢复平台或复杂乐观并发框架**。未来真正出现多端同时写入或自动重试场景，再按实测需要加固。 

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

**来源保护**：真实 `session_id`、用户原始消息及其服务端来源标识、当前 revision 由服务器提供或验证；后续若引入操作键，同样由服务端产生，不能相信 LLM 自填。模型不得设置 `confirmed=true`、伪造用户来源或替用户确认。原文片段存在不是充分授权；工具必须检查语义明确、数值/单位、适用范围和提案引用，不能仅靠字符串包含判断同意。

**整份确认保护**：`accept_brief` 必须保持内容修订号不变，仅在独立的接受记录中追加 `accepted_revision` 与用户证据；同一有效接受重复提交须幂等，不可让确认写入本身触发“版本过期”。`summary_id` 应关联工具⑤生成的指定版 **DesignBrief 内容摘要/哈希** 和实际已向用户展示的摘要记录；必须核对当前修订与用户当前明确接受表达。只说“确认”但有多个不同摘要候选时先澄清。调用 `accept_brief` 后若后续 revision 变化，整体确认自动不适用于新 revision。

**操作结果**：`applied_changes`、`rejected_changes`、`revision`、`invalidated_proposals`、`design_status`；`accept_brief` 另返回 `brief_user_accepted_revision`。无实际变更不必增 revision；同一轮可以先修改转速再接受不受其影响的提案；两次写入按顺序执行并读取最新 revision，若将来存在重复执行风险再增加操作级幂等键；提案有效性按依赖快照检查，而非简单看全局 revision。

用户明确的近似值可保留 `precision=approximate, confirmed=false`；用户后续明确“就以 18000 rpm 作为本次分析假定值”时才能记录可用于固定工况的确定分析输入，并保存这一假设的用户依据。不要将近似观测当成已验证的物理真值。

### 4.2 工具② `get_design_status`（简单只读）

**工具②只报告客观缺项，不负责提问策略、优先级打分、责任归属、推荐下一动作。** 使用同一份 [字段合同](DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md) 中 R/C/O/OPT 定义计算状态。工具①有效写入后应将最新状态作为结果的一部分，避免重复查询。

```json
{
  "known": {
    "dimensions.d_mm": {"value":25,"unit":"mm","confirmed":true,"precision":"exact"},
    "operating.temperature_c": {"value":60,"unit":"degC","confirmed":false,"precision":"approximate"}
  },
  "missing": ["operating.radial_load_n","operating.axial_load_n"],
  "pending_confirmation": ["operating.temperature_c"],
  "conflicts": []
}
```

- `known` 中允许有用户给过、但**尚不能当作最终固定值**的估计/范围；这类值必须保留精度和确认信息；
- `missing` 是当前要求下还没有相应信息/可用候选的必要项，`pending_confirmation` 是已有候选或估计但尚不足以满足完成条件的项；不要将 `null` 视为 0；
- 按当前选择条件不适用的 C 字段不列为缺项；五个优化槽默认不列为用户需补填的缺项；
- `conflicts` 只包含客观矛盾，附最简证据路径即可；
- **返回数据，不返回预写好的问句**。模型依据用户当前意图、对话历史与状态自主选问什么、怎么问，避免用户已答却重复追问。

本工具查询对话历史用于解释“用户说不知道”的事实，但不得把历史消息中未提交的数字当作已确认 DesignBrief。

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
{"config_type":"materials_and_cage | lubrication | clearance_and_fits","observed_revision":8}
```

模型只选择推荐类型，**不能自填工况数值**。工具从指定版本的受信 DesignBrief 读取尺寸、转速、载荷、温度等条件，先判断是否具备必要前置数据，再通过内部共用的 KnowledgeRepository 和审核规则筛选有限候选。

返回成功示例：
```json
{
  "status":"PROPOSAL_READY",
  "proposal_id":"materials-A",
  "created_revision":8,
  "items":[{"path":"engineering.materials.ball_id","value":"reviewed_ball_material_id"}],
  "depends_on":["operating.inner_speed_rpm","operating.temperature_c"],
  "dependency_snapshot":"sha256-of-normalized-relevant-values-and-rule-version",
  "source_refs":["reviewed-rule:..."],
  "limitations":[],
  "evidence_status":"REVIEWED"
}
```

**重要修复：创建时的整体 `created_revision` 用于审计，不作为提案是否过期的唯一条件。** 例如用户只修改应用备注，材料提案无需自动失效；用户修改转速、温度或影响适用性的材料约束，则根据 `depends_on` 与规范化依赖快照重新评估。快照应考虑单位转换后的值、相关假设、审核规则/数据版本，不能仅比较裸数字；接受时同时确认提案未被撤回/取代、未发生受信字段冲突。

`observed_revision` 是当前工具读取的设计快照标识：串行执行时仍需在生成提案前与最新状态核对；不一致则返回 `STALE_CONTEXT`，重新读取后再决定是否推荐，不能在旧工况上生成新提案；此处不需要跨客户端并发事务框架。用户之后接受已展示的旧提案时，按**依赖快照**验证是否仍适用，而不是简单要求 `current_revision===created_revision`。

若不足条件返回 `NEED_INPUT`（列出缺少的推荐必要条件）；找不到可审核配置返回 `NO_VERIFIED_CONFIGURATION`，不可由 LLM 临时补造工程数字。推荐不自动写 DesignBrief confirmed 字段，模型需向用户展示候选及来源、说明适用限制，再等待接受。**推荐适用性与 RoBAS 求解模型兼容性不是同一个判定**：暂不实现独立 `check_solver_compatibility`，未验证的模型条件保持 UNKNOWN，不宣称可运行。

### 4.5 工具⑤ `finalize_design_brief`（最终检查、摘要预览与导出）

建议输入：
```json
{"mode":"check | export","expected_revision":12}
```

**`check`**：根据 [字段合同](DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md) 计算用户层需求完整性，返回 `brief_complete`、`missing`、`unconfirmed`、`conflicts`、`brief_user_accepted`，并生成可展示的规范化 `review_summary`、`summary_id` 与绑定内容哈希/版本。**生成摘要不等于用户已经看过**；只有在用户实际收到该版本摘要的可核验展示记录后，才能接受它。

**`export`**：校验当前期望版本和实际快照后，输出带明确状态的 DGBDesignBrief/v1（含来源、五优化槽及未决项）。缺项时只可导出 `DRAFT/INCOMPLETE`；用户层完整时可导出 `COMPLETE_UNCONFIRMED`，若业务要求正式确认交付则还必须经工具① `accept_brief` 取得 `brief_user_accepted=true` 才标 `CONFIRMED_COMPLETE`。导出不代替确认，也不在无用户要求时每轮自动生成文件。

检查输出示例：
```json
{
  "revision":12,
  "brief_complete":false,
  "brief_user_accepted":false,
  "missing":["engineering.lubrication.lubricant_id"],
  "unconfirmed":["operating.temperature_c"],
  "conflicts":[],
  "summary_id":"summary-12-digest",
  "review_summary":"可供用户审阅的字段及未决项摘要",
  "can_export_draft":true,
  "can_export_complete":false,
  "robas_template_ready":"NOT_ASSESSED"
}
```

**完整确认闭环**：

1. 工具⑤ `check` 生成对应 revision 的摘要（内容 ID/哈希）；
2. Agent 向用户展示摘要，服务端记录其已展示（应绑定实际用户可见回复）；
3. 用户明确回复“确认这一版”，Agent 使用工具① `accept_brief(brief_revision, summary_id)`；程序核对展示、当前版本、原话后记录确认；
4. 工具⑤ `export` 导出带确认状态的当前版本；后来修改任一受信设计参数都会令原整份确认不适用于新版本。

**不要混淆**：`brief_complete` 是用户层参数合同通过，不等于用户已整体接受，也不代表 RoBAS 43/324 输入可求解。V1 工具⑤一律返回 `robas_template_ready=NOT_ASSESSED`；PR-06 独立的 RoBASAdapter 将来再给出 `TEMPLATE_READY` / 非就绪检查结果。

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

**仅一套用户层事实来源**：`DesignBrief` 按 [DGBDesignBrief/v1 字段合同](DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md) 保存 `bearing`、`dimensions`、`operating`、`engineering`、`requirements`、`optimization_slots` 和只读内部 `solver_context`。不要用对话历史或模型上下文代替受信参数存储。

典型 `ParameterValue`：

```json
{
  "value":18000,
  "unit":"rpm",
  "confirmed":true,
  "precision":"exact",
  "source":{"kind":"user","message_id":"turn-004"},
  "note":null
}
```

- `confirmed` 是**用户是否明确指定/接受**，不是物性已被专家验证；其他系统派生值用独立的来源/证据级别，不伪装成用户确认。
- `value=null` 是未知，0 必须有明确来源；“约 15000”可存 `precision=approximate, confirmed=false`，不能通过用户层固定分析值检查。D 的上限使用独立几何边界约束，不能篡改 D 的确定值。
- `PendingProposals` 保存方案、数据/规则来源、实际依赖字段和值的规范化摘要、创建版本、展示证据与失效理由；提案不是已确认参数。
- `ConversationHistory` 保存用户原话、模型回复和简洁工具轨迹，不作为第二套业务事实；记录“用户不知道/暂不想回答”，供模型防止重复提问。
- 推荐依赖失效是**字段级**：修改相关转速/温度/材料等使旧提案适用性待复核；只改备注不应造成无必要失效；不主动更换用户以前选择的材料。
- `BriefSummary`（仅轻量摘要记录）保存 `summary_id`、`brief_revision`、内容哈希、生成/展示的对话标识；整体用户接受存 `accepted_revision` 与来源。它不是另一份可以自由变更的 Brief。
- 身份与版本逐步落地：PR-01 只需 `brief_revision` 和用户消息来源记录；PR-02 接入对话回合 ID；若实际工具重试/同轮多写入需要操作级幂等，再引入 `operation_key`。见 §3.1。

API 请求示例：
```json
{
  "session_id":"session-001",
  "message":"转速改成18000转，我想了解脂润滑"
}
```

API 回复应包含 `reply`、实际 `revision`、本轮 `applied_changes`、`design_status`、`tool_trace_summary`、若生成交付的 `deliverable`。声称写入成功必须能与服务端实际状态对应；若有变更被拒绝，不能遗漏拒绝结果。

**数据库实现建议**：SQLite 先保存当前 Brief JSON、内容 revision、必要的消息来源记录；PR-04/05 真正用到推荐提案和摘要时再加少量表。单会话串行、单次批量短事务；不预建操作幂等日志表、事件溯源、消息队列或异常补偿流程。

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

**产物 B — Complete DesignBrief**：工具⑤检查用户层必要条件满足，可先形成 `COMPLETE_UNCONFIRMED`；只有用户对展示过的当前 revision 摘要调用工具① `accept_brief` 后才成为 `CONFIRMED_COMPLETE`。完成与接受分开，不代表计算可执行。

**产物 C — RoBASInputTemplate（未来 PR-06）**：43/324 位置级输入模板，除 Dw/Z/Dpw/fi/fo 及依赖项外，其他字段的来源及 profile 适用性经过独立审查；`TEMPLATE_READY` 是**未来适配器**给出的独立结果。V1 Agent 不建设 324 字段动态工程规则引擎；PR-06 使用明确的映射表、有限的模型条件与专业校验程序实现这一层。

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
| PR-01 | DGB 字段合同、DesignBrief、单次原子批量更新、简洁状态检查和内容 revision | 无 LLM 批量保存/修改、来源与确认校验、约值/范围、未变更不增版本 | 不做 ReAct、操作级幂等或并发恢复框架 |
| PR-02 | 单会话串行 ReAct loop，接入工具①②，动态提问 + 当前草案只读预览 | 真实 LLM 批量提取/修改/中途插问；展示实时 Brief 草案；顺序写入和消息来源、失败后不虚称已保存 | 不急于工程推荐、分布式事务或自动恢复 |
| PR-03 | 工具③工程知识查询、可追溯数据源及推荐基线准备 | 知识回答/数值有来源、缺数据不乱编；准备少量人工审核的受限配置样例 | 不建全量 RAG |
| PR-04 | 工具④审核配置筛选、字段依赖快照和工具①接受提案；仅在真实重试需求出现时补操作级幂等 | 整套/部分接受；同轮多次不同写入串行生效，相关工况变化失效、无关修改不失效 | 不做独立兼容工具或复杂并发恢复 |
| PR-05 | 工具⑤最终需求检查/摘要与导出，工具① accept_brief 落地 | 展示摘要→用户接受该版本→正式交付；允许 draft，完成/用户确认/DATA ready 严格区分 | 不生成可执行 DATA |
| PR-06（工程准入） | 未来独立 RoBASInputTemplate 适配 | 43/324 映射、五优化槽、来源/模型条件和 golden 对照 | 不自动运行优化/求解 |

PR-01～02 可以不依赖 RoBAS EXE 的工程冻结完成；PR-03/04 的具体工程数值和规则受数据审核约束；PR-06 完整模板就绪需要 PR-00 后续证据。每个 PR 单独分支、测试、审阅，未经用户批准不合并或开展下一个。

## 11. 验收场景和指标

详见 [验收矩阵](CONVERSATION_AGENT_V1_ACCEPTANCE.md)，至少覆盖：
- 批量提供参数、缺项追问、用户改变话题、已问参数避免重复；
- 一轮多工具调用及根据工具反馈改变行动；
- 模型不用工具即可解释一般术语、具体表值必须查询；
- 推荐前置条件缺失→模型自主追问；无可靠审核规则→不编造；
- 用户接受整套/部分提案；重设转速后旧提案不能冒充有效；
- 工具①唯一写入、原子批量更新和真实修订号；PR-02/04 同轮多次操作串行且不盲目重放；用户确认不可伪造；
- PR-02 任意时刻展示当前 Brief 草案；PR-05 通过工具⑤导出带缺项的 draft 或正式交付；完整 Brief 不等于 RoBAS DATA ready；
- 调用预算耗尽、工具报错、重复调用时可解释地停止。

关键确定性不变式 100% 通过；多参数提取覆盖率、无效重复提问率和单任务达成率必须基于真实对话单独记录；真实 LLM 多轮成功率、错误类型、重复提问、工具调用次数与用户轮数单独报告。指标基线需通过首轮真实测试建立，不虚构效果。

## 12. 项目负责人如何掌握开发

每 PR 交付：改动文件与真实功能、关键数据流/工具时序、代表性用户对话、测试层级（mock/真实 LLM/真实 RoBAS 分别说明）、目前未实现的部分、是否有冗余抽象、下一 PR 前置条件。状态只按 NOT_STARTED/IN_PROGRESS/IMPLEMENTED/TESTED/ACCEPTED 管理，不将写完文档等同于功能完成。

**现在的实际状态**：仅完成设计规范和 PR-00 历史审计；Agent/优化/RoBAS 适配业务代码均未实现。PR #2 仍待用户验收，本文提交不代表批准合并或启动 PR-01。
