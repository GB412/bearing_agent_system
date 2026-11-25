# DGBDesignBrief/v1：用户层字段合同（PR-01 实施基线）

> **历史版本，已被 [DesignBrief/v2 当前合同](DGB_DESIGN_BRIEF_V2_FIELD_CONTRACT.md) 替代。** v1 中的游隙、配合字段已不在代码中。无需旧会话兼容或迁移。

> 版本：v1.0（2026-11-22）；**合同设计，不是已实现的数据模型**。与 [Conversation Agent V1 主架构](CONVERSATION_AGENT_V1_ARCHITECTURE.md) 和 [验收矩阵](CONVERSATION_AGENT_V1_ACCEPTANCE.md) 配套。  
> 只约束第一版单列深沟球轴承（DGB）、单一稳态设计工况。字段名是**建议冻结的用户层键**，RoBAS DATA 43/324 底层映射另见 [PR-00 审计](../pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md)。不要将两份字段目录混成一个。

## 1. 字段目录的用途

- 工具①按统一字段路径与类型写入，不允许自由创建未知字段；
- 工具②使用这份目录判断哪些字段“已知、缺失、待确认、冲突”，**不计划提问**；
- 工具④读取受信工况与工程配置，推荐前先检查需要的条件；
- 工具⑤检查**用户层**完整性与整份需求确认，不能代替后续 RoBASInputTemplate 的协议完整性；
- 用户打乱输入顺序、先提约束或选择锁定五变量，都应能用**同一合同**保存。

字段的必需性分为 **必需（R）/条件必需（C）/可选（O）/优化预留（OPT）/系统上下文（SYS）**。条件项由 PR-01 的简单函数判断，不构造通用规则语言。R 是当前 V1 用户层要求，不等于相应 RoBAS DATA 字段已经得到验证。

## 2. 基本字段清单

| 字段路径 | 类型 / 单位 | 必需性 | 合同规则 |
|---|---|---|---|
| `bearing.type` | 固定枚举 `DGB` | R | 只支持单列深沟球轴承；不合类型需说明不支持 |
| `bearing.application` | string | O | 保存原始场景，不凭“高速”推导具体 rpm |
| `bearing.model` | string | O | 具体型号可以通过目录核对；不能只凭型号补全用户未接受的固定尺寸 |
| `dimensions.d_mm` | number，mm | R | 必须是确定的轴承内径；不能从“轴径”无条件推断 |
| `dimensions.D_mm` | number，mm | R | 必须是确定的外径；“D≤52 mm”是边界条件而不是 D=52 |
| `dimensions.B_mm` | number，mm | R | 必须是确定的宽度，不能把“约15”直接视为已定值 |
| `operating.inner_speed_rpm` | number，rpm | R | 内圈实际转速；只知电机转速时不能擅自认为等同 |
| `operating.outer_speed_rpm` | number，rpm | R | 外圈固定由用户明确表达才是 0；未提则未知 |
| `operating.radial_load_n` | number，N | R | 当前**单个轴承**的径向载荷，不是转子总重量；以载荷大小表达 |
| `operating.axial_load_n` | number，N | R | 当前单轴承轴向载荷大小；用户明确“没有轴向载荷”才为 0 |
| `operating.temperature_c` | number，℃ | R | 明确为**假定轴承分析/工作温度**；环境温度不可替代 |
| `operating.axial_load_direction` | enum / reference | C | Fa 非零且当前输入路径需要方向/符号时才追问；坐标定义未审核不能编造正负号 |
| `operating.rotation_direction` | enum / reference | C | 当前工况/模型需要旋转方向时才要求；转速数值与方向分开记录 |
| `operating.misalignment`、`operating.moments` | typed optional | C | 用户明确给出或当前计算条件必须时收集；否则保持未要求 |
| `operating.mounting_orientation` | enum | C | 如需要重力方向或特殊安装影响才补齐 |
| `engineering.materials.inner_ring_id` | catalog id | R | 直接选择或经已审核的组合推荐确认 |
| `engineering.materials.outer_ring_id` | catalog id | R | 可与内圈相同，但不要无条件自动复制 |
| `engineering.materials.ball_id` | catalog id | R | 钢球材料单独可选 |
| `engineering.cage.type` | enum/config id | R | 保持架构型需要与选定工程配置关联 |
| `engineering.cage.material_id` | catalog id | R | 由用户或已审核推荐确认 |
| `engineering.lubrication.mode` | enum（oil/grease/other） | R | 用户想采用脂润滑是一种意图，不等于物性/求解器支持已验证 |
| `engineering.lubrication.lubricant_id` | catalog id | R（按适用模式） | 与润滑方式匹配；不能在无可信来源时虚构实际牌号 |
| `engineering.clearance.group` | enum（如 CN/C3） | C | 用户以游隙组别选方案时可保存；**组别是区间**，不是唯一数值 |
| `engineering.clearance.initial_radial_clearance_mm` | number/range，mm | C | 若按数值给初始游隙则记录；与组别不可随意当成相同语义 |
| `engineering.fits.inner_ring` | reviewed fit/config id | R | 用户自选或审核配置推荐后接受 |
| `engineering.fits.outer_ring` | reviewed fit/config id | R | 同上 |
| `requirements.constraints[]` | typed array | O | 明确约束：字段/比较/数值或表达/来源；如寿命最低要求，不假定当前模型可评估 |
| `requirements.preferences[]` | typed array | O | 如功耗越低越好；不提前设优化权重 |
| `requirements.geometric_bounds[]` | typed array | O | 如 D≤52；不得写入 `dimensions.D_mm` 确定值 |
| `optimization_slots.Dw_mm` | optimize/locked/bounded + mm | OPT | 钢球直径 |
| `optimization_slots.Z` | optimize/locked/bounded + integer | OPT | 钢球数量 |
| `optimization_slots.Dpw_mm` | optimize/locked/bounded + mm | OPT | 钢球节圆直径 |
| `optimization_slots.fi` | optimize/locked/bounded + dimensionless | OPT | 内圈沟曲率系数 |
| `optimization_slots.fo` | optimize/locked/bounded + dimensionless | OPT | 外圈沟曲率系数 |
| `solver_context.mode` | configured enum `-1` | SYS | RoBAS 拟静力学分析模式标识；不是用户问卷 |
| `solver_context.profile_ref` | reviewed profile reference/null | SYS | 未经过审核时保持 null/待验证，不填参考 DATA 的猜测值 |

