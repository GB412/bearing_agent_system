# Conversation Agent V1：可执行架构设计说明

> 状态：**设计讨论稿 v1.0，尚未进入业务代码开发**  
> 日期：2026-11-22  
> 仓库：`GB412/bearing_agent_system`  
> 父基线：PR-00 分支 `docs/pr-00-robas-quasi-static-input-audit`（当前未合并）  
> 依据：[总控规划](../00_MASTER_PLAN.md)、[PR-00 输入审计](../pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md)、[324 字段矩阵](../parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)  
> 原则：**文档说明目标架构，不等于已经实现或经过工程验收。**

## 0. 给项目负责人的一页说明

### 0.1 现在究竟要做什么？

把“我要设计高速电机深沟球轴承”这样不完整的自然语言，通过 **一个** Conversation Agent 的多轮交互，逐步转化为可追溯的 DGB 设计任务。Agent 要能知道：
- 已知什么：尺寸、载荷、转速、温度、用户已经接受的工程配置；
- 还缺什么：会妨碍形成设计任务/计算模板的字段或依据；
- 下一步做什么：追问、澄清、解释、查询、给出有来源的推荐、请用户确认、汇总；
- 什么时候结束：随时能保存需求草案，只有通过确定性检查才可声明输入模板就绪。

用户层目标信息采用已讨论的 V1 口径：DGB 和应用场景；固定 d/D/B；当前轴承的内外圈转速、Fr/Fa、必要方向；假定工作温度；材料/保持架组合配置；润滑方式/润滑剂；游隙和配合；必要时的特殊工况；性能要求；五个待优化变量 Dw、Z、Dpw、fi、fo。

### 0.2 当前不做什么？

- 不开发 GA、BO、代理模型或任何五变量搜索；
- 不运行真实 RoBAS 来决定几何参数；
- 不开发 CAD、二维工程图、三维模型；
- 不支持多轴承类型或复杂多工况优化；
- 不设置 Supervisor、Material Agent、Lubrication Agent 等独立 Agent；
- 不建立庞大 RAG 系统、通用规则引擎、候选版本图或事件溯源平台；
- 不把 RoBAS 324 个底层字段变成 324 个对话问题；
- 不修改原版 RoBAS C#/EXE、DATA 和资源数据库。

### 0.3 三条必须区分的交付状态

1. **DRAFT**：部分需求已经记录，可随时查看和继续对话。
2. **BRIEF_CONFIRMED**：用户接受当前已展示的 DesignBrief；可能仍有缺项。
3. **TEMPLATE_READY**：确定性映射检查证明，除五个优化变量以及明确依赖它们的派生值之外，全部当前模式必需的非优化字段已有可信来源/值，无阻断项。

以上是任务级**计算出的完成状态**，不是第三种参数确认状态。单个用户参数的业务确认状态仍只用 `confirmed` / `unconfirmed`；缺失值用 `null` 表达。

`RUNNABLE_READY` 属未来优化与求解集成阶段：补齐五变量和依赖，重新校验后才能生成可执行 DATA。**本阶段不产生可执行 DATA。**

## 1. 约束与设计边界

