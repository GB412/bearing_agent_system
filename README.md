# Bearing Agent System

面向滚动轴承工程设计的需求引导系统。当前仅实现规划、审计和**单列深沟球轴承（DGB）Conversation Agent V1** 的方案设计，Agent 业务代码尚未开发。

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

GitHub PR #1 记录 DGB RoBAS 拟静力学字段审计（工程协议仍 **BLOCKED**）；PR #2 是当前五工具 ReAct 架构文档，均尚未合并。下一步 PR-01 为参数目录、DesignBrief、唯一受信写入、同轮操作级幂等和简洁状态检查，**尚未开始**。PR-02 提供多轮 ReAct 与只读草案预览；PR-05 才正式完成版本绑定的整份接受与导出。

DGB V1 固定外形尺寸 d/D/B，获取实际轴承载荷、套圈转速及假定工作温度，推荐/确认材料、润滑、游隙与配合，记录设计要求；Dw、Z、Dpw、fi、fo 留给未来优化模块。

工具 `finalize_design_brief` 的「需求完整」与工具①对当前摘要的「整份用户确认」是不同概念，二者均**不等于** RoBAS 43/324 输入模板可运行。材料、润滑与部分曲率/保持架映射仍有审计阻断；不编造工程数值、不将参考 DATA 默认值当成用户确认。

开发采用单 PR 验收方式；每个 PR 说明范围、实际测试、已知缺口、过度设计风险及下一阶段条件，未经授权不合并或启动后续开发。
