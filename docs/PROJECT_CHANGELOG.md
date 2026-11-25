# 项目长期变更记录

本文件从2026-11-25本次修改开始追加记录；不补写或推测此前未留存记录。

## 2026-11-25 保持架类型退出用户层

| 日期 | PR/Commit | 修改模块 | 修改原因 | 实际变化 | 测试结果 | 项目影响 |
|---|---|---|---|---|---|---|
| 2026-11-25 | GitHub PR #7；未提交；业务基线 `2ebc001ef9a42ad1926bef26cc58497f0c6fc39a` | 用户模型、字段目录、提示词、回复标签、合同回归与架构/进度文档 | 用户明确要求删除保持架类型，保持旧会话不兼容，并同步架构 | 必需项由15减为14；保持架材料保留；删除字段不能写入或进入推荐；五优化槽、材料润滑、约束目标保留 | 完整离线pytest：197 passed，5 deselected（24.87s）；Ruff通过；真实模型与RoBAS未运行 | 计算层承担保持架构型、游隙/配合配置；当前草案不等于计算就绪；未开始后续PR |

分支：`feature/pr03-engineering-knowledge`。以上为本次未提交修改，不伪造新提交号。

文件/模块：`src/bearing_agent_system/{models,parameter_catalog,agent_prompt,reply_guard}.py`；`tests/{test_designbrief_v2_contract,test_pr02_conversation,test_pr03_recommendation_adoption}.py`；README、MASTER_PLAN、v2字段合同、架构与验收矩阵、PROJECT_MANUAL/PROJECT_CHANGELOG。新增测试验证保持架类型结构拒绝、set/replace/propose拒绝、保持架材料仍可保存及必需项为14。

验证环境：本机 `bearing-agent` Conda环境；pytest使用独立临时目录和离线模式。离线结果只说明相应确定性合同和回归通过，不代替真实LLM、多轮体验或工程验收。