| 维度 | V1 决策 | 边界/警告 |
|---|---|---|
| 轴承 | 单列深沟球轴承 DGB | 其他型号仅提示不支持 |
| 工况 | 单一稳态设计工况 | 多工况信息可记录，不生成多份 DATA |
| 尺寸 | d、D、B 的确定值 | 用户只说上限时不可擅自当成最终值 |
| 转速 | 内/外圈实际转速与转动关系 | 未指定旋转圈的“15000 rpm”需澄清 |
| 载荷 | 当前轴承所受 Fr/Fa、必要方向 | 设备总载荷/整个转子重力不能直接当单轴承载荷 |
| 温度 | 假定轴承工作/分析温度 | 首版只有经核实的指定温度模型才能用一个温度填相关字段 |
| 材料 | 内外圈组合、钢球、保持架；必要时轴/座 | 材料 CSV 只覆盖部分物性，其余依赖审核配置 |
| 润滑 | 方式、具体润滑剂及适用模型 | 脂润滑名称不等于当前 RoBAS 已支持脂润滑物理模型 |
| 游隙/配合 | 初始游隙 + 配合方案 | CN/C3 为区间，不能无规则变成唯一数；自由/工作游隙不能混用 |
| 安装/特殊项 | 条件性获取 | 安装姿态、轴内径、座外径、预紧、错位、力矩等不作为普通用户默认问卷 |
| 目标 | 记录硬约束候选、性能偏好 | 不在此阶段决定优化算法和目标权重 |
| 五变量 | Dw/Z/Dpw/fi/fo 占位或用户锁定范围 | 不主动询问最终优化值；相关派生几何必须延后 |
| 计算协议 | RoBAS 拟静力学 Mode=-1 | PR-00 的工程输入冻结仍 BLOCKED |

## 2. 系统结构：一个 Agent + 四个普通服务

```text
                         用户消息
                            │
                    Conversation API
                            │
                  Conversation Agent (LLM)
                理解 / 下一步动作 / 表达
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
     DesignBriefStore   RequirementChecker  KnowledgeService
     单一受信状态写入     完整性/冲突/依赖      CSV/SQLite/审核规则
          │                 │                  │
          └─────────────────┼──────────────────┘
                            │
                   RoBASInputAdapter
               字段映射/缺项/协议准备检查
                            │
         DesignBrief + MissingReport + InputTemplate
                    （不运行优化）
```

注意：图中是职责，不等于必须创建 5 个大型类或 5 个进程。建议使用一个 Python 后端进程、一个 LLM 客户端、一份参数目录、一套 Pydantic 数据模型和一个轻量存储。模块边界按可测试性划分，不按名字包装 Agent。

| 组件 | 负责 | 输入 | 输出 | 绝不负责 |
|---|---|---|---|---|
| Conversation Agent | 理解话语、选择提问/推荐/汇总动作、生成友好回复 | 最近消息、DesignBrief 摘要、检查报告、工具结果 | 结构化意图提案和回复 | 直接改数据库或伪造材料物性 |
| DesignBriefStore | 参数合法变更、来源/确认、依赖失效、版本与持久化 | 受约束的参数 patch、预期版本 | 新版本及变更摘要 | 自行决定该问什么 |
| RequirementChecker | 类型/单位/范围、冲突、必填条件、依赖和 readiness | 当前 DesignBrief、catalog、映射能力 | 缺项/冲突/可提问候选/ready 结果 | 自行写用户答案 |
| KnowledgeService | 查询 DGB 型号、材料/润滑 CSV 和审核规则；产生候选组合 | 有界查询、已知工况 | 带来源与适用限制的候选 | 无依据生成工程阈值 |
| RoBASInputAdapter | 将受信字段映射到 43/324 模板、报告缺口 | DesignBrief、求解器 profile、输入矩阵 | InputTemplate / MissingReport | 填造五变量、猜测 profile、调用求解器 |
| Conversation API | 接入、会话标识、错误响应 | session_id、user_message、revision | agent_message、brief_delta、next_action、readiness | 放置工程业务规则 |

注：上表将 StateManager 的“唯一受信写入”原则落在 DesignBriefStore 上，**不照搬旧项目复杂实现**。仓库文档虽提出 LangGraph/Pydantic/Python3.11+，本方案使用最小 LangGraph 编排即可，不引入新的 Supervisor。

## 3. 对外输入输出合同（先设计，代码在后续 PR 实现）

### 3.1 单轮输入

```json
{
  "session_id": "session-001",
  "expected_revision": 4,
  "request_id": "turn-0005",
  "message": "转速改为18000转，润滑先按你推荐的方案"
}
```

- `session_id` 识别同一设计会话。
- `expected_revision` 用于避免并发/重复消息覆盖新状态。
- `request_id` 用于重试去重。
- `message` 是用户自然语言；可一次给多个参数，可纠错，也可只是提问。

