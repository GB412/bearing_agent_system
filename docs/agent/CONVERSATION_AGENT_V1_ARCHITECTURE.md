# Conversation Agent V1：受约束 ReAct 架构与工具合同

> 版本：v1.1（2026-11-22，覆盖原 v1.0 固定五步骤设计）；状态：**设计规范，Agent 业务代码尚未实现**。  
> GitHub：GB412/bearing_agent_system，设计 PR #2；PR-00 #1 仍在评审。  
> 依据：[项目总控](../00_MASTER_PLAN.md) · [动态交互验收](CONVERSATION_AGENT_V1_ACCEPTANCE.md) · [RoBAS PR-00 审计](../pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md) · [324 字段矩阵](../parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)。  
> 本文件**替代**原有「interpret → validate → assess → choose_next_action → compose」固定流程及旧五动作路由，不新增平行架构。

## 0. 项目负责人：一页看懂 V1

**目标**：通过一个 Conversation Agent 与用户多轮对话，获取、澄清、解释、推荐和确认深沟球轴承（DGB）的设计需求，生成版本化的 \`DGBDesignBrief/v1\`，供未来五变量优化及 RoBAS 拟静力学输入适配使用。

**架构**：一个自主决策的 Conversation Agent，最多暴露 **5 个工具**。模型自主决定「问什么、怎么问、何时查知识、何时推荐、是否继续调用工具」；确定性程序决定「什么值能写入、来源是否可信、哪些字段缺失、方案是否符合审核规则、何时可宣称交付完成」。不用 Supervisor、多专业 Agent、复杂通用规则引擎。

**工具**：
1. \`update_design_brief\`：唯一受信写入，保存/修改用户明确提供的参数或接受已展示的推荐。
2. \`get_design_status\`：**简单状态查询**，只读当前已知、缺失、待确认、冲突；**不替模型决定提问顺序**。
3. \`lookup_engineering_knowledge\`：查询专业解释依据、型号/材料/润滑/游隙/配合资料；区分模型一般知识与可追溯的工程数值。
4. \`recommend_engineering_config\`：读取当前受信设计任务，按经审核的工程规则筛选材料/保持架、润滑或游隙/配合组合，生成**待确认提案**。
5. \`finalize_design_brief\`：检查用户层需求是否完整和一致，并返回/导出版本化 DesignBrief、未决项及交付状态。

**不设置**：独立 \`confirm_recommendation\`（并入工具①）、\`check_solver_compatibility\`（用户决定 V1 暂不设）、\`question_planner\`、独立搜索 Agent、求解器运行工具和 CAD 工具。

**本阶段不做**：Dw/Z/Dpw/fi/fo 的优化、RoBAS EXE 求解、CAD、多轴承类型、多工况设计、自动工程批准。PR-00 已记录 43 条 DATA / 324 字段，但工程协议冻结仍 **BLOCKED**。

## 1. 需求范围和参数角色

| 参数组 | V1 目标 | 获取方式 |
|---|---|---|
| 类型/应用 | 单列深沟球轴承；应用场景、可选号 | 用户描述；型号目录只在有真实数据时查询 |
| 固定外形 | d、D、B 具体数值（mm） | 用户明确输入/型号查表后确认 |
| 单稳态工况 | 内外圈转速、轴承实际 Fr/Fa、必要方向、假定工作温度 | 用户明确输入；歧义追问；不能用「高速/轻载」代替数值 |
| 工程配置 | 内外圈/球/保持架材料及类型、润滑方式/润滑剂、初始游隙、内外圈配合 | 用户自选，或工具④推荐后用户接受 |
| 条件项 | 轴内径、座外径、姿态、力矩、错位、预紧等 | 当前计算路径确实需要且没有审核配置时才询问 |
| 设计要求 | 最低寿命等硬约束候选、功耗等目标/偏好 | 用户自然语言描述；可评估性分别记录 |
| 优化预留 | Dw、Z、Dpw、fi、fo | 默认待优化；用户可锁定某项/设置范围；不主动问最终值 |
| 内部配置 | 物性、几何派生、求解器控制与 RoBAS profile | 后续有依据的确定性适配；不转成用户问卷 |

原则：用户不需要知道 RoBAS 324 字段；必须区分用户事实、推荐但未接受的提案、已确认选择、系统派生量、优化变量与尚未审核的求解器参考值。

## 2. 系统架构

\`\`\`text
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
\`\`\`

**背后的普通服务，不额外包装为 Agent：**
- \`DesignBriefStore\`：单一受信写入、版本/幂等、用户证据核实、用户已确认值与推荐提案分开管理；
- \`RequirementChecker\`：按 V1 参数目录、条件必需项和基本约束生成简洁状态及缺项；
- \`KnowledgeRepository\`：结构化型号/材料/润滑/规则/审核配置，只读版本化数据；
- \`RecommendationService\`：规则筛选、适用性检查、提案建立；
- \`FinalizationService\`：需求完成性和交付版本检查；
- \`RoBASAdapter\`：**PR-06 后续实现**，不纳入当前 ReAct 工具五的判定责任。

建议 Python 3.11+、Pydantic、单进程、SQLite 存业务数据，LLM 支持 tool calling。编排用最小 LangGraph/等价原生 agent loop；选库前锁定实际依赖版本，不为了 ReAct 名称而新增 Supervisor、自定义 planning graph 或多个状态副本。

## 3. 一轮执行和 ReAct 循环——取代旧固定五步骤

\`\`\`text
START / 用户新消息
  ↓
加载 session 对应 DesignBrief、最近对话、待确认提案及状态摘要
  ↓
Conversation Agent (LLM)
  ├─ 直接向用户回复/提问/解释 → final_response_check → END
  └─ 自主选工具 → 权限/参数/预算校验 → 执行
                                         ↓
                                   返回结构化结果
                                         ↓
                                   更新上下文与状态
                                         │
                                         └──── 回到同一个 Agent (LLM)
\`\`\`

**模型在单轮内可以反复决定下一步行动，但不能无限循环。** 每个用户消息完成后，必须把交互控制权还给用户；不能在没有用户消息时自行确认设计值。建议初期每轮最多约 5–6 次业务工具调用（可配置、需真实测试调整），限制重复同参数调用、超过预算后可靠停止。可根据使用情况再设模型调用上限/超时和只读补查限制。

**结束条件**：无需工具即可回答；需要用户补充/澄清；等待用户接受推荐；本轮已可汇总；本轮工具失败/无可靠数据；预算耗尽；用户要求交付且工具⑤已返回结果。最后一次自然语言回复不能重写工具返回的事实。

**不做的事**：不要求固定「提取→写入→检查→决策→回复」五个 LLM/图节点；不强制每轮调用工具②；不要求每次先查工具③才可使用工具④；无独立 ASK/CLARIFY/RECOMMEND/CONFIRM/SUMMARIZE 路由节点（这些是自然语言行为，不是五个工具或 Agent）。

**调用顺序**：同一用户消息涉及参数更新与推荐时，先完成参数受信更新，再基于最新 DesignBrief 生成推荐。所有**写入串行、版本控制**；可以并行的只读调用必须使用一致的 DesignBrief revision。工具①写入成功后自动附上刷新后的精简状态，避免模型机械重复调用工具②。

**建议最小图**：

\`\`\`text
prepare_context → agent ──(tool_calls?)──► guarded_tools ──► agent
                     └──(response)──► finalize_response → END
\`\`\`

\`prepare_context\` 与 \`finalize_response\` 可用普通应用函数，不强制做图节点。用户确认与提交操作在普通对话回合完成，不使用复杂的长时间暂停/恢复机制；必要的会话持久化和业务持久化分开。

## 4. 五个工具：输入输出、权限、失败条件

### 4.1 工具① \`update_design_brief\`（唯一写入）

用途：批量保存用户明确事实、修订用户事实、接受以前已经展示且当前仍有效的推荐提案。不再有独立确认工具。

建议 schema：

\`\`\`json
{
  "operation": "set | replace | accept_proposal",
  "changes": [
    {"path": "operating.inner_speed_rpm", "raw_value": "18000转", "evidence_span": "内圈转速18000转"}
  ],
  "proposal_id": null,
  "accepted_paths": []
}
\`\`\`

\`set/replace\` 使用 \`changes\`；\`accept_proposal\` 使用 \`proposal_id\` 和可选 \`accepted_paths\`，不混在一个危险的无约束 payload 里。模型不得传 \`confirmed=true\`、\`confirmed_by=user\`、\`source=user\` 或 \`revision\` 来伪造授权。

**服务器端隐式注入**：\`session_id\`、用户真实消息、\`message_id\`、\`request_id\`、\`expected_revision\`。这些值从经认证的会话入口获取，而不是信任模型自填。工具检查 evidence_span 在真实消息中，验证明确语义、参数目录、单位/范围、冲突、用户锁定规则、有效推荐提案；需要澄清时拒绝相应字段并说明理由。证据字符串的存在**本身不等于**用户已确认；模糊语言和推断不能直接视为精确值。

提交采用单次原子写入、幂等 request_id；有冲突时不得悄悄覆盖。仅当实际发生已接受的有效状态变更时 revision 增加。一次消息可批量更新多个字段，不应每个字段单独调用一次工具。

返回：\`applied_changes\`、\`rejected_changes\`、\`revision\`、\`invalidated_dependent_proposals\`、简洁 \`design_status\`。如用户修改转速，不自动换材料；只对旧材料推荐的适用性标记待核查。

### 4.2 工具② \`get_design_status\`（简单只读）

**职责只限于客观状态，不替模型规划问题。**

\`\`\`json
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
\`\`\`

这是**示例状态**，不表示 d/D/B 会自动从无来源型号中补出。字段可以附简单单位/不确定性/状态，不建立复杂的「责任归属、优先级打分、预生成问题列表、处理动作」系统。已确实标记为非适用的条件项不列为 \`missing\`；近似值、上限与确定值的区别不能被扁平化隐藏。

工具返回以后：
- **模型负责判断问哪一个、问几个、怎么用自然语言问**；
- 一般先处理用户当前意图，再关注关键工况和推荐前置条件，但**不是固定问卷**；
- 用户表示不知道材料时，可调用工具④或工具③，不重复问材料名；
- 对话历史帮助避免刚刚问过又马上重复；如果用户只想了解知识，先解释而不是强制继续填表；
- 模型不得仅因为“自己觉得不重要”便把 \`missing\` 从检查器中删掉。

工具①更新成功后已经附精简状态。用户单纯要求查看进度，或 LLM 真正需要刷新状态时，才主动调用工具②。

### 4.3 工具③ \`lookup_engineering_knowledge\`（只读知识）

建议输入 \`{ "topic": "clearance | fit | bearing_model | material | lubrication | terminology", "query": "...", "context_revision": 8 }\`。返回 \`summary\`、\`facts[]\`、\`source_refs[]\`、\`applicability\`、\`limitations\`、\`evidence_level\`，无结果明确 \`NOT_FOUND/UNVERIFIED\`。

知识来源按证据强度分层：
1. **模型内在知识**：理解用户问题、解释公认的通用概念、组织语言，不作为未经核验的具体材料物性/公差/标准数值来源；
2. **本地结构化数据**：RoBAS SQLite 型号与几何、CSV 材料/润滑（原始值均需质量核验）、有来源的标准表、人工审核配置；标识数据版本/哈希、单位、适用范围；
3. **可选外部检索**：当本地缺少来源、用户明确要求依据时，使用可信标准/厂家手册获取证据；**V1 不把联网搜索变成强制默认步骤**，网页内容仅为候选证据，未经审核不得成为可计算的系统配置。

V1 不建大规模 RAG；结构化数据 + 少量审核规则优先。用户问“CN 与 C3 的含义”可以根据已知知识先解释；问“本尺寸游隙具体数值范围”必须查可追溯依据。没有证据时直接告知，不填造数字。

### 4.4 工具④ \`recommend_engineering_config\`（筛选、建立提案）

建议输入：
\`\`\`json
{"config_type":"materials_and_cage | lubrication | clearance_and_fits","design_revision":8}
\`\`\`
工具**自己读取当前受信 DesignBrief**，不让模型重复传 d/D/B/转速等工况，以免传旧值。若 \`design_revision\` 不匹配当前版本，拒绝创建旧工况提案。

规则：检查推荐所需前提 → 查询有限的**已审核**候选组合 → 校验已知适用条件、来源及必要属性 → 形成少量备选 → 返回证据和限制。**工具内部使用工具③底层同一数据仓/规则，不要求模型另行先调工具③。**

返回：
\`\`\`json
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
\`\`\`
若缺少前置条件，则返回 \`NEED_INPUT\` 与缺哪些条件；无审核数据返回 \`NO_VERIFIED_CONFIGURATION\`；当前 RoBAS 模型兼容性尚未证明的候选**不得宣称可运行**。在 PR-04 不单独开发 \`check_solver_compatibility\` 工具：推荐适用性筛选只检查当前**有证据的**条件，底层模型未知保持 UNKNOWN，不假装已验证。

推荐是一个 **proposal**，不是 DesignBrief 中的用户已确认值。推荐可能同时包含材料、钢球、保持架材料；允许用户整套或部分接受。模型负责解释推荐，不得创造没有返回的工程数字或冒充“最优方案”。

### 4.5 工具⑤ \`finalize_design_brief\`（最终检查与导出）

输入：
\`\`\`json
{"mode":"check | export","expected_revision":8}
\`\`\`
\`check\` 不修改业务状态，只报告设计需求是否完整；\`export\` 导出**指定修订版本**的需求文档（完整或标记为草案）。若用户希望将整个 Brief 标记为「已确认」，必须已经明确看过当前摘要并接受**该版本**；这项证据在受信状态层验证，不能由模型以 \`mode=export\` 代替用户同意。

\`\`\`json
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
\`\`\`

检查项：d/D/B、套圈转速、真实单轴承 Fr/Fa、分析温度；需要用户确认的材料/润滑/游隙和配合；条件项与自相矛盾参数；偏好与约束记录；来源和 revision；五优化槽保留为待优化或明确锁定。

**特别边界**：工具⑤是 **用户层需求完整性与交付检查**，不是当前就检查 RoBAS 324 字段的求解输入完整性。V1 暂不实现独立 Solver Compatibility 工具。未来 PR-06 的确定性 RoBASAdapter 有自己的协议 gate，只有那时经过审核才能产生 \`TEMPLATE_READY\`；工具⑤只能返回 \`robas_template_ready: NOT_ASSESSED\` 或后续接收适配器的独立结果，**不得因 brief_complete=true 自称 DATA 可运行**。

模式分支：用户随时能导出标记为 INCOMPLETE 的草案；只有 \`brief_complete=true\` 且没有阻断时才允许作为完成版需求导出。需要保存确认摘要、版本和生成文件/内容的可追溯 ID，不能从不匹配 revision 的旧内容导出。

## 5. Agent 如何决定「下一个问什么、怎么问」

这不设专门工具，也没有五动作硬路由。模型可根据：
- 当前用户明确意图：直接回答其问题、优先处理修改或推荐请求；
- \`get_design_status.missing\`：哪些**客观必需项**尚未明确；
- 当前 DesignBrief 的已知值与近似值、范围、冲突；
- 专业推荐的已知前置条件与工具返回的 \`NEED_INPUT\`；
- 会话历史：用户是否已回答、已表示不知道、暂不想回答；
- 交互负担：优先问 1–2 组相关问题，不每次逐项点名。

**模型有权决定提问的时机、对象和表达，但无权更改哪些字段是必要输入。** 不生成「优先级分数」「下一步动作计划」作为工具②职责。普通顺序可倾向：固定尺寸/型号 → 明确套圈转速 → Fr/Fa → 温度 → 推荐与确认工程配置；但可被用户意图打断，不得硬编码为固定问卷。

案例：已知 d/D/B、转速而 Fr/Fa 缺失，模型可询问“轴承实际承受的径向载荷与轴向载荷分别是多少？没有轴向载荷可以说明为零”。如果用户要求先了解 C3，则先解释，保持缺项不变。如果用户说「不知道材料」，调用工具④或说明缺哪些推荐前置条件，不反复问“材料是什么”。

**语言质量检查**：不重复问已明确的参数，不把“电机转速”自动认作内圈转速，不把装置总载荷视为单轴承载荷；解释为什么需要专业参数，不用用户无法理解的 RoBAS rec 编号向其追问。

## 6. DesignBrief 与状态管理

建议七个用户层分组：
\`bearing\`、\`dimensions\`、\`operating\`、\`engineering\`、\`requirements\`、\`optimization_slots\`、\`solver_context\`。最后一组只放模式和审核身份/未来映射信息，不让未验证 profile 混入用户确认值。

\`ParameterValue\` 最小结构：
\`\`\`json
{
  "value": 18000,
  "unit": "rpm",
  "confirmed": true,
  "source": {"kind":"user","message_id":"turn-004"},
  "precision": "exact",
  "note": null
}
\`\`\`

- 业务确认只有 \`confirmed\`/\`unconfirmed\`；缺失 \`value=null\`；\`precision\` 可为 \`exact/approximate/range/unknown\`。模型不得写 \`confirmed\`。
- “无轴向载荷”可确认 Fa=0；未提 Fa 仍为 null。“约 15000 rpm”保留近似性，不直接当最终固定工况；尺寸上限与确定尺寸不同。
- 来源必须来自真实用户消息、受信资源/公式，不由 LLM 随意填写。
- 修改 d/D/B、转速、载荷、温度等后，失效相关派生结果和曾经推荐包的适用性；已确认的用户原始选择**不擅自覆盖**，而是报告原依据待核查。
- \`PendingProposals\` 独立于 DesignBrief 的 confirmed 值；只存提案 ID、内容、数据源、依赖 revision、展示证据、适用条件、过期信息。
- \`ConversationHistory\` 记录用户消息、模型输出、工具调用事实；**不是第二个可信参数真相来源**。
- \`expected_revision\` 和 \`request_id\` 防止并发覆盖、重复确认、工具调用重放。新用户修改导致完整 Brief 的先前接受版本失效，必须针对新 revision 重新接受。

会话/API 建议：
\`\`\`json
{
  "session_id":"session-001",
  "request_id":"turn-0005",
  "expected_revision":4,
  "message":"转速改成18000转，我想了解脂润滑"
}
\`\`\`
返回 \`reply\`、\`revision\`、本轮实际 \`applied_changes\`、精简 \`design_status\`、\`tool_trace_summary\`（工具名称/状态/耗时/来源，不含模型私有推理）、\`deliverable\`（若有）。模型不能先对用户声称写入成功再去调用工具写入。

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

**产物 C — RoBASInputTemplate（未来 PR-06）**：43/324 位置级输入模板，除 Dw/Z/Dpw/fi/fo 及依赖项外，其他字段的来源及 profile 适用性经过独立审查；\`TEMPLATE_READY\` 是**未来适配器**给出的独立结果。

**产物 D — Runnable DATA.txt（本阶段不做）**：未来五变量已经给定、其派生量复算、DATA 协议通过后的产物；运行成功/收敛/工程合格还需独立证据。

不要把 \`brief_complete\`、\`brief_user_accepted\`、\`TEMPLATE_READY\`、\`RUNNABLE_READY\` 合并成单个布尔值。V1 \`finalize_design_brief\` 不暴露 RoBAS 求解能力。

## 9. 最小文件职责建议（不按名字强制拆空壳）

\`\`\`text
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
\`\`\`

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
