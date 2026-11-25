# DGBDesignBrief/v2：当前用户层字段合同

> 生效于 PR #7。本文件取代 PR-01 的 v1 历史合同，只约束深沟球轴承 DGB 对话层的结构化需求，不是 RoBAS 的 43/324 求解输入协议。

## 1. 明确删除的字段

**直接从 DesignBrief 删除，而不是改为选填：**

- `engineering.cage.type`（保留 `engineering.cage.material_id`）。
- `engineering.clearance` 和其下的组别、初始径向游隙。
- `engineering.fits` 和其下的内、外圈配合。
- `/brief` 与 `/status` 均不展示它们；`set/replace/propose/accept/delegate` 不再接收这些字段。
- 知识工具仍可以解释这些专业概念，但不将其保存为用户参数。
- RoBAS 的保持架分析构型及模板中的 `freeIntCls`、`raceFit1`、`raceFit2` 属于后续计算模块的固定配置，不在 DesignBrief 中提供或假冒用户确认；目前工程适用性仍待验证。

## 2. 用户层字段清单

| 类别 | 字段 | 规则 |
|---|---|---|
| 轴承 | `bearing.type`，`bearing.application`，`bearing.model` | DGB 固定；应用/型号可选 |
| 外形尺寸 | `dimensions.d_mm`、`dimensions.D_mm`、`dimensions.B_mm` | 当前必需 |
| 运行工况 | `operating.inner_speed_rpm`、`outer_speed_rpm`、`radial_load_n`、`axial_load_n`、`temperature_c` | 当前必需 |
| 辅助工况 | `operating.axial_load_direction`、`rotation_direction`、`misalignment`、`moments`、`mounting_orientation` | 可选；计算前如有需要再核实 |
| 材料 | `engineering.materials.inner_ring_id`、`outer_ring_id`、`ball_id` | 保留原有配置与缺项规则 |
| 保持架材料 | `engineering.cage.material_id` | 必需；保持架类型由后续计算配置负责，不询问或写入 |
| 润滑 | `engineering.lubrication.mode`、`lubricant_id` | 保留 |
| 用户约束和目标 | `requirements.constraints[]`、`preferences[]`、`geometric_bounds[]` | 只记录用户确实给出的设计要求 |
| 优化设置 | `optimization_slots.Dw_mm`、`Z`、`Dpw_mm`、`fi`、`fo` | 默认待优化；用户可锁定或限定范围 |
| 系统上下文 | `solver_context.mode`、`profile_ref` | 系统侧，不是用户问卷 |

硬约束如最小寿命、最大外径，与优化目标如最小化功耗，均要独立保存。记录目标不代表已经具备计算对应指标的求解模块。

当前必需字段共14项：d/D/B、ni/no、Fr/Fa、Top（8项），内外圈和钢球材料（3项）、保持架材料（1项）、润滑方式和润滑剂（2项）。硬约束、优化目标及五变量槽继续保留。

## 3. 对话边界

- 用户明确提供的载荷、尺寸、转速、工作温度应受信保存；轴径不自动等于轴承内径，电机转速不自动等于内圈转速，未知不等于零。
- 允许用户先给硬约束、目标或五变量范围，顺序不固定；Agent 每轮只询问必要的 1–2 组问题。
- 材料、保持架、润滑的推荐仍有待采纳、明确授权和来源审查流程。
- 保持架类型、游隙与配合不再是必填项，不进入任何推荐提案或参数写入，也不影响对话层的缺项检查。
- DesignBrief 完成不等于 RoBAS 计算输入有效，更不等于工程校核成功。

## 4. 数据版本与测试

`schema_version = DGBDesignBrief/v2`。**不做旧 v1 JSON/SQLite 会话迁移或兼容处理**；使用新的 SQLite 数据库。旧会话负载不保证可以读取。

`python -m pytest -q tests -m "not live"` 与 `ruff check .` 必须通过。回归应验证缺失列表不含保持架类型/游隙/配合；五条被删除路径的写入和推荐均被拒绝；材料、润滑、硬约束、目标、五变量仍正常。

本次不修改 RoBAS 计算模板、计算程序或固定 profile。