### 3.2 单轮输出

```json
{
  "reply": "已把内圈转速修订为18000 rpm。先前润滑推荐需重新核对适用性。",
  "revision": 5,
  "brief_delta": [
    {"path": "operating.inner_speed_rpm", "operation": "replace", "value": 18000}
  ],
  "next_action": {"type": "ASK", "target": "engineering.lubrication"},
  "readiness": {
    "brief_user_accepted": false,
    "template_ready": false,
    "missing_count": 3,
    "blocking_reasons": ["lubrication_profile_unverified"]
  }
}
```

输出内容必须从真正已持久化状态构造；模型不能声称保存了实际未保存的更新。以上数值、`missing_count` 均为接口例子，不代表已运行结果。

### 3.3 V1 DesignBrief 的最小用户层结构

建议保留七个一级组，而不是保存全部 324 字段：

1. `bearing`：type、application、optional model；
2. `dimensions`：d/D/B，以及用户明确给出的额外固定结构条件；
3. `operating`：内外圈 rpm、轴承 Fr/Fa、方向、单稳态工况、假定分析温度，特殊力矩/错位可选；
4. `engineering`：内外圈/钢球/保持架材料、保持架类型、润滑方式/润滑剂、初始游隙、内外圈配合、必要安装配置；
5. `requirements`：用户明确表达的硬约束候选和偏好，注明是否能被当前模型评估；
6. `optimization_slots`：Dw、Z、Dpw、fi、fo，默认待优化；允许后续锁定单变量或限制范围；
7. `solver_context`：mode、profile_id、profile_sha256、数据源版本、审计/适用性状态及缺项报告。

其中 `model`、应用场景、精度、密封、工作制度等可以保留为上下文，但不自动成为 DATA 的必需字段。不同来源的字段各自带确认与溯源，不要为每个物性建立独立的用户对话问题。

建议以 `ParameterValue` 统一封装**用户可决定的参数**：

```json
{
  "value": 15000,
  "unit": "rpm",
  "confirmed": true,
  "source": {"kind": "user", "ref": "turn-0002"},
  "precision": "exact",
  "note": null
}
```

- `confirmed` 只有 true/false 两种；无值时 `value:null` 且未确认。
- `precision` 只说明信息是 exact / approximate / range / unknown，不是另一套“确认状态”。
- “15000 rpm”可以作为用户明确给出的值确认；“大概 15000 rpm”需要保存为估计或范围，最终固定计算值仍需明确。
- “没有轴向载荷”可以由用户明确表达转换为 Fa=0；没提 Fa 不能写 0。
- 用户接受一套推荐材料时，对其中有明确枚举值的字段批量确认，但不能自动补齐 CSV 未包含的物性。

系统派生字段可以只在 adapter 中按依赖计算，不必全部长期持久化；必须能追溯公式/配置版本。

### 3.4 工程推荐包（临时提案，不是一套复杂参数状态机）

```json
{
  "proposal_id": "rec-material-0003",
  "kind": "material_bundle",
  "source_refs": ["material_catalog_sha256:...","rule:R-..."],
  "depends_on": ["operating.inner_speed_rpm","operating.temperature_c"],
  "items": [
    {"path":"engineering.ring_material","value":"某审核记录ID"},
    {"path":"engineering.ball_material","value":"某审核记录ID"}
  ],
  "limitations": ["适用转速范围需审查"]
}
```

用户明确说“接受刚才的材料推荐”，且没有歧义时，才由受信写入模块确认这些字段。未接受前不更改 confirmed。若同时存在多个“刚才的推荐”无法识别指向，应澄清而非猜测。

## 4. 每一轮实际怎样运行

第一版采用有界动态流程（建议最小 LangGraph）；不是无限循环的 ReAct，也不是固定问卷：

