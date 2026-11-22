# PR-00：DGB RoBAS 拟静力学工程输入审计

- 日期：2026-11-20（Asia/Shanghai）；GitHub PR **#1**，项目阶段 **PR-00**，两者分别编号。
- 分支：`docs/pr-00-robas-quasi-static-input-audit`；业务基线 `02861ea09e77906f4360ed1e3e9c7268a0c9ea1f`。审计工件已提交 2b286f1c671cc581fb0027544d9b61db6554624b；提交引用在 PROJECT_CHANGELOG 追加。
- 结论：43 记录/324 字段的源码及资源盘点完成；工程输入协议冻结 **BLOCKED**，等待人工验收。没有 Agent/优化实现，没有修改原版 DATA/SQLite/EXE 或 Bearing_CAD 架构，没有开始 PR-01。
- [逐字段矩阵](../parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)、[全表结构](DATABASE_SCHEMA_AUDIT.md)。

## 1. 方法和证据边界

历史审计先阅读了当时 MASTER_PLAN、PR-00 及初始矩阵，并核对工作区与 SHA。旧项目手册/临时记录现已从本项目清理。Bearing_CAD 本机 main 为 `4460a784846d7df978579f49e8685a18da336e81`，审查时工作区干净。使用本地源码事实优先于旧迁移文档。

源码根 `D:/RotorStudio/RoBAS`；资源根 `D:/RotorStudio/ui_rotorstudio-9857bcc7afce658be15dfd2b559a55cb12b55bbd/NetLib/RoBAS_Resources`；Python 根 `D:/RotorStudio/Bearing_CAD/Bearing_CAD`。JSON inventory 保存全部 101 个实际 C# 文件、审查的 Python 文件、SQLite/CSV/EXE/DATA 路径、字节数及 SHA-256。未将商业二进制/数据库完整复制进 Git。

原版 UI 曾在 Windows 上进行只读查看（仅观察工况、润滑、材料和 solver 界面，没有保存同次输入、生成 DATA 或截图）。原版 UI 实际进程为 `C:/RollBearing/RollBearing.exe`，显示 RollBearing；源代码 AssemblyVersion=1.0.0.0。资源求解器 RoBAS_v2.exe SHA `0449dbade9f97da768961e7cd8af3277b8a6fbf2bf8a2b2c9c23784caac11829`。本机 UI 二进制与源码是否同一构建、是否确切等于“RoBAS 8.11” **BLOCKED**，不能用文件名证明版本。

静态源码提取不是执行 C#，JSON 的 source_references 是词法引用定位，可能包含注释/其他轴承/动力分支；不能单凭引用推断运行依赖。矩阵 SetAnalysisValue 限定 DGB 方法，getter/setter 与默认表达式均留证。RoBAS_v2 求解器计算核源码未提供，每个字段在求解核的实际读取/忽略条件仍 BLOCKED。

调用链：`Controls/DeepGrooveBallServer/DeepGrooveBallBearingServer.cs` 的 onPropertyValueChanged → UpdateModelInServer → UpdateMaterial/UpdateLubricant → BaseBearing.SetAnalysisValue；Analyzing → BallBearingAnalysis.Solve → DeleteFile → generateAnalysisInputTxt → generateStaticAnalysisInputs → exe/DATA.txt，再启动 RoBAS_v2.exe。`Core/MachineElement.cs` 的基类 SetAnalysisValue 为空。未触发 Solve，因为它删除并重写原版 DATA 和输出。

## 2. 字段审计与五变量

324 个字段按主来源分组：USER_INPUT=41、ROBAS_DATABASE=34（本次实为 CSV）、DERIVED=25、OPTIMIZATION_VARIABLE=5、SOLVER_PROFILE=78、REFERENCE_PROFILE_UNVERIFIED=141、UNSUPPORTED_OR_UNKNOWN=0。后者为 0 仅因每个字段均有初始化/写出位置，绝不表示语义都已确认。类别是未来输入职责；不表示现有 API 全部暴露。所有非优化字段仍需按 gate 关闭确认、适用性、单位问题；不是“其余 319 项均完整”。

