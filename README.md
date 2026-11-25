# Bearing Agent System

面向滚动轴承工程设计的需求引导系统。当前已经实现规划文档、RoBAS 工程输入审计，以及**深沟球轴承（DGB）的结构化 DesignBrief 状态底座**；PR-01 和 PR-02 已先后合并到 main；PR-03 正在独立分支实现工程知识查询。

## 当前设计

**单一 Conversation Agent + 受约束的 ReAct 工具循环 + 当前已实现的 3 个工具。** 模型自主决定问什么、怎么问、是否查询或推荐；程序负责参数可信写入、客观缺项、知识来源和最终需求检查。

| 工具 | 用途 |
|---|---|
| `update_design_brief` | 保存/修改用户事实、接受推荐及整份需求；唯一参数写入工具 |
| `get_design_status` | 仅返回已知、缺失、待确认、冲突及估计信息，不负责提问规划 |
| `lookup_engineering_knowledge` | 查询可信工程知识与依据 |

不设置独立 `confirm_recommendation`、`question_planner` 或 `check_solver_compatibility`。独立推荐工具与最终导出工具尚未实现；当前不运行优化、RoBAS EXE 或 CAD。

## 文档入口

1. [项目总控规划](docs/00_MASTER_PLAN.md) —— 当前目标、技术边界与 PR 进度。
2. [Conversation Agent V1 架构和五工具合同](docs/agent/CONVERSATION_AGENT_V1_ARCHITECTURE.md) —— **当前唯一有效的对话架构**。
3. [DGBDesignBrief/v2 当前用户层字段合同](docs/agent/DGB_DESIGN_BRIEF_V2_FIELD_CONTRACT.md) —— 生效的新字段路径、硬约束、目标、优化槽；[v1 历史合同](docs/agent/DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md) 已归档。
4. [ReAct 动态对话与工具验收矩阵](docs/agent/CONVERSATION_AGENT_V1_ACCEPTANCE.md) —— 包含状态事务与整体确认的真实场景。
5. [PR-00 RoBAS 输入审计](docs/pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md)、[43 记录/324 字段矩阵](docs/parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)、[数据源审计摘要](docs/pr00/DATABASE_SCHEMA_AUDIT.md)。

## 当前进度与工程边界

GitHub PR #1（RoBAS 输入审计）和 PR #2（五工具 ReAct 架构）均已合并；工程适配状态仍为 **BLOCKED**。PR-01 的参数目录、DesignBrief、原子写入、内容 revision 与简洁状态检查已实现，PR-01（GitHub #3）已合并。PR-02（GitHub #4）也已合并到 main；PR-03 正在单独分支开发。PR-02 提供单会话串行 ReAct、多轮对话与只读草案预览；`operation_key` 仅在实际重复工具写入风险出现时再实现；PR-05 才正式完成版本绑定的整份接受与导出。

DGB V1 固定外形尺寸 d/D/B，获取实际轴承载荷、套圈转速及假定工作温度，收集材料、保持架材料、润滑等配置与设计要求（包括硬约束、优化目标）；保持架类型、游隙和配合不在 DesignBrief 中；Dw、Z、Dpw、fi、fo 留给未来优化模块。

工具 `finalize_design_brief` 的「需求完整」与工具①对当前摘要的「整份用户确认」是不同概念，二者均**不等于** RoBAS 43/324 输入模板可运行。材料、润滑与部分曲率/保持架映射仍有审计阻断；不编造工程数值、不将参考 DATA 默认值当成用户确认。

开发采用单 PR 验收方式；每个 PR 说明范围、实际测试、已知缺口、过度设计风险及下一阶段条件，未经授权不合并或启动后续开发。

第一版不建设 RoBAS 43/324 字段的动态工程规则引擎；这些映射与专业校验留给后续适配层。当前不实现分布式事务、复杂异常恢复或跨客户端并发控制。

## PR-01：参数模型与受信状态管理（已合并）