```text
START
  ↓
① interpret_user_message（LLM结构化提取）
  ↓
② validate_and_apply（确定性校验、原子提交、修订号+1）
  ↓
③ assess_requirements（缺项、冲突、依赖失效、ready）
  ↓
④ choose_next_action（LLM在允许候选动作中选）
  ├── ASK / CLARIFY / SUMMARIZE → ⑤ compose_and_return
  └── RECOMMEND / CONFIRM（必要查询）→ bounded_knowledge_lookup
                                              ↓
                                         ⑤ compose_and_return
  ↓
END
```

实现时可以把 ②③ 合并为一个服务调用。建议每轮最多一次主要工程知识查询和少量明确限定的补查；若工具不通，提供缺项解释，不陷入无限自动重试。

### 4.1 LLM 理解输出：只提出变更

```json
{
  "intent": ["correct_value", "accept_recommendation"],
  "patch_proposals": [
    {"path":"operating.inner_speed_rpm","raw_value":"18000转","operation":"replace",
     "evidence":"转速改为18000转"}
  ],
  "referenced_proposal_id": "rec-lub-0002",
  "ambiguities": []
}
```

LLM 无权限填写 `confirmed_by=user` 或写入 DB；原始用户话语必须支持每个明确参数的变更。推荐接受只能引用确实在当前会话展示过、仍适用的 proposal ID。提示词不是唯一安全机制，写入端必须检查。

### 4.2 状态更新规则

- 新精确值：合法且来自当前明确用户表达时写入 confirmed=true。
- 估计/范围：记录 `precision` 与边界，不偷换成固定计算值；可用于下一轮追问。
- 用户修订：明确“改为/不是/实际上”等，允许更改此前确认值；记录修订摘要。
- 语言冲突：如用户同一轮同时“外圈固定”和“外圈6000 rpm”，不执行冲突字段，返回 CLARIFY。
- 无依据推断：不能更新为 confirmed。
- 依赖变化：材料/润滑/游隙的推荐适用性重新检查；派生计算缓存失效。对用户直接指定的原始值不无故撤销确认，但可标记 `applicability_blocked`；基于旧工况确认的推荐包需重新推荐或请用户再次确认。
- 版本冲突：expected_revision 不一致时拒绝过期写入并返回当前版本。
- 重试：同一 request_id 不得重复确认/重复写入。

建议状态落盘初期使用单机 SQLite（会话表+当前 DesignBrief JSON+有限轮次记录即可），无需建设多数据库或复杂事件总线；具体是否改成文件存储可由 PR-01 在测试后比较决定。

## 5. 动态决策：Agent 怎样知道下一步问什么？

### 5.1 确定性检查先形成候选

RequirementChecker 从参数目录和所选 solver profile 得到：

```json
{
  "known": ["dimensions.d_mm","dimensions.D_mm","dimensions.B_mm"],
  "missing_required": ["operating.inner_speed_rpm","operating.radial_load_n"],
  "uncertain": ["operating.axial_load_n"],
  "conflicts": [],
  "pending_recommendations": [],
  "conditional_questions": ["operating.load_direction"],
  "next_question_candidates": [
    {"target":"operating.inner_speed_rpm","reason":"计算必需、当前未知"},
    {"target":"operating.radial_load_n","reason":"计算必需、当前未知"}
  ]
}
```

不是在提示词里写死一个巨大的固定问卷。参数是否必需由条件和所选计算路径决定。

### 5.2 LLM 只在合法候选中做动态选择

优先解决冲突/歧义；其次选择对计算就绪和推荐依赖影响最大的缺项；再次处理待确认推荐，最后才是可选偏好。LLM 可根据会话上下文把自然相关的 1–2 个问题合并提问，例如“径向、轴向载荷分别是多少？”，避免每回合只问一个无关问题。

若用户明确要求“先解释游隙”，应优先回答用户当前提问，再回到补全流程；不能强制追问。

如果 LLM 选择不在允许集合中的动作，校验拒绝并使用确定性回退（例如选择第一项最高优先级阻断）。若没有真正可靠的推荐数据源，不允许模型仅凭提示词制造具体材料/润滑数值。