|变量|DATA 物理记录/列（均 1-based）|原版赋值/精度|判定|
|---|---|---|---|
|Z|6 / 3 nRe|DGB.SetAnalysisValue:217 = Roller.RollerNum；整数；GetPltElemInd(nRe)同步输出索引|位置 VERIFIED，待优化|
|Dw|11 / 1 bReDia|同方法:227 = Roller.BallDiameter；BallRoller getter 0.001 mm，再 BReDia setter /1000|位置 VERIFIED，待优化|
|Dpw|11 / 2 pitchDia|同方法:228 = Roller.PitchDiameter；getter 0.01 mm，再 PitchDia setter /1000|位置 VERIFIED，待优化|
|fo|11 / 5 raceCurFac1|BallBearingGeometry:125 标为外圈，但 RaceCurFac1 自动属性不连接 backing；构造器:43 写 0.52；DGB 未赋此值|外圈语义/位置 VERIFIED；优化到原版写出链 BLOCKED|
|fi|11 / 6 raceCurFac2|同类:153 标为内圈，自动属性断链；构造器:44 写 0.54；DGB 未赋此值|内圈语义/位置 VERIFIED；优化到原版写出链 BLOCKED|

Python geometry_updates 用外/内沟半径除 Dw 写 fo/fi；这不是原版 DGB 的有效赋值行为。原版 OuterRace.CurFac 默认0.54、InnerRace.CurFac默认0.52，与 DATA 的0.52/0.54顺序数值不同。不能为了“和案例相同”把 fo/fi 对调。矩阵中的值是 DATA 中原样观测值，不是认可的优化结果。

其他确认的问题：BallBearingGeometry.ShimThickness1 读写 freeIntCls；DATA 仍分别序列化 shimThickness1/freeIntCls。BaseBC 的可见 Mx/My、Rx/Ry 是独立自动属性，DATA 用 appMomY/appMomZ、appMis11/21/12/22；UI 值不能直接视为对应 DATA 已更新。Rpm1 setter 同时写 rpmRange21，Rpm2 写 rpmRange12，构造器初始值不执行这些 setter，故案例 rpm2=20000 与 rpmRange12=0 可以并存。温度转换实际由 RoBAS.Utility.MathMethod 实现（Utility/MathMethod.cs:100/110），C→K加273.15，K→C减273.15；Lubricant 自己的黏温公式明确用273。最初将此项误记为缺外部实现，已补查并追加更正。

## 3. 数据库与保持架依赖

见 DATABASE_SCHEMA_AUDIT：7 个资源 SQLite 文件逐表实读；材料/润滑实际来自 CSV。材料选择只覆盖六项物性；4 个完整材料记录各6项+轴/座各5项，共34个 DATA 字段。rec8.6、strainLimit/hardness/wearCoeff/misis 等没有 CSV 查询来源。Lubricant 名称与黏温曲线存在，但未找到向 DATA 模型参数自动传值的调用。

DGB.SetAnalysisValue 分析保持架新建 StraightPocketCage，而 CAD 对象 Cage 是 StampingCage。StraightPocketCage 构造器按 public mm getter 顺序：pocket=round(1.004*Dw+0.12,1)，guideGap=0.6*(pocket-Dw)，OD=round(outerSidewall-guideGap,2)，ID=round(OD-0.6*Dw,2)，width 由 CalculateWidth 后 round(...,2)。外/内间隙、BPocCls1、两组 guide 随该几何派生，再通过 /1000 setter。guide clearance 依赖 InnerRace.OutsideDiameter；不是仅凭 d/D/B 可确定。d/5 和 D*1.14 是该源码构造分析轴/座的规则，未经用户安装条件确认，不可作为通用工程恒等式。

## 4. 实际 DGB 案例及逐字段比较

原始留存路径 `D:/RotorStudio/Bearing_CAD/Bearing_CAD/build/robas-solver01-acceptance-20261108/real-DGB/run-85ffea6353a545bc822c50a2b3ced583/DATA.txt`，SHA `b6610d150b0b8b05f0d024fe0c6fb90c1d4b270d5ef20f95398d48a6aa165a0f`。这是本机留存案例，本次未重新由 UI 生成；2026-11-08 的生成来源来自历史迁移文档，原始同次 UI 配置/截图和完整生成过程无法独立重建，标 BLOCKED。

43 条记录、标签顺序、每列数目全部与 C# 静态序列化及 Python 布局核对，324 个原始值逐字段列入矩阵。序列化位置是一致证据；材料恰好等于构造器或 CSV 记录，不证明当时选了哪个记录。记录内容 d40/D68/B15 mm、Z11/Dw8.334/Dpw54 mm，外/内挡边59.02/49 mm；Fx4500/Fy0/Fz2000 N；外圈0/内圈20000 rpm；各温度323 K。不能将其认定为目标高速低载工况，更不能认定工程合格。

