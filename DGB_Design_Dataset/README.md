# DGB 设计任务数据集 / 实际 RoBAS 资源核验样例（1 条）

本包采用 5 个文件：
- `schema/DGBCase_v1.schema.json`：案例和核心 DesignBrief 字段结构的 JSON Schema（Draft 2020-12）。
- `data/design_cases.jsonl`：1 条 `DGB-0001` 设计案例，含 12 组需求字段与实际核验的 RoBAS 资源原始记录及解析物性。
- `data/dialogue_cases.jsonl`：与 DGB-0001 对应的 1 条 9 消息参考对话。
- `review/case_review.csv`：1 条逐项数据来源/审核记录。
- `README.md`：格式说明与校验边界。

## 关键校验完成了什么

实际读取用户提供的 `/mnt/data/RoBAS_Resources.zip`：
- 资源包 SHA256：`d5b072f08f3a76e283d35215e91097d88a1702e6ff5f3c6675cc726d3e73b626`
- `Data/DGBData.db`：精确 SQL 查询表 `model`、`model='6205'`，唯一行 `(6205,25,52,15,1.0)`，匹配外形尺寸。
- `Resource/materialDB.csv`：严格名称匹配 `氮共渗轴承钢`、`工具钢`，逐字段复读原始6项物性，未创造 GCr15 ID。CSV SHA256：`9e018aeced3bbe924b02c59f0761468e3558107ebdc110d943b247024e768bc1`。
- `Resource/lubricantDB.csv`：严格名称匹配 `VG32`，逐字段复读原始8项数值；CSV SHA256：`4b0372b04e1d8a0b25cb8c811b9a3c3aaacbb5fae6f3f38e8b01742879606434`。
- 原版 `RoBAS/Core/BallBearing/DeepGroveBallBearing/DeepGrooveBallBearing.cs`：实际出现 `StampingCage` 构造。
- 基础数值合理性检查：材料弹性模量、密度、导热率、热膨胀系数、泊松比、比热容在宽泛正值/基础物理范围；油的两温度及黏度满足正值和温度排序。**这不是专业审核，不是对材料品种是否适用于滚珠、保持架的批准。**
- JSON Schema 校验、选用自然键唯一性和原始行完全一致性通过；`case_id` 与 `dialogue_id` 的交叉引用通过。

## 案例里是实际的材料、润滑数据，不再只是待查引用

在 `reference_brief.engineering` 中：
- `materials.inner_ring_id.value = '氮共渗轴承钢'`，`outer_ring_id.value = '氮共渗轴承钢'`，`ball_id.value = '氮共渗轴承钢'`；
- `cage.material_id.value = '工具钢'`；
- `lubrication.lubricant_id.value = 'VG32'`。
这些**真实名称**可直接用于用户展示/Agent 确认。`robas_catalog_evidence.materials` 和 `.lubricants` 同时**嵌入对应原始行与物性值、单位、CSV行号、SHA256**，无需下游先猜测名称或重新查找才看得到数据。未来真正写求解器时仍应以选定版本验证当前资源未变化。

## 不能宣称已验证的事情

- `氮共渗轴承钢`用于钢球、`工具钢`用于冲压保持架，是**合成用户选择**；只是确实存在于本版 RoBAS 材料库，不表示制造或高速工作适用性已确认。
- 运行条件 Fr=300 N、Fa=50 N、ni=15000 rpm、温度 60℃ 是合成设计任务，**没有** RoBAS 实际计算结果。
- `VG32` 是本版 RoBAS 油库的准确名称，不是某个品牌商品；暂不推算 60℃ 下的精确黏度，也不推断 rec9.7/10 的牵引/油膜参数。
- 初始游隙采用用户组别 `CN`，但原库 `DGBData.db` 的 `游隙` 与 `游隙_旧）` 在 `d=30` 行的 `0_B/0_S`、`3_B/3_S` 不一致，查表优先级及单位尚未工程冻结，因此不选定数值，初始游隙保持 null。
- `k5/H7` 是模拟用户的配合要求，不是已验证的 RoBAS 数据库 ID。保留用户需求，但适配器不能直接把它当成已审核的过盈量。
- `6205` 原库 `主参数` 表含参考钢球直径、球数、节圆直径；仅作为参考来源记录，**五个优化变量仍全部 null**。
- `confirmed: true` 只表示模拟用户明确选择/接受这些值；`engineering_reviewed: false`、`robas_solver_verified: false`、`brief_complete: false` 表示尚不能宣称完整工程设计或可求解 DATA。

## 数据集与 Agent 的衔接

用户层字段与现有 `DGBDesignBrief/v1` 合同一致：
https://github.com/GB412/bearing_agent_system/blob/docs/conversation-agent-v1-architecture/docs/agent/DGB_DESIGN_BRIEF_V1_FIELD_CONTRACT.md

- 一个 `design_case` 对应 1 条完整记录，一个 `case_id` 可对应多条不同难度的 `dialogue_case`。
- 数据集的 `robas_catalog_evidence` 是**案例层审核快照**，不是新 Agent 必须向普通用户询问的字段。以后可由独立评测程序使用快照检查推荐材料名、数值、来源及模型完整性。
- 严格区分**数据库命中校验、基础数值检查、工程适用性审核、真实 RoBAS 求解验证**四个不同层次。
- 本样例只是数据格式和来源核验样本，不属于“工程已审通过的完整方案”；批量生成前应先确定至少一套经工程审核的可推荐配置，否则只能生成目录存在、待专业审核的案例。

## 复核方法（在用户本地有同一资源包时）

核对模型：`select model,d,Dd,B,rsmin from model where model='6205'`；材料按 `materialName` 严格匹配；润滑按 `oilName` 严格匹配。比较 `robas_catalog_evidence` 中的 `raw_row` 与原 CSV 行，并校验文件 SHA256。此包**没有重新分发完整 RoBAS CSV/SQLite 或商业源码**，只保存所选原始记录的快照。