### 5.3 允许的下一步动作

| 动作 | 目的 | 用户侧表现 |
|---|---|---|
| ASK | 获取关键缺项 | “需要确认实际径向载荷是多少？” |
| CLARIFY | 消除不明确/冲突 | “外圈究竟固定还是6000 rpm？” |
| RECOMMEND | 查询并展示候选配置 | “可选材料配置 A/B，依据是……” |
| CONFIRM | 请用户整体接受/修改推荐或阶段性摘要 | “是否采用这套材料与保持架配置？” |
| SUMMARIZE | 展示已知、未决、缺项和下一步 | “已确认尺寸/转速，剩余润滑和安装……” |

用户要求纯解释、查看进度或撤回时，可在既有动作（SUMMARIZE/CLARIFY）和回复生成中处理，不需要为每个交互创造新 Agent。进入最终完成状态必须由 Checker 判定，不由 LLM 自行宣布。

## 6. 工程推荐：推荐什么，如何保证不乱推荐？

### 6.1 先推荐组合，而不是逐项盘问

- 材料/保持架组合：优先同一套圈材料 + 独立钢球/保持架材料选择；
- 润滑组合：方式、具体润滑剂、所需物性与可表示的模型；
- 游隙/安装组合：初始游隙区间/分析值路径、内外圈配合、适用温度与结构假设；
- Solver Profile：系统选择经过审核的计算配置，对普通用户说明关键假设而非数值步长。

同一推荐包允许用户“一次接受”，也允许“接受材料、拒绝润滑”这样的局部确认。不要把所有用户参数一次打包确认，避免意外修改与未理解的接受。

### 6.2 推荐数据必须有适用性

流程：已有工况 → 查询结构化数据 → 检查质量与适用范围 → 生成少量候选及解释 → 展示来源与限制 → 等待明确接受 → 更新 DesignBrief → 再次做完整性检查。

按 PR-00：材料和润滑基础物性来自原版 CSV；型号尺寸来自 SQLite；部分物性异常、润滑 CSV 与 DATA 牵引/油膜字段未闭环。不能仅凭“记录存在”称为可推荐/可计算。**优先建立 1–2 套人工审核的高质量基线配置**，比先支持几十种未经核验的材料润滑组合更合适。

若查不到可靠数据：
- 可以解释选择依据和现有证据缺口；
- 可以给出“需要工程确认”的候选，但不能冒充已审核推荐；
- 不能把查不到的值填成以前 DATA 的默认值；
- 明确提示“这项不影响当前对话继续，但阻断 TEMPLATE_READY”。

## 7. RoBAS 映射：只保留必要边界

### 7.1 为什么需要两种对象

- `DesignBrief`：面向用户，表达真正的设计意图。
- `RoBASInputTemplate`：面向程序，定位 43 条记录的 324 个字段和它们的取值来源。

不要将 InputTemplate 中的 324 个字段全部持久化成用户必答参数。系统配置、DB 记录和派生参数按版本生成或引用。

### 7.2 模板就绪检查（最终以后实现）

当且仅当：
1. 固定尺寸/工况及所选模式必需的用户字段已确认；
2. 需要用户接受的工程配置确已接受；
3. profile 的 ID/SHA/适用范围与逐字段允许继承清单受信；
4. CSV/DB 记录有版本和字段映射；派生公式可追溯；
5. 五个优化槽和它们的依赖被正确标为以后补齐，而不是用占位零伪装计算值；
6. 不存在当前模板阶段阻断的来源、单位、坐标、模型不兼容或配置冲突；

才可以声明 TEMPLATE_READY。

如果只满足部分要求，输出 `MissingReport`，字段包含 `user_field`、`data_field_id`、`reason`、`resolution_owner`（USER/KNOWLEDGE/ENGINEERING/OPTIMIZER）、`suggested_action`。这样不会把所有底层 BLOCKED 全部变成用户提问。

### 7.3 已知 RoBAS 关键阻断