**游隙的最低 V1 完成规则**：用户确认 `group` 或精确初始游隙方案中的一种，且所选方案数据来源可靠；两者均有时需检查一致性。**用户层已选择 ≠ 具体工作游隙或计算所需数值已得到**；数值映射留待专业规则及 PR-06 证明。

**配合的最低 V1 完成规则**：两套圈均有明确的配合选择或已接受的工程组合。若仅有意图“紧一些”，不视为选定配合。

**范围条件**：例如 D≤52 先保存到 `requirements.geometric_bounds`；尚未给定 D 时 `dimensions.D_mm.value=null`。不要用一个 `float` 同时表示精确值、上限、区间。

## 3. 单参数、推荐提案与五变量的形状

用户可确定字段统一包装为：

```json
{
  "value": 18000,
  "unit": "rpm",
  "confirmed": true,
  "precision": "exact",
  "source": {"kind": "user", "message_id": "turn-004"},
  "note": null
}
```

- `confirmed` 表示是否有**用户明确确定/接受**该值；不是“系统已证明工程正确”。对用户明确说“约 18000”可记录 `value=18000, precision=approximate, confirmed=false`，用于后续追问，不应满足固定计算值要求。
- `value=null` 表示未给定，不等于 `0`；原话“无轴向载荷”可支持 Fa=0。
- `source.kind` 可以是 `user/catalog/reviewed_rule/derived` 等，但系统数据的可信性使用额外的 `evidence_status/source_ref`，**不能把系统已验证误写成用户已确认**。
- 用户接受审核推荐后，所选字段的 `confirmed` 可变 true，且保存 `source_ref=proposal_id`、用户接受消息；系统底层物性不因此产生用户逐字段确认。
- `precision=range` 的内容应保存明确 `min/max` 的有界对象（例如几何约束），`precision=approximate` 保存估计数值及原始表达，不静默变 exact。
- 用户自己提出的约束/偏好也必须标记来源与是否仅是期望，不能直接混入优化器的可计算硬约束集合。

