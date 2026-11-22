# Bearing Agent System

面向滚动轴承工程设计的需求引导系统。当前已经实现规划文档、RoBAS 工程输入审计，以及**深沟球轴承（DGB）的结构化 DesignBrief 状态底座（PR-01 待验收）**；PR-01 和 PR-02 已先后合并到 main；PR-03 正在独立分支实现工程知识查询。

## 当前设计

**单一 Conversation Agent + 受约束的 ReAct 工具循环 + 5 个工具。** 模型自主决定问什么、怎么问、是否查询或推荐；程序负责参数可信写入、客观缺项、知识来源和最终需求检查。

| 工具 | 用途 |
|---|---|
| `update_design_brief` | 保存/修改用户事实、接受推荐及整份需求；唯一参数写入工具 |
| `get_design_status` | 仅返回已知、缺失、待确认、冲突及估计信息，不负责提问规划 |
| `lookup_engineering_knowledge` | 查询可信工程知识与依据 |
| `recommend_engineering_config` | 在当前工况下筛选经审核的候选配置 |
| `finalize_design_brief` | 检查用户层完整性，生成待用户审阅摘要，导出草案或完整需求 |

不设置独立 `confirm_recommendation`、`question_planner` 或 `check_solver_compatibility`。V1 不运行优化、RoBAS EXE 或 CAD。

## 文档入口

1. [项目总控规划](docs/00_MASTER_PLAN.md) —— 当前目标、技术边界与 PR 进度。
2. [Conversation Agent V1 架构和五工具合同](docs/agent/CONVERSATION_AGENT_V1_ARCHITECTURE.md) —— **当前唯一有效的对话架构**。
3. [DGBDesignBrief/v1 用户层字段合同](docs/agent/DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md) —— PR-01 的字段路径、类型、单位、条件必需和优化槽实施基线。
4. [ReAct 动态对话与工具验收矩阵](docs/agent/CONVERSATION_AGENT_V1_ACCEPTANCE.md) —— 包含状态事务与整体确认的真实场景。
5. [PR-00 RoBAS 输入审计](docs/pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md)、[43 记录/324 字段矩阵](docs/parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)、[数据源审计摘要](docs/pr00/DATABASE_SCHEMA_AUDIT.md)。

## 当前进度与工程边界

GitHub PR #1（RoBAS 输入审计）和 PR #2（五工具 ReAct 架构）均已合并；工程适配状态仍为 **BLOCKED**。PR-01 的参数目录、DesignBrief、原子写入、内容 revision 与简洁状态检查已实现，PR-01（GitHub #3）已合并。PR-02（GitHub #4）也已合并到 main；PR-03 正在单独分支开发。PR-02 提供单会话串行 ReAct、多轮对话与只读草案预览；`operation_key` 仅在实际重复工具写入风险出现时再实现；PR-05 才正式完成版本绑定的整份接受与导出。

DGB V1 固定外形尺寸 d/D/B，获取实际轴承载荷、套圈转速及假定工作温度，推荐/确认材料、润滑、游隙与配合，记录设计要求；Dw、Z、Dpw、fi、fo 留给未来优化模块。

工具 `finalize_design_brief` 的「需求完整」与工具①对当前摘要的「整份用户确认」是不同概念，二者均**不等于** RoBAS 43/324 输入模板可运行。材料、润滑与部分曲率/保持架映射仍有审计阻断；不编造工程数值、不将参考 DATA 默认值当成用户确认。

开发采用单 PR 验收方式；每个 PR 说明范围、实际测试、已知缺口、过度设计风险及下一阶段条件，未经授权不合并或启动后续开发。

第一版不建设 RoBAS 43/324 字段的动态工程规则引擎；这些映射与专业校验留给后续适配层。当前不实现分布式事务、复杂异常恢复或跨客户端并发控制。

## PR-01：参数模型与受信状态管理（待验收）

PR-01 的代码位于 `feature/pr01-designbrief-state`。这是可执行的结构化输入底座，不是 DeepSeek / ReAct 对话程序。

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests
python examples/pr01_demo.py
ruff check .
```

示例展示从结构化参数批量更新到 SQLite 重新读取、缺项检查；测试不调用任何外部 API 或 RoBAS。相关范围、优化范围单位与用户证据校验、约束替换/撤销及已知限制见 [PR-01 实施说明](docs/pr01/IMPLEMENTATION_REPORT.md)。没有安装 Ruff 的本地环境应如实标记未运行，不将 pytest 通过等同于 Ruff 通过。

## PR-02：真实 DeepSeek Conversation Agent（Draft，待实测）

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

终端指令 `/status`、`/brief`、`/trace`、`/new`、`/exit`；可选真实测试 `python examples/pr02_live_eval.py --max-cases 5`。**离线 CI 通过不代表真实 DeepSeek 已通过**；无凭据时必须报告真实 API 验证仍待完成。此阶段只实现两个工具、单 Agent，不提供工程推荐或 RoBAS 计算。

## PR-03：有来源的工程知识查询（开发中）

第三个 Agent 工具 `lookup_engineering_knowledge` 只读本地少量制造商资料，返回出处、适用条件和审核状态；未找到资料不编造数值。当前仅覆盖6206主要外形尺寸与CN/C3概念，不提供专业推荐或RoBAS计算。详见 [PR-03 实施说明](docs/pr03/IMPLEMENTATION.md)。