目前 PR-00 尚未工程冻结；尤其需要警惕：
- fo/fi 原版 backing fields 不同步；
- `ShimThickness1` 与 freeIntCls 映射问题；
- Mx/My/Rx/Ry 的 UI 值到 DATA 字段没有可靠直通链；
- 材料 CSV 只提供一部分 DATA 物性，部分记录数值异常；
- 润滑剂 CSV 不能自动填充全部 rec9.7/10 模型参数；
- 保持架分析几何和 CAD 几何不等价；
- 部分轴/座尺寸继承原版经验式而非设备真实参数；
- 未建立与目标高速低载工况同次可追溯的原版 UI → DATA → 计算证据。

**这些问题不应让对话提取功能停工，但必须阻断虚假的“计算就绪”报告。**

## 8. 最小实现的文件/模块边界（建议，而非硬性目录要求）

```text
src/bearing_agent_system/
  api.py                 # 会话接口/请求响应
  conversation.py        # 一轮编排，最小LangGraph
  llm_contracts.py       # LLM结构化提取/决策合同
  models.py              # DesignBrief/ParameterValue/TurnResult
  parameter_catalog.py   # DGB 用户层参数定义/依赖
  state_store.py         # 唯一写入、revision、request_id
  checks.py              # 缺失、冲突、依赖、ready
  knowledge.py           # 只读数据/规则适配
  robas_adapter.py       # 输入模板/missing报告；不运行EXE
tests/
  test_state_store.py
  test_parameter_catalog.py
  test_turn_contracts.py
  test_conversation_policy.py
  test_recommendation.py
  test_input_readiness.py
  test_llm_real_cases.py
```

第一版可以合并其中的小文件；**不允许为了看起来模块齐全而强行创建空壳服务**。只保留一套核心 DesignBrief 数据模型；Chat history 是对话记录，不是第二套参数事实来源。

## 9. PR 分阶段实现及每步验收

| 阶段 | 做什么 | 必须演示/证明什么 | 明确不做 |
|---|---|---|---|
| 设计评审（本文件） | 冻结用户层 V1 目标、每轮循环、状态边界、动作集合、验收案例 | 用户理解并批准架构；解决文档与 PR-00 的冲突 | 不写业务代码 |
| PR-01 | 参数目录、DesignBrief、受信写入/版本最小实现 | 无 LLM 情况下能保存/修改/校验/恢复；用户未接受推荐不会变 confirmed | 不调 RoBAS、不开启复杂流程 |
| PR-02 | LLM 结构化提取 + 单轮解释 + 多轮状态更新 | 真实模型多轮能准确提取、纠错、明确未知、范围、单位 | 不做工程推荐算法 |
| PR-03 | RequirementChecker + 动态提问与回退 | 不重复问，用户打乱顺序仍合理；冲突优先澄清 | 不建立复杂规划器 |
| PR-04 | 审核配置查询、推荐包、确认/拒绝 | 有来源可审计；整体/局部接受；条件变化失效 | 不建设全量RAG |
| PR-05 | DesignBrief 汇总、阶段性确认、MissingReport、任务级 ready | draft/确认/模板准备严格区分；正确暴露 BLOCKED | 不造虚假DATA |
| PR-06（依赖 PR-00 工程证据） | DesignBrief → RoBAS 43/324 模板适配 | golden 对照、缺项阻断、五槽及依赖占位；完整协议检查 | 不运行五变量优化 |
| 未来 | 数据集联合测试/优化/求解/CAD | 独立验收后再集成 | 不提前引入 |

PR-01 至 PR-03 只需稳定的用户层合同，不应被原版 EXE 的全部工程问题无限阻断。PR-04 中任何具体推荐需要数据审查，PR-06 的 TEMPLATE_READY 必须遵守 PR-00 尚未关闭的技术阻断。若项目手册与此分阶段准入冲突，应明确报告，先由用户确认修改总控计划，不能暗中绕过。

## 10. 测试设计

详细场景及预期见 [Conversation Agent V1 验收矩阵](CONVERSATION_AGENT_V1_ACCEPTANCE.md)。重点包括：

