# PR-01 · DGBDesignBrief / 受信状态管理实施与验收说明

> 2026-11-23；真实 DeepSeek、ReAct、RoBAS 求解不在本 PR 范围内。PR #3 为 Draft，等待用户本地验收。

## 本 PR 实现内容

- `DGBDesignBrief/v1` Pydantic 模型：bearing、dimensions、operating、engineering、requirements、optimization_slots、solver_context；五优化槽默认 `optimize`。
- 一份数值字段目录，针对普通数值、嵌套约束和五个优化槽，统一检查原始数字证据、物理单位、基本类型，再转换为规范单位。
- `SQLiteDesignBriefStore`：每 session 一份 Brief；`set/replace`、原子批量写入、实际值无变化不增加 revision，显式关闭 SQLite 连接以兼容 Windows 临时目录。
- `DesignBriefService`：为 PR-02 工具①/②提供直接可复用的 Python 入口。
- `get_design_status`：已知、缺失、待确认、冲突；包含已生效约束的 ID 和优化槽当前值，不进行提问决策。

## PR-01 验收补丁：参数可信性与约束修改

1. **锁定/有界优化变量的单位与证据**：
   - `Dw_mm`、`Dpw_mm`：允许带有明确用户证据的长度单位换算，如 `Dw=0.8cm → 8mm`、`Dpw∈[3,4]cm → [30,40]mm`。
   - `Z` 必须为正整数且无物理单位；`fi/fo` 是无量纲数。数值范围的两个端点都需要在引用的用户原话中出现；不存在的端点不得由模型编造。
   - `precision=approximate`、或原话紧邻该数字出现“约/大约”等语义，不允许直接写入生效的 `locked/bounded`；必须由下一轮澄清或确认后再写。当前 **不额外保存优化槽的暂定估计值**。
2. **几何与数值约束**：
   - `外径不超过5.2mm` 且模型错传 `cm` 必须拒绝，不能静默保存为 `D≤52mm`。
   - 已明确表达 `≤/≥/不超过/至少/上限` 等限制的用户消息，不能被截取数字后错误写成 `D=52` 等固定尺寸。
   - 已支持的额外定量目标包括 `life_hours`（h）、`power_loss`（W）；未知字段的**数值硬约束**不允许无单位合同就直接确认为受信工程数据。
3. **约束替换和撤销**：
   - `set` 自动生成 `req-...` ID；`replace` 要求 `UpdateChange.target_id` 指定原有约束；`replace` 且 `value=null`，并具备用户撤销证据时，移除该约束。
   - 同一字段/比较符的不同上限，要求明确 `replace`，避免旧限制被一直追加。多个不同方向的约束可以同时存在。
   - 旧版本 SQLite 中缺少 ID 的约束自动补 ID 并持久化，不改变已有内容 revision；用户修改后已撤销的约束不再参与冲突检查。

## 工具输入示例

优化槽采用顶层单位：

```json
{
  "operation": "set",
  "changes": [
    {
      "path": "optimization_slots.Dw_mm",
      "value": {"mode": "locked", "value": 0.8},
      "unit": "cm",
      "precision": "exact",
      "evidence_span": "锁定Dw=0.8cm"
    }
  ]
}
```

约束采用嵌套单位；编辑时需指定受信状态返回的 ID：

```json
{
  "operation": "replace",
  "changes": [
    {
      "path": "requirements.geometric_bounds[]",
      "target_id": "req-<实际数据库ID>",
      "value": {
        "field": "dimensions.D_mm",
        "operator": "<=",
        "value": 60,
        "unit": "mm"
      },
      "evidence_span": "外径上限改为60mm"
    }
  ]
}
```

## 自动化验收

- GitHub Actions Python 3.11：最新受信修复测试结果 **85 passed**；`ruff check .` 通过；`python examples/pr01_demo.py` 通过。
- 包含数值单位/原话冲突、范围端点真实性、近似值锁定、截短证据中的比较符、上下限方向、约束替换/撤销、事务回滚、旧数据 ID 迁移以及普通零值输入。
- 本地 Windows 验收：`python -m pytest -q tests`、`ruff check .`、`python examples/pr01_demo.py`，并检查临时 SQLite 文件是否可以清理。

## 仍然不在 PR-01 范围内

- 用户自然语言的完整语义判定：简单的比较符和证据片段扫描只防明显错误，**不代表模型已完整理解句子**。复杂用户意图、指代与歧义由 PR-02 DeepSeek 多轮对话处理。
- 未经审核的专业材料、润滑剂或型号目录，不能因为格式合法就被视为工程可用。
- 系统提出的优化建议范围应在未来推荐阶段作为**待用户接受的提案**；当前不允许冒充用户输入的硬范围。
- 不构建额外 Agent、全量规则引擎、求解器调用、RoBAS 43/324 字段适配或 CAD。
- V1 同一会话串行更新，不实现分布式事务、操作级 exactly-once 或复杂恢复框架。
