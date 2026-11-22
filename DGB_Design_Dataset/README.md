# 深沟球轴承设计任务数据集 · DGB-0001 修订版

> **当前定位：** RoBAS 数据来源已核验的合成对话测试样本；**不是**工程审核通过的轴承设计，不可作为 RoBAS 可执行输入或参数优化正确答案。
> 轴承类型：单列深沟球；单稳态工况；固定 d/D/B；Dw、Z、Dpw、fi、fo 留待优化。

## 文件组织

| 文件 | 含义 | 本版本数量 |
|---|---|---|
| `schema/DGBCase_v1.schema.json` | DGBCase/v1 及内嵌 DialogueCase/v1 JSON Schema | 1 |
| `data/design_cases.jsonl` | 含 12 组设计字段、原始 RoBAS 数据记录和来源证明的设计任务 | 1 条 DGB-0001 |
| `data/dialogue_cases.jsonl` | 不同能力测试用对话；与同一 case_id 对应 | 3 条，A/B/C |
| `review/case_review.csv` | 独立审核状态、数据源核验、已知阻断 | 1 条 |
| `README.md` | 本说明 | 1 |

仓库根目录另有一个小脚本 `scripts/validate_dgb_dataset.py`，专门执行结构、跨文件、对话来源及可选的原始数据库核验；并未增加新 Agent 或规则引擎。

## 本次具体整改

1. `dimensions.d_mm`、`dimensions.D_mm`、`dimensions.B_mm` 的确认发生在参考对话 **u02**（用户确认 25×52×15），**不是 u01**（用户只是提出 6205 型号）。现在 `source.message_id='u02'`。
2. Schema 现在约束固定尺寸、载荷、转速、温度、优化 Z 为整数或空、其它优化槽数值类型、已确认但空值等错误，并为对话增加基本结构规范。
3. 新增独立校验脚本，检查 d < D、型号/尺寸与源行一致、材料和油品名与实际快照一致、对话 ID、审核记录、模拟用户参数的来源消息。**仅 JSON Schema 通过不等于数据可信。**
4. 保留原有对话 A（专业用户直接提供参数），新增对话 B（普通用户不熟悉专业配置，先查询真实目录后选择）、对话 C（不知道轴向载荷、参数修改、跳过后补齐）。三条对话都以同一设计任务为基础。
5. 修正模拟用户的 `known_facts`，补齐载荷方向、旋转方向；新对话的预期结果比较**业务参数值**，消息 ID 在每段对话内部独立，不拿 A 的 u01/u02 作为其它对话的来源标准。
6. 明确数据的 `allowed_uses` / `blocked_uses`：目前仅用于需求 Agent 对话测试/格式与来源复核，**不能**冒充工程合格配置或优化器训练的正确方案。

## 数据来自实际 RoBAS 资源，不是凭空编造

本案例由用户提供的 `RoBAS_Resources.zip` 和原版 `RoBAS(1).zip` 核对，**原始资源本身没有提交到公开仓库**。

| 数据 | 实际来源 | 本案例的目录匹配 |
|---|---|---|
| 型号 6205、d/D/B=25/52/15 mm | `RoBAS_Resources/Data/DGBData.db` → `model` | 唯一记录 |
| 氮共渗轴承钢、工具钢 | `RoBAS_Resources/Resource/materialDB.csv` | 名称及六项原始物性一致 |
| VG32 | `RoBAS_Resources/Resource/lubricantDB.csv` | 名称及原始密度/黏温/比热数值一致 |
| StampingCage | RoBAS 原版深沟球轴承 C# 文件 | 出现实际构造代码 |

**源文件核对与工程适用性是两回事：** 尽管本版选定的两个材料与 VG32 都来自原始资源，无法据此确认“氮共渗轴承钢适合该高速滚珠”“工具钢适合冲压保持架”“VG32 在此工况能满足润滑要求”。它们是模拟用户选型，并未获得工程审批；不生成求解器缺失物性。

运行工况为**人工构造**：n_inner=15000 rpm、n_outer=0 rpm、Fr=300 N、Fa=50 N、假定工作温度 60℃；不是设备试验和已求解工况。用户希望 L10h≥20000 h 和低功耗，但本数据集没有计算所得寿命/功耗真值。

### 数据源证据

- 资源 ZIP SHA-256：`d5b072f08f3a76e283d35215e91097d88a1702e6ff5f3c6675cc726d3e73b626`。
- 6205 来源：`DGBData.db` 的 `model` 行，数据库 SHA-256 为 `4b0e9c56a4d216cf952ce13e31676c4e509130530b872d724a2dfe4c6186878f`。
- 材料 CSV SHA-256：`9e018aeced3bbe924b02c59f0761468e3558107ebdc110d943b247024e768bc1`。
- 润滑 CSV SHA-256：`4b0372b04e1d8a0b25cb8c811b9a3c3aaacbb5fae6f3f38e8b01742879606434`。
- `reference_brief.engineering.*.value` 是真正选中的目录名称；
  `robas_catalog_evidence` 嵌入**原 CSV 行文本、解析物性、单位、行号及哈希**，供复核，非只有引用。
- RoBAS 数据库当前/旧游隙表存在差异；**CN 仅为用户选择**，具体初始游隙仍为 `null`。
- k5/H7 为模拟用户的装配偏好，**尚未得到 RoBAS 配合表/工况适用性证明**。
- Solver profile 缺失、额外几何/方向映射及润滑油膜牵引模型未闭环；
  `brief_complete=false`、`robas_template_ready=NOT_ASSESSED`、`engineering_reviewed=false`、`robas_solver_verified=false` 是**刻意保留的正确状态**。

## 复现校验

需要 Python 3.11+ 和 `jsonschema`：

```bash
python -m pip install jsonschema
python scripts/validate_dgb_dataset.py --dataset DGB_Design_Dataset
```

这只能检查 Schema、来源消息、跨文件关联、已嵌入源行的自洽性，**不能实时检查 RoBAS 数据库**。要复验原始资源：

```bash
python scripts/validate_dgb_dataset.py --dataset DGB_Design_Dataset \
  --robas-archive /path/to/RoBAS_Resources.zip \
  --source-archive '/path/to/RoBAS(1).zip' --self-test
```

第二个命令会对比 ZIP 哈希、CSV 原始行及数值、DGBData.db 型号记录、C# StampingCage 源码并执行 **10 项负向错误注入测试**。源资源不可用时，**不得把离线检查当作目录再次核验**。两种检查都不等于真实 RoBAS 计算或工程审核。

## 适用测试与限制

- 对话 A：用户知道参数并明确选择材料；用于完整参数提取和确认来源。
- 对话 B：用户不知道材料润滑，先查询真实目录，再选择；**目录列举不能作为已经验证的推荐**。
- 对话 C：初始条件不明确，表示轴向载荷暂时未知，随后修订转速、补齐载荷；检验不重复追问及未知不能填零。

**重要：** 三个变体共用同一参考设计任务的业务值，但各自有独立的用户消息 ID；数据使用时按 `case_id` 分组划分训练集/测试集，避免不同变体间泄漏。

下一步若要升级为真实完整工程设计案例，需要专业人员批准材料/保持架/润滑、游隙及配合规则，落实可验证 Solver Profile，取得本工况的实际 RoBAS 计算证据。**不允许靠 AI 推断把审核状态改成 true。**
