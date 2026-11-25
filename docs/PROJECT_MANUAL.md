# 项目事实说明书

更新日期：2026-11-25。本文只记录本次核实的代码事实与验证范围；设计规范见总控和 v2 合同，不建立平行架构。

## 基线与本次状态

- 仓库：GB412/bearing_agent_system；分支：`feature/pr03-engineering-knowledge`。
- 精确业务基线 SHA：`2ebc001ef9a42ad1926bef26cc58497f0c6fc39a`。
- 当前修改：**未提交**；GitHub PR #7（用户层字段收敛，不是项目阶段 PR-07）。
- `DGBDesignBrief/v2` 保留14个必需字段：d/D/B、ni/no、Fr/Fa、Top，内外圈/钢球材料、保持架材料、润滑方式和润滑剂。
- 保持架类型、游隙、配合已从模型、白名单、缺项和推荐入口删除；知识仍可解释这些概念。
- 旧 v1/v2 会话不兼容、不迁移；使用新的数据库验证。未修改或清理旧 SQLite。

## 项目进度与完成度

| 范围 | 完成度 | 证据与限制 |
|---|---|---|
| 本次字段删除与14项合同 | UNIT_TESTED | 本地完整离线 pytest：197 passed，5 deselected；Ruff通过 |
| 单Agent、状态底座及三个工具 | IMPLEMENTED | `src/bearing_agent_system`；本次离线回归覆盖调用链，未重新验收真实模型 |
| 当前版本真实对话体验 | 待核实 | 本次未运行付费API，不能以离线 scripted model 代替真实模型验收 |
| 独立最终检查/导出和完整RoBAS适配 | NOT_IMPLEMENTED | 当前草案仍为 DRAFT_ONLY / NOT_ASSESSED |
| 计算配置工程适用性 | 待核实 | 未运行RoBAS EXE，未做工程审核 |

使用 NOT_IMPLEMENTED、IMPLEMENTED、UNIT_TESTED、INTEGRATION_TESTED、REAL_ENV_VERIFIED、ENGINEERING_REVIEWED 描述具体范围；本次不宣称达到真实模型或工程验收。

## 问题清单与后续影响

- 保持架分析构型、freeIntCls、raceFit1/2由后续计算层配置，当前用户层删除不代表其工程适用性已验证。
- 旧会话不在本次兼容范围；没有新增迁移流程。
- 当前三工具与后续独立推荐/最终导出工具按架构文档分阶段实施；不自动开始下一PR。
- 参数受信写入、推荐采纳与约束来源保护继续保留；没有修改优化算法、RoBAS、Bearing_CAD或原始资源。

相关文档：[总控](00_MASTER_PLAN.md)、[v2合同](agent/DGB_DESIGN_BRIEF_V2_FIELD_CONTRACT.md)、[架构](agent/CONVERSATION_AGENT_V1_ARCHITECTURE.md)、[变更记录](PROJECT_CHANGELOG.md)。