- “高速低载”只有定性描述，不冒充具体转速/载荷；
- 一次输入多个参数，不重复询问；
- 转速未说明哪个圈转时必须澄清；
- “外圈固定”可记录 outer_speed=0，而“未说明轴向载荷”不能设 Fa=0；
- “25×52×15”有明确语境方能按 d/D/B 解析；
- D≤52 是上限，不是 D=52；
- “转速约15000”保留不确定性；
- 工作温度 vs 环境温度不可混用；
- 用户要求先解释游隙时回答问题，不强迫按问卷继续；
- 用户明确拒绝推荐、部分接受、修改转速后，相关配置需要重查；
- 没有可信润滑模型时明确受阻，不虚构已通过；
- 用户可随时查看已知、未知、待确认内容；
- 数据集与 Agent 使用同一 DGBDesignBrief 结构；不能以训练集相似表述替代真正的隐藏测试。

### 10.1 质量门槛

先建立少量手工验收的黄金场景（建议 15–20 个），再用不同表述、顺序和边界情况扩展到约 50–100 个案例。区分**确定性测试**（必须全部通过）与 **LLM 实测**（按成功率和错误类型复盘）。

指标建议：
- 禁止伪造用户确认/未知填零/擅自覆盖锁定值：关键测试 **100%** 通过；
- 用户已明确的参数提取、单位规范化：逐参数计算正确率；
- 动态追问是否针对真实缺项、是否重复提问：案例级判定；
- 推荐是否具有来源且适用：无来源时禁止宣布工程确认；
- 同样输入下的平均完成轮数：只作辅助指标，不以越少越好；
- 需求完成与 DATA 模板准备分开验收。

阈值在 PR-02/PR-03 的首轮真实模型测试后，根据黄金集的难度再冻结；不得凭空宣传已达某一成功率。

## 11. 负责人如何持续掌握项目

每次 PR 报告必须包含以下表格，并同步更新总控文档：

| 问题 | 必须回答 |
|---|---|
| 这次改什么 | 新增/修改了哪些具体文件和行为 |
| 为什么改 | 对应用户故事和当前阻断是什么 |
| 如何实现 | 关键数据流、状态写入点、函数入口 |
| 哪些还不能做 | 真实未解决问题、工程条件和依赖 |
| 测试了什么 | mock、单元、真实 LLM、真实 RoBAS 分别列证据 |
| 是否过度设计 | 是否存在可删除的 Agent、抽象层或冗余状态 |
| 下一阶段依赖 | 输入、合同、资源、用户要确认的决策 |
| 是否准入下一 PR | 明确通过/未通过，不能用“代码跑通”代替验收 |

建议项目状态只维护一个表：NOT_STARTED / IN_PROGRESS / IMPLEMENTED / TESTED / ACCEPTED；这些是**项目管理状态**，与参数确认状态不同。

目前：PR-00 只完成本机审计工件，输入工程冻结仍 BLOCKED；本文为架构设计讨论稿；PR-01 业务代码尚未开始。不要把文档创建视为功能完成。

## 12. 设计评审要先批准的事项

1. 单一 Conversation Agent + 确定性支撑服务，而不是复杂多 Agent；
2. 采用简洁 ParameterValue（true/false confirmed）和单一受信写入；
3. 最小 LangGraph 的有界回合编排，不采用无限 ReAct；
4. 采用 DRAFT / BRIEF_CONFIRMED / TEMPLATE_READY 三个任务级概念；
5. 工程配置推荐包可整体或局部确认；
6. PR-01～03 可以使用人工案例/审核数据推进，PR-06 的真实计算输入另设严格工程门槛；
7. 与数据集工作线只共享版本化 DesignBrief 协议，不让 Agent 与数据生成脚本互相依赖。

批准后再将方案拆成可以交给 Codex 的 PR-01 实施任务清单；**本次文档 PR 不实现业务代码、不自动合并，不启动下一 PR。**