优化槽建议统一：

```json
{
  "Dw_mm": {"mode": "optimize", "value": null, "bounds": null},
  "Z": {"mode": "locked", "value": 10, "bounds": null, "source_message_id": "turn-007"},
  "Dpw_mm": {"mode": "optimize", "value": null, "bounds": null},
  "fi": {"mode": "optimize", "value": null, "bounds": null},
  "fo": {"mode": "optimize", "value": null, "bounds": null}
}
```

未锁定的槽维持待优化，不为完成需求强制要求用户填写。变量范围/锁定必须被完整保存，不可被默认优化模板覆盖。

## 4. RequirementChecker / 工具②的最小结果合同

```json
{
  "known": {
    "dimensions.d_mm": {"value": 25, "unit": "mm", "precision": "exact", "confirmed": true},
    "operating.temperature_c": {"value": 60, "unit": "degC", "precision": "approximate", "confirmed": false}
  },
  "missing": ["dimensions.D_mm", "operating.axial_load_n"],
  "pending_confirmation": ["operating.temperature_c"],
  "conflicts": []
}
```

- `missing` 仅包含本阶段真正必需却未提供**可用值**的字段；未适用的 C 项不列入。
- `pending_confirmation` 包含用户层已经有建议值、估计值、待确认推荐或已失效适用性依据的项；与 missing 允许根据具体情况区分但不能丢失信息。
- 允许 R 字段为 `known` 且同时因不够精确出现在 `pending_confirmation`；最终完成检查必须验证 exact + confirmed 等适用条件。
- **不返回**预定义问题列表、责任归属、问句优先级或计划；模型根据状态、用户当前意图和历史决定怎么问。

## 5. Tool⑤ / 完成要求（仅用户层）

`brief_complete` 检查：R 字段的可用性、条件必需项、确认状态、基本数值/几何一致性、相互冲突的要求、有来源的材料/润滑/配合选择、五槽定义齐全（允许 optimize/null），以及本版本待确认提案中不能被默认为已接受的部分。

`brief_user_accepted` 表示用户**对已展示的指定版本/摘要**进行整体接受，由工具① `accept_brief` 记录；并不自动推导自 `brief_complete`。若 revision 改变，原接受不适用于新版。

**整份确认不改变 Brief 内容 revision**：`accept_brief` 只保存独立的版本绑定接受记录，不能因为确认动作自身使刚接受的 revision 失效。用户之后实际修改任一受信参数才使原整份接受不再适用于新 revision。

草案可以随时导出且标 `INCOMPLETE`，完成版需要 `brief_complete=true`；若业务流程要求“确认完成版”，还需本版本 `brief_user_accepted=true`。工具⑤不生成 RoBAS DATA、不推断 `TEMPLATE_READY`，而返回 `robas_template_ready=NOT_ASSESSED`。

**本合同当前还存在的工程前置条件**：游隙/配合选择的具体可用组合、材料和润滑审核数据源尚未建立；它们是 PR-03/04 的内容，不允许 PR-01 靠硬编码不可信默认值补全。RoBAS 的温度/坐标/模型适用细节以 PR-00 后续审核为准。

## 6. PR-01 必须通过的最小合同测试

1. 每个 V1 字段路径存在、类型/单位/类别稳定；未知路径拒绝。
2. “25×52×15”在明确轴承尺寸语境中批量存 d/D/B；“轴径25”不能未经澄清直接写 d。
3. “外径≤52”只写范围约束，不写确定外径。
4. “约18000rpm”保存估计且不通过 exact gate；“无轴向载荷”可写确认的 0，未提 Fa 仍为 null。
5. “外圈固定”可以记录 no=0；“电机15000转”不自动写 ni。
6. 用户锁定 Z=10，其余四个槽保持待优化。
7. CN/C3 保存为组别而非唯一毫米值；如果用户给的是数值游隙，保持物理量与来源。
8. 用户要求低功耗/最低寿命，分别保存 preference/constraint，不凭空定可评估权重。
9. `get_design_status` 只返回简洁客观状态，但能保留不确定性、待确认、冲突。
10. 系统来源和用户确认分开；推荐未经用户接受不能变成 confirmed。