独立公式追踪得到 pocket8.5、guideGap0.0996、cage OD58.92/ID53.92/width11 mm；CageCls2=4.92、pocket clearance0.083、guide width2.42/pos5.5/clearance4.92 mm，与案例对应项一致。完整数值回读与 roundtrip 对比见测试。原版构造器曲率0.52/0.54与 CAD 沟道曲率模式不是等价输入。没有宣称324项均可从用户需求独立重建。

## 5. Bearing_CAD builder/API 能力审查

`bearing_cad/robas_data.py` DataDocument.parse 验43行/标签/每列/有限数值、Mode=-1、kUnit/kBrg；render 输出CRLF，保留数值token；read记录原文件SHA。没有逐字段来源/确认语义或工程适用性校验。

`robas_ball_input.py` BallDataDocument、geometry_updates、update_ball_data 可复用：显式 reference_data、geometry_mode（legacy_data/cad_geometry）、几何冲突显式确认、分析内圈OD、工况/材料/润滑覆盖、五项 analysis_parameters_mm、速度setter联动。仍强制先读完整 profile；空模板/缺失字段不能直接解析。solver_updates只允许nStps。底层 operating/material/lubricant 字段 override 允许范围见 robas_data.profile_overrides；提供接口不代表请求方有可信值。

`robas_analysis.py` _CONDITIONS 仅 load_x/y/z_n、outer/inner_speed_rpm，另 free_clearance_mm；_MATERIAL_VALUES 仅6项（轴/座5项）、_CAGE_VISCOSITIES仅pocket/guide且模型码=2，solver仅load_steps。load_analysis_profiles要求operator manifest中的ID、source、SHA、相对路径；_check_reference校验哈希与固定输出文件名；隔离运行保留输入哈希及inherited/effective工况。这能追踪profile身份，不能表达用户逐字段确认。operating_conditions可为空、继承被报告，但仍可能运行。

未独立生成项：全部未覆盖 solver/控制标志、寿命/接触属性、剩余材料属性、润滑牵引/油膜、温度、力矩/错位、配合、热边界/扫描/初值/重力及未覆盖保持架模型字段等，逐项见矩阵。run_analysis拒绝显式 CAD cage（request.cage非空）；analysis_geometry强制inner_race_od_mm。不能仅扩展对话问题就宣称这些数据链已实现。

后续接口建议仅为审计产物：显式字段级 source/confirmation/dependency 输入；缺项返回对象；与已锁定 profile 的允许继承清单；单位转换和构建分离；在新项目的唯一受信写入模块维护确认状态与版本。不要照搬旧项目的 StateManager 或所谓旧 PR-01 契约；由新的 Conversation Agent 设计决定最小实现。

## 6. 未来对话必须问、可查询、可派生

|职责|必需内容 / 条件|缺失处理|
|---|---|---|
|用户固定边界|DGB、d/D/B；额外分析挡边、内圈OD、实际轴/座尺寸及安装结构|缺失返回具体字段；d/D/B不能代替分析几何|
|用户运行条件|带坐标定义的载荷、力矩/位移控制和约束、外/内圈转速、重力方向；零值也需明确来源|坐标/符号未确认即BLOCKED；UI假连接项不可默认为已设置|
|用户安装与热边界|游隙、外圈间隙/内圈过盈、温度及温标、错位/残余应力、冷却/流量/压力/HTC等适用条件|用户不知道时只能推荐可溯源配置，接受前unconfirmed|
|工程配置选择|滚动体/内外圈/保持架/轴/座材料；润滑剂与模型；保持架构型、分析profile适用范围|选择名称不足以填寿命及模型参数；需审核profile或工程输入|
|自动查询|确定版本CSV中的六项材料物性/润滑基础曲线；SQLite型号及确实存在的几何规则|保留DB/CSV哈希、自然键/主键、列、原始单位；缺行/重名/异常值失败|
|确定性派生候选|经审核的getter单位链、保持架/分析几何公式、输出元素索引；黏温物性仅在公式适用性审核后|记录公式版本、输入依赖；上游变化失效；依赖优化量则保持待计算|
|受信系统配置|Mode/kUnit/kBrg、数值步长/控制开关/输出命名等审核profile|不让用户凭空提供内部码；没有适用profile则BLOCKED|
|仅设计上下文|应用、工况周期、精度/密封/成本偏好及寿命/应力/温升目标|记录需求来源；不得虚构对应DATA字段或审核阈值|

## 7. 输入完整性 gate（规范，尚未开发）

