# PR-01 · DGBDesignBrief / 受信状态管理实施与验收说明

> 2026-11-22 · 代码实现阶段；真实 DeepSeek、ReAct、RoBAS 求解均不在本 PR 范围内。

## 实现内容

- `DGBDesignBrief/v1` Pydantic 模型：用户层 bearing、dimensions、operating、engineering、requirements、optimization_slots、solver_context；优化五槽默认 `optimize`。
- 单一字段白名单与数值/单位规范化；未知字段和系统保留字段禁止模型修改。
- `SQLiteDesignBriefStore`：每个 session 一份 Brief，结构化 `set`/`replace`、单次批量原子提交、无实际变化不增加 revision，短 SQLite 事务。
- `DesignBriefService`：后续工具①、工具②可以直接调用的 Python 业务入口。无需 LangGraph 即可调用。
- `get_design_status`：只返回 known/missing/pending_confirmation/conflicts；不生成问句和优先级。
- 工程数据不默认填充。五变量留给未来优化；最终完整性/整份确认/推荐与知识查询不在此 PR 实现。

## 自动化验证

- `pytest -q tests`：实际结果以 PR 审查时输出为准；测试涵盖空任务、批量更新、更新回滚、来源、零值、估计、单位、约束、游隙、Z 锁定、重启持久化、非法几何和未知字段。
- `python -m examples.pr01_demo`（或在仓库根目录运行 `python examples/pr01_demo.py`）：显示写入结果、缺项、重新打开 SQLite 后的 Brief。
- `python -m compileall -q src tests`：基本语法检查。

## 明确限制及后续 PR

- PR-01 接受**结构化**参数，不独立解析用户自然语言；语义识别/缺字段检测/真实 DeepSeek 多轮测试从 PR-02 开始。`evidence_span` 的字符存在性与少量显式负面规则**不能证明完整自然语言语义正确**。
- 用户确认推荐与整份 Brief 需要实际提案和可验证摘要，分别留给 PR-04/05。
- 材料/润滑的目录 ID 目前是用户选择的标识，不等于数据可用或经过专业审核。
- 没有 RoBAS 43/324 字段映射、真实求解器调用或 CAD。
- 单进程单会话串行是 V1 目标；无操作级幂等日志表、分布式事务或断点恢复平台。
- 完整 `ruff check .` 在有 Ruff 的标准开发/CI 环境执行；本地缺 Ruff 时不冒充通过。
