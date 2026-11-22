# RoBAS 数据资源审计结论（精简版）

> 2026-11-20 原版 C#、7 个 SQLite、材料/润滑 CSV 的**历史只读审计摘要**。原始全表结构和临时采集 JSON 已从本 Agent 仓库当前分支移除；该摘要不是工程批准。需要完整表结构时应在授权的本地 RoBAS 资源中重新查询。详情见 [PR-00 审计报告](PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md)。

## 数据源实际分工

| 资源 | 原版代码入口 | 内容与边界 |
|---|---|---|
| `Resource/materialDB.csv` | `Controls/MaterialServer.cs` → `FileIO.Csv2DataTable` | 审计时 13 条材料记录；选材名称匹配，基础 6 类物性 |
| `Resource/lubricantDB.csv` | `Controls/LubricantServer.cs` → `FileIO.Csv2DataTable` | 审计时 31 条润滑剂记录；密度、黏温点和热参数等 |
| `bearing.db`、`DGBData.db` 等 SQLite | `Utility/DataBase/DBConnection.cs`、`DataControl.cs` | 轴承型号、几何尺寸、设计标准/工艺相关数据，不是材料/润滑物性主来源 |
| 其他 SQLite | 同上，审计时共实读 7 个 SQLite 文件 | 属于原版相关型号/二维设计资源；V1 对话不引入全部工程图表 |

原版 SQLite 资源与本机安装资源可能存在版本/哈希差异，不能凭文件名认为一致。**禁止在本仓库上传原始数据库、商业依赖或未经授权的源码片段。**

## 材料 CSV 字段（历史审计）

| 原始列 | 映射属性 | 单位 |
|---|---|---|
| materialName | Name | 文本，自然键，不是 SQL 主键 |
| elsaModules(Pa) | ElasticModules | Pa |
| density(kg/m3) | Density | kg/m³ |
| heatConductivity(w/m/k) | Conductivity | W/(m·K) |
| linearExpan(1/k) | ThermalExpansion | 1/K |
| poisson | PoissonRatio | 无量纲 |
| specificHeat | SpecificHeat | J/(kg·K) |

**限制：** 原版 CSV 不覆盖 `strainLimit`、`hardness`、`wearCoeff`、`misis` 和 rec 8.6 相关全部字段；不能因用户选择材料名就认为材料 DATA 已完整。审计记录中若干材料行的导热率/泊松比存在明显异常，必须核对来源和单位，不允许自动修正或用作可信默认推荐。

## 润滑 CSV 字段（历史审计）

| 原始列 | 映射属性 | 说明 |
|---|---|---|
| oilName | LubricantName | 文本名称键 |
| density0 / slopeDensity | Density0 / SlopeDensity | 密度截距与温度系数 |
| t1(degC),t2(degC) | T1,T2 | 给定温度 ℃ |
| v1(m^2/s),v2(m^2/s) | Nu1,Nu2 | 运动黏度 m²/s；界面可能以 mm²/s 展示 |
| specificHeat0(J/kg/degC),slopeCp | SpecificHeat0,SlopeSpecificHeat | 比热容及温度系数 |

`Core/Lubricant/Lubricant.cs` 实现温度相关密度/比热/黏度计算，相关公式与温度范围仍需核实适用性。没有证据证明选定润滑油后会自动填写 DATA 中 rec 9.7/10 全部牵引、油膜、黏度字段。

## 给 Conversation Agent V1 的直接结论

1. 型号（可选）可以查询经核对的 DGB 尺寸数据；用户仍须确认 d/D/B，不能把型号自动等同全部内部几何。
2. 材料和润滑采用**少量经审核的组合配置 + 用户整体/局部确认**，不把 CSV 当作可靠工程规则库。
3. 底层六项材料物性由可信数据源/适配器生成，不要求用户逐项填写；缺少的物性由 MissingReport 报告。
4. 游隙、配合和标准值不能仅因 SQLite 表里有数就随意推荐；具体表版本、适用范围和规则待审核。
5. RoBAS `REFERENCE_PROFILE_UNVERIFIED` 字段不得被静默继承并称为已确认。
6. PR-00 的 43 条记录/324 字段技术映射保留在 [字段矩阵](../parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)；原始 C#、数据库和生成脚本不作为新 Agent 仓库源码管理。

**证据等级：** 源码/数据库只读审计和历史测试记录；不是同次 UI → DATA → EXE 成功求解证据，不是制造审核。