模板对象使用明确 field ID=(record_index,field)、value=null、source_kind/source_ref、unit、confirmed/unconfirmed、dependency/formula版本；五优化槽保留null及OPTIMIZATION_VARIABLE。OPT_PENDING不是第三种业务确认状态。RoBAS DATA不支持null占位：有任何缺项时禁止序列化可执行DATA；不能写空串、零或profile旧值来占位。

TEMPLATE_READY必须：43记录/324字段身份与顺序固定；非优化必需输入有限/单位/来源明确；用户可决定值全部confirmed；受信系统值有审核规则版本；profile有ID/SHA/逐字段允许继承清单及适用性确认；CSV/DB有哈希/记录键/列/单位/转换；派生值有公式及完整依赖；无冲突/BLOCKED。依赖五变量的派生项可在模板阶段标明待优化依赖，但不能声称已得到数值；RUNNABLE_READY还要求五变量及全部依赖已填并重算、取整/枚举/数组/模型条件校验通过。

所有324个协议位置必须在RUNNABLE阶段有可溯源值，即使某模式忽略该字段也须有经审核的固定编码；在缺求解核文档时不自行省略。未来负面检查至少包括：空/NaN/Inf、单位不明、坐标不明、未确认零值、未知/重名材料、缺物性、profile哈希变化、模型码与物性/温度不符、nRe索引不符、几何/配合冲突、旧依赖未失效、曲率/垫片自动属性断链。缺项报告须列 field ID、原因、缺失来源、所需行动；任一阻断状态为INCOMPLETE。序列化或预校核通过不代表收敛、外部求解性能验证或工程验收。

## 8. 自审问题清单与准入

|ID|未解决问题 / 影响|状态 / 所需证据|
|---|---|---|
|B01|UI二进制/源码/RoBAS8.11构建身份|BLOCKED：需版本或构建可追溯证明|
|B02|fo/fi backing不同步及ShimThickness1错误；Mx/My/Rx/Ry与DATA断链|BLOCKED：工程人员明确采用的映射策略；本PR仅报告，不修原版|
|B03|求解核每字段读取、枚举条件、未注单位与坐标符号|BLOCKED：原版协议手册/计算核源码/受控单变量实验|
|B04|材料寿命/接触属性、异常CSV值、推荐适用性|BLOCKED：可靠材料证书/标准版本及专业审核|
|B05|润滑CSV与rec9.7/10的有效传值规则、热边界模型|BLOCKED：明确公式/单位/模型数据及适用性审核|
|B06|目标高速低载案例及同次UI配置-生成DATA证据|BLOCKED：现留存仅默认工况；本次未运行覆盖原版数据的Solve|
|B07|分析保持架与CAD保持架一致性、额外几何及轴座假设|BLOCKED：工程profile与安装/结构输入确认|
|B08|温标转换曾误记为缺外部源码，现已补查|CLOSED_SOURCE_CHECK：Utility/MathMethod.cs:100/110，±273.15；静态回归检查通过，不等于UI构建已验明|
|B09|当前Python API逐字段确认/来源不完备|NOT_IMPLEMENTED；后续PR范围待本次人工验收|
|B10|API pytest缺cadquery；当前环境为Python3.14|BLOCKED：完整CAD测试环境；不安装/重构本次范围外依赖|

验收自审：43/324完整性、每字段源码/初始化/属性/案例定位、数据库实际结构与来源、Python覆盖范围、确认gate已记录。单位/分支/五变量有效写入链/真实目标案例仍有上述阻断，故不勾选“工程协议冻结/原版UI同次生成闭环已通过”。历史审计工具检查 14 passed，Bearing_CAD 球轴承输入相关单元测试 23 passed；完整 API 测试因缺少 cadquery 无法收集。本轮无 EXE 实测；原始一次性采集工具/工件已从本仓库清理，测试记录仅供追溯。PR-00完成度为UNIT_TESTED（审计工件一致性）；完整工程输入链NOT_IMPLEMENTED；REAL_ENV_VERIFIED仅限本机UI只读观察与数据只读检查，不扩展至求解；ENGINEERING_REVIEWED未达到。本 PR-00 的工程冻结仍未达到，**不得将其当作已通过工程协议验收**；是否合并本审计 PR 须经负责人另行判断。2026-11-22 准入澄清：**用户层 PR-01～02（字段模型及 ReAct 对话）可在架构文档验收、用户授权后独立推进**，不需要先关闭全部 RoBAS 工程阻断；但 PR-06 的 RoBASInputTemplate 适配及 TEMPLATE_READY 必须继续满足本报告要求。本次澄清不代表自动授权开发或合并。