PR-01 的代码已合并到 `main`，历史开发分支为 `feature/pr01-designbrief-state`。这是可执行的结构化输入底座，不是 DeepSeek / ReAct 对话程序。

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests
python examples/pr01_demo.py
ruff check .
```

示例展示从结构化参数批量更新到 SQLite 重新读取、缺项检查；测试不调用任何外部 API 或 RoBAS。相关范围、优化范围单位与用户证据校验、约束替换/撤销及已知限制见 [PR-01 实施说明](docs/pr01/IMPLEMENTATION_REPORT.md)。没有安装 Ruff 的本地环境应如实标记未运行，不将 pytest 通过等同于 Ruff 通过。

## PR-02：真实 DeepSeek Conversation Agent（已合并）

PR-02 已通过验收并合并到 main。详见 [PR-02 实施与 DeepSeek 测试说明](docs/pr02/IMPLEMENTATION_REPORT.md)。

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests -m "not live"
ruff check .
$secure = Read-Host "DeepSeek API Key" -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
Remove-Variable secure
$env:DEEPSEEK_THINKING = "disabled"
python -m bearing_agent_system.chat_cli --model deepseek-flash
```

终端指令 `/status`、`/brief`、`/trace`、`/new`、`/exit`；可选真实测试 `python examples/pr02_live_eval.py --max-cases 5`。**离线 CI 通过不代表真实 DeepSeek 已通过**；无凭据时必须报告真实 API 验证仍待完成。PR-02 历史阶段只实现两个工具、单 Agent；PR-03 在此基础上增加第三个知识工具。

## PR-03：有来源的工程知识查询（开发中）

第三个工具 `lookup_engineering_knowledge(query, catalog_query=None)` 同时支持本地制造商专业知识检索（最多11条带来源记录）和可选 RoBAS 原版材料/润滑剂/型号 JSON 的精确查询。普通概念允许直接解释；语义结果为 `RELATED_EVIDENCE`，只能表示相关；无可靠相关结果返回 `NOT_FOUND`。完整 RoBAS 原始目录必须经本地授权提取，不提交 GitHub；来源含原文件哈希/行号，不能擅自猜测单位、审核状态或工程适用性。

```powershell
python -m pytest -q tests -m "not live"
ruff check .
# 下列命令需要本地环境中配置 DEEPSEEK_API_KEY，是真实付费 API 测试：
python examples/pr03_live_eval.py --model deepseek-flash --max-cases 4
```

性能硬约束与软目标的语义由 DeepSeek 在 ReAct 对话中判断，不依赖中文比较关键词的后端正则；后端仍校验字段、单位、数值与真实来源。可运行针对性付费测试：`python examples/pr03_constraint_live_eval.py --model deepseek-flash --max-cases 7`，核对硬约束、软目标、假设提问与 SQLite 实际结果。该测试不会在默认 CI 中调用 API，失败应保留真实记录再分析。

真实测试核验模型是否实际调用知识工具、是否按厂家网页引用来源、是否在数值依据不足时停止编造，以及知识查询是否保持 DesignBrief 只读。脚本保存脱敏报告到被 Git 忽略的 `artifacts/pr03_live/`；未运行真实 API 时不可宣称 DeepSeek 验收通过。当前权威文档：[PR-03 混合检索与真实验收说明](docs/pr03/HYBRID_KNOWLEDGE_IMPLEMENTATION.md)；[初版历史说明](docs/pr03/IMPLEMENTATION.md)。

首次语义模型验收需单独安装：`python -m pip install -e ".[dev,semantic]"`，然后显式运行 `python examples/pr03_semantic_smoke.py --allow-download`；此步骤可能下载模型，普通 CI 不会下载。

## PR #7：DesignBrief/v2 用户层收敛（Draft）

当前测试分支直接删除 `engineering.cage.type`、`engineering.clearance` 和 `engineering.fits`，共五条叶字段路径；保留保持架材料；`/brief`、`/status` 不再展示或追问，写入、提案及采纳均不允许这些字段。游隙与配合知识仍可只读解释；保持架分析构型与 RoBAS 模板中的固定值由后续计算适配层独立负责，本次不修改。

`schema_version` 为 `DGBDesignBrief/v2`，本次**不迁移、不兼容旧 JSON/SQLite 会话**，请使用新 SQLite 数据库运行验证。详见 [v2 字段合同](docs/agent/DGB_DESIGN_BRIEF_V2_FIELD_CONTRACT.md)。

本次本地修改的事实与验证范围见 [项目说明书](docs/PROJECT_MANUAL.md) 和 [追加变更记录](docs/PROJECT_CHANGELOG.md)。
