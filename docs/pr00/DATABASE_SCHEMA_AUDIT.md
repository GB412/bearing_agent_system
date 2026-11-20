# 原版数据资源实际结构

2026-11-20，只读 SQLite URI `mode=ro&immutable=1`，未执行 DDL/DML。数据库无独立单位元数据时不得按列名猜单位。以下为资源包版本；运行安装目录的哈希另见 evidence/audit.json，不能混用版本。

材料不是 SQLite 表：`Controls/MaterialServer.cs` 类 `RoBAS.MaterialServer` 构造器读取 `Application.StartupPath/Resource/materialDB.csv`，`retrieveMaterialsFromCsv` → `FileIO.Csv2DataTable`，`GetMaterialByNameFromDataTable` 按 materialName 精确选择首条，再按列序映射 6 个属性。CSV 无 SQL 主键；必须检查名称唯一且记录存在，禁止沿用原版 catch 后返回默认 Material 的行为。

润滑同样来自 `Controls/LubricantServer.cs`，`GetLubricantByNameFromDataTable` 按 oilName，列序映射 Density0,T1,Nu1,T2,Nu2,SlopeDensity,SpecificHeat0,SlopeSpecificHeat。CSV 无 SQL 主键。CSV 作者、标准版本、测量依据及工程适用性 BLOCKED；文件存在不等于物性可靠。

`Utility/DataBase/DBConnection.cs` 的 GetConnection/GetDGBDataConnection/GetACBDataConnection/GetCRBDataConnection 分别连接 bearing.db/DGBData.db/ACBData.db/CRBData.db。`DataControl` 查询 bearing_type、table_design、bearing_design 及尺寸表，DGB 的 model 为型号几何数据。未发现 MaterialServer 或 LubricantServer 使用这些 SQLite 连接；不能把几何库当材料/润滑库。

CSV materialDB.csv：13 行；materialDBDefault.csv：13 行；lubricantDB.csv：31 行；lubricantDBDefault.csv：30 行。完整表头、样本、编码、SHA 在 evidence/audit.json 的 csv 节。

|materialDB.csv 列|Material 属性 / DATA backing|单位 / 限制|
|---|---|---|
|materialName|Name；只用于选记录|文本，自然键，非数据库 ID|
|elsaModules(Pa)|ElasticModules → elasticModules|Pa|
|density(kg/m3)|Density → density|kg/m³|
|heatConductivity(w/m/k)|Conductivity → conductivity|W/m/K|
|linearExpan(1/k)|ThermalExpansion → thermalExpansion|1/K|
|poisson|PoissonRatio → poissonRatio|无量纲|
|specificHeat|SpecificHeat → specificHeat|J/kg/K，Material 属性标注|

案例候选“渗碳轴承钢”六项为 1.90E11、7870、30.5、1.10E-6、0.29、837，与案例数值一致；无法据此反证该案例当时执行过数据库选择。strainLimit/hardness/wearCoeff/misis 及 rec 8.6 全部不在这 6 列映射内，由构造器初始化；不能随材料名自动认定正确。高碳铬轴承钢条目中 conductivity=3.50E-05、poisson=3.60E-07 等需工程复核，禁止自动修正、推荐或冒充标准数据。

|lubricantDB.csv 列|Lubricant 属性|单位 / 限制|
|---|---|---|
|oilName|LubricantName|名称自然键|
|density0|Density0|kg/m³，温度截距|
|t1(degC),t2(degC)|T1,T2|℃|
|v1(m^2/s),v2(m^2/s)|Nu1,Nu2|m²/s，UI 显示 mm²/s|
|slopeDensity|SlopeDensity|密度对℃斜率；CSV无额外元数据|
|specificHeat0(J/kg/degC)|SpecificHeat0|J/kg/℃，温度截距|
|slopeCp|SlopeSpecificHeat|比热对℃斜率|

`Core/Lubricant/Lubricant.cs` 的 GetDensity(T)=T*SlopeDensity+Density0；GetSpecificHeat(T)=T*SlopeSpecificHeat+SpecificHeat0；GetDynamicViscosity(T)=GetKinematicViscosity(T)*GetDensity(T)。GetKinematicViscosity 使用 t=T+273、ν*1e6、shift=0.7（min(v1,v2)<0.3 时 0.95）、双对数拟合。此为源码事实，非审核公式；温度范围/物理有效性 BLOCKED。这些方法没有被 BallBearingAnalysis.generateStaticAnalysisInputs 调用来填 rec 9.7/10；pocVis/gsVis、牵引和油膜仍是构造器值。禁止从“选了 VG32”推断所有 DATA 润滑配置已经完整。

## SQLite 全表清单

每列格式 `名称:声明类型:pk序号`，完整 DDL、NOT NULL、DEFAULT 和逐表行数均见 JSON。无单位元数据列标为 BLOCKED；不承诺不存在独立资料。

### ACBData.db

SHA-256 `633bc2ccdfdb4836d22ace8f19dea591e1b932a89606291958343adb24a2af23`

|表名|行数|列与主键（单位 BLOCKED）|
|---|---:|---|
|B级内圈技术条件|10|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|B级外圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|B级总图内圈技术条件|11|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|B级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|B级粗糙度表|11|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|C级内圈技术条件|9|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|C级外圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|C级总图内圈技术条件|10|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|C级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|C级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|D级内圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|D级外圈技术条件|14|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|D级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|D级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|D级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|E级内圈技术条件|13|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|E级外圈技术条件|15|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|E级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|E级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|E级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|G级内圈技术条件|13|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|G级外圈技术条件|15|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|G级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP9:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|G级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|G级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|fc_f0|41|Dw_Dpw:REAL:pk0; fc:VARCHAR(20):pk0; f0:VARCHAR(20):pk0|
|model|139|model:VARCHAR(50):pk1; d:REAL:pk0; Dd:REAL:pk0; B:REAL:pk0; B2:REAL:pk0; T:REAL:pk0; rsmin:REAL:pk0; r1smin:REAL:pk0; alfa:VARCHAR(50):pk0|
|主参数|16|model:VARCHAR(50):pk1; Dw:VARCHAR(20):pk0; Z:VARCHAR(20):pk0; Dwp:VARCHAR(20):pk0; fai:VARCHAR(20):pk0|
|倒角尺寸表|25|rsmin:REAL:pk0; d:INTEGER:pk0; rsmax_r:REAL:pk0; rsmax_a:REAL:pk0; rs_r:VARCHAR(255):pk0; rs_r_Upper:VARCHAR(255):pk0; rs_r_Lower:VARCHAR(255):pk0; rs_a:VARCHAR(255):pk0; rs_a_Upper:VARCHAR(255):pk0; rs_a_Lower:VARCHAR(255):pk0; r3:VARCHAR(255):pk0; r3_Upper:VARCHAR(255):pk0; r3_Lower:VARCHAR(255):pk0; r8:VARCHAR(255):pk0; r8_Upper:VARCHAR(255):pk0; r8_Lower:VARCHAR(255):pk0|
|冲压统一图册|37|model:VARCHAR(50):pk1; S:REAL:pk0; Bc:REAL:pk0; Dc2:REAL:pk0; Dc:REAL:pk0|
|变量|203|变量名:VARCHAR(15):pk1; 变量值:VARCHAR(30):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|变量表|265|变量名:VARCHAR(255):pk0; 变量值:VARCHAR(255):pk0|
|套圈统一图册|137|model:VARCHAR(50):pk1; Dw:REAL:pk0; Z:SMALLINT:pk0; Dwp:REAL:pk0; De:REAL:pk0; Dd2:REAL:pk0; Re:REAL:pk0; ae:REAL:pk0; t_SK:REAL:pk0; hz:REAL:pk0; di:REAL:pk0; d2:REAL:pk0; Ri:REAL:pk0; ai:REAL:pk0|
|实体保持架倒角|10|Dc:REAL:pk1; Ra:VARCHAR(50):pk0; Ra_h:VARCHAR(50):pk0; Ra_l:VARCHAR(50):pk0; Rmax:VARCHAR(50):pk0|
|实体统一图册|100|model:VARCHAR(50):pk1; Dc1:REAL:pk0; Dc:REAL:pk0; Bc:REAL:pk0; DeltaC:REAL:pk0; J:REAL:pk0|
|洛轴非装配倒角尺寸|20|rs:REAL:pk1; r2:VARCHAR(20):pk0; r3:VARCHAR(20):pk0; r5:VARCHAR(20):pk0; r8:VARCHAR(20):pk0|
|游隙|32|d:REAL:pk1; 2_B:VARCHAR(9):pk0; 2_S:VARCHAR(9):pk0; 0_B:VARCHAR(9):pk0; 0_S:VARCHAR(9):pk0; 3_B:VARCHAR(9):pk0; 3_S:VARCHAR(9):pk0; 4_B:VARCHAR(9):pk0; 4_S:VARCHAR(9):pk0; 5_B:VARCHAR(9):pk0; 5_S:VARCHAR(9):pk0|
|计算稿|261|段号:VARCHAR(15):pk0; 顺序号:REAL:pk1; 节号:VARCHAR(10):pk0; 内容:VARCHAR(180):pk0; 变量名:VARCHAR(10):pk0; 变量值:VARCHAR(50):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|轴承宽度公差|8|d:INTEGER:pk0; 0B_Upper:VARCHAR(255):pk0; 0B_Lower:VARCHAR(255):pk0; 2B_Upper:VARCHAR(255):pk0; 2B_Lower:VARCHAR(255):pk0; 3B_Upper:VARCHAR(255):pk0; 3B_Lower:VARCHAR(255):pk0|
|钢球标准尺寸|113|Dw:REAL:pk1; Inch:VARCHAR(8):pk0; deltab:VARCHAR(50):pk0|
|非装配倒角允差|21|公称尺寸:REAL:pk1; 上偏差:VARCHAR(20):pk0; 下偏差:VARCHAR(20):pk0|
|非装配倒角尺寸|15|rsmin:REAL:pk1; r3:VARCHAR(20):pk0; r3_h:VARCHAR(20):pk0; r3_l:VARCHAR(20):pk0; r8:VARCHAR(20):pk0; r8_h:VARCHAR(20):pk0; r8_l:VARCHAR(20):pk0|


### bearing.db

SHA-256 `288f6c1083687259be5b6fd460e165112134c5d3219a42d926ba62795dd9452a`

|表名|行数|列与主键（单位 BLOCKED）|
|---|---:|---|
|T_SKFA01|418|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA02|119|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA03|248|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA04|92|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA05|118|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA06|120|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; b_:REAL:pk0; Ring:VARCHAR(255):pk0; r:REAL:pk0; r0:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA07|29|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; b_:REAL:pk0; Ring:VARCHAR(255):pk0; r:REAL:pk0; r0:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA08|29|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; b_:REAL:pk0; Ring:VARCHAR(255):pk0; r:REAL:pk0; r0:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA09|70|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D1_D2:REAL:pk0; d1:REAL:pk0|
|T_SKFA10|41|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D1_D2:REAL:pk0; d1_d2_:REAL:pk0|
|T_SKFA11|85|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D1_D2:REAL:pk0; d1:REAL:pk0|
|T_SKFA12|3|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; r:REAL:pk0; d1:REAL:pk0; D1_:REAL:pk0|
|T_SKFA13|14|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; r:REAL:pk0; d1:REAL:pk0; F20:REAL:pk0|
|T_SKFA14|29|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA15|29|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA16|29|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA17|24|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; b_:REAL:pk0; Ring:VARCHAR(255):pk0; r:REAL:pk0; r0:REAL:pk0; D2:REAL:pk0; d2_:REAL:pk0|
|T_SKFA18|21|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; b_:REAL:pk0; Ring:VARCHAR(255):pk0; r:REAL:pk0; r0:REAL:pk0; D2:REAL:pk0; d2_:REAL:pk0|
|T_SKFA19|21|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; b_:REAL:pk0; Ring:VARCHAR(255):pk0; r:REAL:pk0; r0:REAL:pk0; D2:REAL:pk0; d2_:REAL:pk0|
|T_SKFA20|35|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; f0:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFC01|553|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; Dbmax:REAL:pk0; type_:REAL:pk0; r12:VARCHAR(255):pk0; r34:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0; d1_:REAL:pk0|
|T_SKFC02|389|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; 2B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; Dbmax:REAL:pk0; type_:REAL:pk0; r12:VARCHAR(255):pk0; r34:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0; d1_:REAL:pk0|
|T_SKFC03|65|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; type_:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFC04|44|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; type_:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFC05|66|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; type_:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFC06|5|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; damin:REAL:pk0; D3:REAL:pk0; c_:REAL:pk0; b_:REAL:pk0; type_:REAL:pk0; r12:REAL:pk0; r0:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFC07|125|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ka:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; type_:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFC08|389|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; 2B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ka:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; Dbmax:REAL:pk0; type_:REAL:pk0; r12:VARCHAR(255):pk0; r34:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0; d1_:REAL:pk0|
|T_SKFD01|118|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D1:VARCHAR(255):pk0; d2:REAL:pk0|
|T_SKFD02|24|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r:REAL:pk0; D1:VARCHAR(255):pk0; d2:REAL:pk0|
|T_SKFD03|69|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; r:REAL:pk0; D1:VARCHAR(255):pk0; d1_:REAL:pk0|
|T_SKFD04|15|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; r:REAL:pk0; D1:VARCHAR(255):pk0; d1_:REAL:pk0|
|T_SKFD05|8|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; c_:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; r:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFE01|94|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damin:REAL:pk0; Damax:REAL:pk0; damin_:REAL:pk0; damax_:REAL:pk0; s:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; E:REAL:pk0; d1:REAL:pk0|
|T_SKFE02|548|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; damin_:REAL:pk0; damax_:REAL:pk0; dbmin:REAL:pk0; s:REAL:pk0; Aangel_ring:VARCHAR(255):pk0; r12:REAL:pk0; r34:REAL:pk0; D1:REAL:pk0; F:REAL:pk0|
|T_SKFE03|10|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; c_:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; damax_:REAL:pk0; s:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; D1:REAL:pk0; F:REAL:pk0|
|T_SKFE04|388|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; damax_:REAL:pk0; dbmin:REAL:pk0; s:REAL:pk0; E:REAL:pk0; Y:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0; F:REAL:pk0|
|T_SKFE05|14|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; s:REAL:pk0; e:REAL:pk0; Y:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; E_:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFE06|242|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; dbmin:REAL:pk0; e:REAL:pk0; Y:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; F:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFE07|3|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; Damin:REAL:pk0; rbmax:REAL:pk0; s:REAL:pk0; damin_:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; E:REAL:pk0; d1:REAL:pk0|
|T_SKFE08|81|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; dbmin:REAL:pk0; damax_:REAL:pk0; s:REAL:pk0; rbmax:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; F:REAL:pk0; D1:REAL:pk0|
|T_SKFE09|4|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; rbmax:REAL:pk0; E:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; d1_:REAL:pk0; D1:REAL:pk0|
|T_SKFE10|3|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; Damax:REAL:pk0; Damin:REAL:pk0; damin_:REAL:pk0; s:REAL:pk0; rbmax:REAL:pk0; r12:REAL:pk0; tapper:REAL:pk0; r34:REAL:pk0; d1_:REAL:pk0; E:REAL:pk0|
|T_SKFE11|80|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; damin:REAL:pk0; Damax_:REAL:pk0; damax:REAL:pk0; s:REAL:pk0; rbmax:REAL:pk0; r12:REAL:pk0; tapper:REAL:pk0; r34:REAL:pk0; F:REAL:pk0; D1:REAL:pk0|
|T_SKFE12|141|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; Dbmax:REAL:pk0; s:REAL:pk0; e_:REAL:pk0; Y:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; E:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0|
|T_SKFE13|25|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; dbmax:REAL:pk0; s:REAL:pk0; e:REAL:pk0; Y:REAL:pk0; r12:REAL:pk0; F:REAL:pk0; d1_:REAL:pk0; D1:REAL:pk0|
|T_SKFE14|41|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; d1:REAL:pk0; E:REAL:pk0|
|T_SKFE15|77|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; d1:REAL:pk0; D1_:REAL:pk0|
|T_SKFE16|41|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; d1:REAL:pk0; E:REAL:pk0|
|T_SKFE17|31|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; kr:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; c_:REAL:pk0; rbmax:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; E_:REAL:pk0; d1_:REAL:pk0; D1:REAL:pk0|
|T_SKFF01|141|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; s:REAL:pk0; r12:REAL:pk0; F:REAL:pk0|
|T_SKFF02|11|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; c_:REAL:pk0; r12:REAL:pk0; F:REAL:pk0|
|T_SKFF03|11|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; c_:REAL:pk0; r12:REAL:pk0; F:REAL:pk0|
|T_SKFF04|24|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; da_:REAL:pk0; Db:REAL:pk0; Da:REAL:pk0; db_:REAL:pk0; s:REAL:pk0; r12:REAL:pk0; E:REAL:pk0; F:REAL:pk0|
|T_SKFF05|179|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; r12:REAL:pk0; E:REAL:pk0|
|T_SKFF06|11|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; r12:REAL:pk0; E:REAL:pk0|
|T_SKFF07|11|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; r12:REAL:pk0; E:REAL:pk0|
|T_SKFF08|46|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; da_:REAL:pk0; db:REAL:pk0; Da:REAL:pk0; r12:REAL:pk0; E:REAL:pk0|
|T_SKFH01|300|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; T:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y:REAL:pk0; Y0:REAL:pk0; c_:REAL:pk0; B:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; Damin:REAL:pk0; damax_:REAL:pk0; dbmin_:REAL:pk0; Dbmin:REAL:pk0; camin:REAL:pk0; cbmin:REAL:pk0; a:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; d1:REAL:pk0|
|T_SKFH02|4|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; T:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y:REAL:pk0; Y0:REAL:pk0; c_:REAL:pk0; B:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; Damin:REAL:pk0; damax_:REAL:pk0; dbmin:REAL:pk0; Dbmin_:REAL:pk0; camin:REAL:pk0; cbmin:REAL:pk0; a:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; d1:REAL:pk0; T1:REAL:pk0; C1:REAL:pk0; B1:REAL:pk0; Tn:REAL:pk0|
|T_SKFH03|39|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; T:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; c_:REAL:pk0; ramax:REAL:pk0; r0max:REAL:pk0; dbmin:REAL:pk0; Dbmin_:REAL:pk0; cbmin:REAL:pk0; a:REAL:pk0; r12:REAL:pk0; r5:REAL:pk0; d1:REAL:pk0; T1:REAL:pk0; C1:REAL:pk0; B1:REAL:pk0; Tr0:REAL:pk0|
|T_SKFH04|90|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; T:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; 2B:REAL:pk0; ramax:REAL:pk0; rbmax:REAL:pk0; Damax:REAL:pk0; Damin:REAL:pk0; damax_:REAL:pk0; camin:REAL:pk0; r34:REAL:pk0; r5:REAL:pk0; C1:REAL:pk0|
|T_SKFI01|326|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFI02|101|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; damax_:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFI03|37|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; innerDia:REAL:pk0; outerDia:REAL:pk0; width:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFI04|322|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; taper:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFI05|59|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; taper:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFI06|22|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; e:REAL:pk0; Y1:REAL:pk0; Y2:REAL:pk0; Y0:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; taper:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFJ01|139|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damin:REAL:pk0; Damax:REAL:pk0; damin_:REAL:pk0; damax_:REAL:pk0; s1:REAL:pk0; k1:REAL:pk0; k2:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0; camin:REAL:pk0|
|T_SKFJ02|79|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin_:REAL:pk0; damax_:REAL:pk0; s1:REAL:pk0; s2:REAL:pk0; k1:REAL:pk0; k2:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFJ03|27|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin_:REAL:pk0; damax_:REAL:pk0; s2:REAL:pk0; k1:REAL:pk0; k2:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFJ04|138|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damin:REAL:pk0; Damax:REAL:pk0; damin_:REAL:pk0; damax_:REAL:pk0; s1:REAL:pk0; k1:REAL:pk0; k2:REAL:pk0; taper:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0; camin:REAL:pk0|
|T_SKFJ05|56|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin_:REAL:pk0; damax_:REAL:pk0; s1:REAL:pk0; s2:REAL:pk0; k1:REAL:pk0; k2:REAL:pk0; taper:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d2:REAL:pk0|
|T_SKFK01|210|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; H:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; A:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d1_:INTEGER:pk0|
|T_SKFK02|47|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; H1:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; A:REAL:pk0; D3:REAL:pk0; H:REAL:pk0; R:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; D2:REAL:pk0; d1_:INTEGER:pk0; c_:INTEGER:pk0; s:INTEGER:pk0|
|T_SKFK03|45|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; H:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; A:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; rbmax:REAL:pk0; damax_:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; D1:REAL:pk0; B:INTEGER:pk0|
|T_SKFK04|16|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; H1:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; A:REAL:pk0; D3:REAL:pk0; H:REAL:pk0; R:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; rbmax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; r34:REAL:pk0; D1:REAL:pk0; b_:INTEGER:pk0; D2:INTEGER:pk0; s:INTEGER:pk0; c_:INTEGER:pk0|
|T_SKFM01|188|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; H:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; A:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; r12:REAL:pk0; type_:INTEGER:pk0; D1_:REAL:pk0; d1:REAL:pk0|
|T_SKFN01|30|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; Dw:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; B1:REAL:pk0; B2:REAL:pk0; B3:REAL:pk0; r12:REAL:pk0; D1_:REAL:pk0; d1:REAL:pk0; Ea:REAL:pk0; Eb:REAL:pk0|
|T_SKFP01|111|ID:INTEGER:pk1; Type:VARCHAR(255):pk0; d:REAL:pk0; D_:REAL:pk0; H:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:VARCHAR(255):pk0; nmax:REAL:pk0; Mass:REAL:pk0; A:REAL:pk0; H1:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; type_:REAL:pk0; r12:REAL:pk0; D1:REAL:pk0; d1_:REAL:pk0; b_:REAL:pk0; B1:REAL:pk0; db1max:VARCHAR(255):pk0; db2max:VARCHAR(255):pk0; s:REAL:pk0|
|adddynamicforce1|3|Type:VARCHAR(255):pk1; svalue:REAL:pk0; min:REAL:pk0; max:REAL:pk0|
|adddynamicforce2|15|Type:VARCHAR(255):pk1; svalue:REAL:pk0; min:REAL:pk0; max:REAL:pk0|
|adddynamicforce3|3|Type:VARCHAR(255):pk1; svalue:REAL:pk0; min:REAL:pk0; max:REAL:pk0|
|bearing_design|81|DisplaySize:REAL:pk0; Type:TEXT:pk0; Index:INTEGER:pk0; DrawSize_Start:REAL:pk0; DrawSize_ID:REAL:pk0; Fmin:REAL:pk0; Sealed:REAL:pk0; SizeTable:VARCHAR(255):pk0; Picture:VARCHAR(255):pk0; CalculationTable:VARCHAR(255):pk0; Draw:VARCHAR(255):pk0; Special:VARCHAR(255):pk0|
|bearing_design_查询|81|Type:TEXT:pk0; Index:INTEGER:pk0; SizeTable:VARCHAR(255):pk0|
|bearing_type|30|ID:SMALLINT:pk1; Type:TEXT:pk0; Units:SMALLINT:pk0; Group:REAL:pk0; GroupDesign:REAL:pk0; Load:REAL:pk0; Famax:REAL:pk0; Frmax:REAL:pk0; DesignID:REAL:pk0; Sp_des_count:REAL:pk0; TableAID:VARCHAR(255):pk0; TableBID:VARCHAR(255):pk0; TableCID:VARCHAR(255):pk0; Sp_des_reload:REAL:pk0; Friction_coeff:REAL:pk0; Bearing_factor:REAL:pk0; Bearing_pair:REAL:pk0|
|table_design|22|table_designID:VARCHAR(255):pk1; Design:TEXT:pk0|
|tableb|4|TableBID:VARCHAR(255):pk1; Design:TEXT:pk0|
|tablec|1|TableCID:VARCHAR(255):pk1; Design:TEXT:pk0|


### bearing_Backup.db

SHA-256 `44e48d60314b48ea393d63cc5cac30559e9172d521db24b9ddeef95985380982`

|表名|行数|列与主键（单位 BLOCKED）|
|---|---:|---|
|T_SKFA01|418|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:REAL:pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; kr:REAL:pk0; ka:REAL:pk0; f0:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|T_SKFA02|0|ID:INTEGER:pk1; Type:TEXT:pk0; d:REAL:pk0; D_:REAL:pk0; B:REAL:pk0; C:REAL:pk0; C0:REAL:pk0; Pu:REAL:pk0; nr:REAL:pk0; nmax:REAL:pk0; Mass:REAL:pk0; ramax:REAL:pk0; Damax:REAL:pk0; damin:REAL:pk0; kr:REAL:pk0; ka:REAL:pk0; f0:REAL:pk0; r:REAL:pk0; D2:REAL:pk0; d1_d2:REAL:pk0|
|adddynamicforce1|3|Type:VARCHAR(255):pk1; svalue:REAL:pk0; min:REAL:pk0; max:REAL:pk0|
|adddynamicforce2|15|Type:VARCHAR(255):pk1; svalue:REAL:pk0; min:REAL:pk0; max:REAL:pk0|
|adddynamicforce3|3|Type:VARCHAR(255):pk1; svalue:REAL:pk0; min:REAL:pk0; max:REAL:pk0|
|bearing_design|81|DisplaySize:REAL:pk0; Type:TEXT:pk0; Index:INTEGER:pk0; DrawSize_Start:REAL:pk0; DrawSize_ID:REAL:pk0; Fmin:REAL:pk0; Sealed:REAL:pk0; SizeTable:VARCHAR(255):pk0; Piacture:VARCHAR(255):pk0; CalculationTable:VARCHAR(255):pk0; Draw:VARCHAR(255):pk0; Special:VARCHAR(255):pk0|
|bearing_design_查询|81|Type:TEXT:pk0; Index:INTEGER:pk0; SizeTable:VARCHAR(255):pk0|
|bearing_type|30|ID:SMALLINT:pk1; Type:TEXT:pk0; Units:SMALLINT:pk0; Group:SMALLINT:pk0; GroupDesign:SMALLINT:pk0; Load:SMALLINT:pk0; Famax:REAL:pk0; Frmax:REAL:pk0; DesignID:REAL:pk0; Sp_des_count:REAL:pk0; TableAID:VARCHAR(255):pk0; TableBID:VARCHAR(255):pk0; TableCID:VARCHAR(255):pk0; Sp_des_reload:REAL:pk0; Friction_coeff:REAL:pk0; Bearing_factor:REAL:pk0; Bearing_pair:REAL:pk0|
|table_design|22|table_designID:VARCHAR(255):pk1; Design:TEXT:pk0|
|tableb|4|TableBID:VARCHAR(255):pk1; Design:TEXT:pk0|
|tablec|1|TableCID:VARCHAR(255):pk1; Design:TEXT:pk0|
|粘贴错误|12|F1:REAL:pk0; F2:VARCHAR(255):pk0; F3:REAL:pk0; F4:REAL:pk0; F5:REAL:pk0; F6:REAL:pk0; F7:REAL:pk0; F8:REAL:pk0; F9:VARCHAR(255):pk0; F10:REAL:pk0; F11:REAL:pk0; F12:REAL:pk0; F13:REAL:pk0; F14:REAL:pk0; F15:REAL:pk0; F16:REAL:pk0; F17:REAL:pk0; F18:REAL:pk0; F19:REAL:pk0; F20:REAL:pk0|


### BearingType.db

SHA-256 `6e9b08abd010acd87884700403e0575bf0dac8991132d2db44111e885e12adeb`

|表名|行数|列与主键（单位 BLOCKED）|
|---|---:|---|
|_TMPCLP29761|0|model:VARCHAR(255):pk1; d:INTEGER:pk0; Dd:INTEGER:pk0; B:INTEGER:pk0; rsmin:INTEGER:pk0; Cr:INTEGER:pk0; Cor:INTEGER:pk0; grease:INTEGER:pk0; oil:INTEGER:pk0; mass:INTEGER:pk0|
|_TMPCLP591401|106|ID:INTEGER:pk1; 字段2:VARCHAR(255):pk0; 字段3:VARCHAR(255):pk0; 字段4:VARCHAR(255):pk0; 字段5:VARCHAR(255):pk0; 字段6:VARCHAR(255):pk0; 字段7:VARCHAR(255):pk0; 字段10:VARCHAR(255):pk0; 字段8:VARCHAR(255):pk0; 字段9:VARCHAR(255):pk0|
|圆柱滚子轴承型号目录|0|model:VARCHAR(255):pk1; d:INTEGER:pk0; Dd:INTEGER:pk0; B:INTEGER:pk0; rsmin:INTEGER:pk0; r1smin:INTEGER:pk0; Cr:INTEGER:pk0; Cor:INTEGER:pk0; grease:INTEGER:pk0; oil:INTEGER:pk0; mass:INTEGER:pk0|
|深沟球轴承型号目录|105|model:VARCHAR(255):pk1; d:REAL:pk0; Dd:REAL:pk0; B:REAL:pk0; rsmin:REAL:pk0; Cr:REAL:pk0; Cor:REAL:pk0; 脂润滑转速:REAL:pk0; 油润滑转速:REAL:pk0; 重量:REAL:pk0|
|角接触球轴承型号目录|0|model:VARCHAR(255):pk1; d:INTEGER:pk0; Dd:INTEGER:pk0; B:INTEGER:pk0; rsmin:INTEGER:pk0; r1smin:INTEGER:pk0; Cr:INTEGER:pk0; Cor:INTEGER:pk0; grease:INTEGER:pk0; oil:INTEGER:pk0; mass:INTEGER:pk0|


### CRBData.db

SHA-256 `00058d459d5f5d5c1c7807e9de17d86aaa0558bb15e0e53a005fc039da4cb9e8`

|表名|行数|列与主键（单位 BLOCKED）|
|---|---:|---|
|B级内圈技术条件|10|d:REAL:pk1; d_l:VARCHAR(9):pk0; Vdp9:VARCHAR(9):pk0; Vdp01:VARCHAR(9):pk0; Vdp234:VARCHAR(9):pk0; Vdmp:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; VBs:VARCHAR(9):pk0; Sd:VARCHAR(50):pk0; Ki:VARCHAR(50):pk0; VB2s:VARCHAR(50):pk0; Li:VARCHAR(50):pk0; dimp-dimpa:VARCHAR(50):pk0; Sdi:VARCHAR(50):pk0; deltaCir_i:VARCHAR(50):pk0; Vdip:VARCHAR(50):pk0|
|B级外圈技术条件|9|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; VDdp9:VARCHAR(9):pk0; VDdp01:VARCHAR(9):pk0; VDdp234:VARCHAR(9):pk0; VDdmp:VARCHAR(9):pk0; VCs:VARCHAR(50):pk0; SDd:VARCHAR(50):pk0; Ke:VARCHAR(50):pk0; VC2s:VARCHAR(50):pk0; deltaCir_e:VARCHAR(50):pk0; VDep:VARCHAR(50):pk0|
|B级总图内圈技术条件|11|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|B级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|B级粗糙度表|12|套圈直径:REAL:pk1; _Dd:VARCHAR(20):pk0; _d:VARCHAR(20):pk0; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Ddis:VARCHAR(20):pk0|
|C级内圈技术条件|9|d:REAL:pk1; d_l:VARCHAR(9):pk0; Vdp9:VARCHAR(9):pk0; Vdp01:VARCHAR(9):pk0; Vdp234:VARCHAR(9):pk0; Vdmp:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; VBs:VARCHAR(9):pk0; Sd:VARCHAR(50):pk0; Ki:VARCHAR(50):pk0; VB2s:VARCHAR(50):pk0; Li:VARCHAR(50):pk0; dimp-dimpa:VARCHAR(50):pk0; Sdi:VARCHAR(50):pk0; deltaCir_i:VARCHAR(50):pk0; Vdip:VARCHAR(50):pk0|
|C级外圈技术条件|9|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; VDdp9:VARCHAR(9):pk0; VDdp01:VARCHAR(9):pk0; VDdp234:VARCHAR(9):pk0; VDdmp:VARCHAR(9):pk0; VCs:VARCHAR(50):pk0; SDd:VARCHAR(50):pk0; Ke:VARCHAR(50):pk0; VC2s:VARCHAR(50):pk0; deltaCir_e:VARCHAR(50):pk0; VDep:VARCHAR(50):pk0|
|C级总图内圈技术条件|10|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|C级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|C级粗糙度表|12|套圈直径:REAL:pk1; _Dd:VARCHAR(20):pk0; _d:VARCHAR(20):pk0; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Ddis:VARCHAR(20):pk0|
|D3_d3公差表|9|D3_d3:REAL:pk1; ΔD3_Δd3上偏差:VARCHAR(20):pk0; ΔD3_Δd3下偏差:VARCHAR(20):pk0|
|D级内圈技术条件|15|d:REAL:pk1; d_l:VARCHAR(9):pk0; Vdp9:VARCHAR(9):pk0; Vdp01:VARCHAR(9):pk0; Vdp234:VARCHAR(9):pk0; Vdmp:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; VBs:VARCHAR(9):pk0; Sd:VARCHAR(50):pk0; Ki:VARCHAR(50):pk0; VB2s:VARCHAR(50):pk0; Li:VARCHAR(50):pk0; dimp-dimpa:VARCHAR(50):pk0; Sdi:VARCHAR(50):pk0; deltaCir_i:VARCHAR(50):pk0; Vdip:VARCHAR(50):pk0|
|D级外圈技术条件|14|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; VDdp9:VARCHAR(9):pk0; VDdp01:VARCHAR(9):pk0; VDdp234:VARCHAR(9):pk0; VDdmp:VARCHAR(9):pk0; VCs:VARCHAR(50):pk0; SDd:VARCHAR(50):pk0; Ke:VARCHAR(50):pk0; VC2s:VARCHAR(50):pk0; deltaCir_e:VARCHAR(50):pk0; VDep:VARCHAR(50):pk0|
|D级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|D级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|D级粗糙度表|12|套圈直径:REAL:pk1; _Dd:VARCHAR(20):pk0; _d:VARCHAR(20):pk0; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Ddis:VARCHAR(20):pk0|
|E公差表|4|滚道宽度E:REAL:pk1; E上偏差:VARCHAR(20):pk0; E下偏差:VARCHAR(20):pk0|
|E级内圈技术条件|18|d:REAL:pk1; d_l:VARCHAR(9):pk0; Vdp9:VARCHAR(9):pk0; Vdp01:VARCHAR(9):pk0; Vdp234:VARCHAR(9):pk0; Vdmp:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; VBs:VARCHAR(9):pk0; Sd:VARCHAR(50):pk0; Ki:VARCHAR(50):pk0; VB2s:VARCHAR(50):pk0; Li:VARCHAR(50):pk0; dimp-dimpa:VARCHAR(50):pk0; Sdi:VARCHAR(50):pk0; deltaCir_i:VARCHAR(50):pk0; Vdip:VARCHAR(50):pk0|
|E级外圈技术条件|17|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; VDdp9:VARCHAR(9):pk0; VDdp01:VARCHAR(9):pk0; VDdp234:VARCHAR(9):pk0; VDdmp:VARCHAR(9):pk0; VCs:VARCHAR(50):pk0; SDd:VARCHAR(50):pk0; Ke:VARCHAR(50):pk0; VC2s:VARCHAR(50):pk0; deltaCir_e:VARCHAR(50):pk0; VDep:VARCHAR(50):pk0|
|E级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|E级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|E级粗糙度表|12|套圈直径:REAL:pk1; _Dd:VARCHAR(20):pk0; _d:VARCHAR(20):pk0; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Ddis:VARCHAR(20):pk0|
|G级内圈技术条件|18|d:REAL:pk1; d_l:VARCHAR(9):pk0; Vdp9:VARCHAR(9):pk0; Vdp01:VARCHAR(9):pk0; Vdp234:VARCHAR(9):pk0; Vdmp:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; VBs:VARCHAR(9):pk0; Sd:VARCHAR(50):pk0; Ki:VARCHAR(50):pk0; VB2s:VARCHAR(50):pk0; Li:VARCHAR(50):pk0; dimp-dimpa:VARCHAR(50):pk0; Sdi:VARCHAR(50):pk0; deltaCir_i:VARCHAR(50):pk0; Vdip:VARCHAR(50):pk0|
|G级外圈技术条件|17|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; VDdp9:VARCHAR(9):pk0; VDdp01:VARCHAR(9):pk0; VDdp234:VARCHAR(9):pk0; VDdmp:VARCHAR(9):pk0; VCs:VARCHAR(50):pk0; SDd:VARCHAR(50):pk0; Ke:VARCHAR(50):pk0; VC2s:VARCHAR(50):pk0; deltaCir_e:VARCHAR(50):pk0; VDep:VARCHAR(50):pk0|
|G级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|G级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|G级粗糙度表|12|套圈直径:REAL:pk1; _Dd:VARCHAR(20):pk0; _d:VARCHAR(20):pk0; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Ddis:VARCHAR(20):pk0|
|model|318|model:VARCHAR(6):pk1; d:INTEGER:pk0; Dd:INTEGER:pk0; B:INTEGER:pk0; rsmin:VARCHAR(3):pk0; r1smin:VARCHAR(3):pk0; di:VARCHAR(5):pk0; De:VARCHAR(5):pk0; BBt:VARCHAR(5):pk0; Bt:VARCHAR(5):pk0|
|倒角尺寸表|30|rsmin:REAL:pk0; d:INTEGER:pk0; rsmax_r:REAL:pk0; rsmax_a:REAL:pk0; rs_r:VARCHAR(255):pk0; rs_r_Upper:VARCHAR(255):pk0; rs_r_Lower:VARCHAR(255):pk0; rs_a:VARCHAR(255):pk0; rs_a_Upper:VARCHAR(255):pk0; rs_a_Lower:VARCHAR(255):pk0; r3:VARCHAR(255):pk0; r3_Upper:VARCHAR(255):pk0; r3_Lower:VARCHAR(255):pk0; r8:VARCHAR(255):pk0; r8_Upper:VARCHAR(255):pk0; r8_Lower:VARCHAR(255):pk0; r2:VARCHAR(255):pk0; r2_Upper:VARCHAR(255):pk0; r2_Lower:VARCHAR(255):pk0; r5:VARCHAR(255):pk0; r5_Upper:VARCHAR(255):pk0; r5_Lower:VARCHAR(255):pk0|
|单列游隙|29|d:REAL:pk1; 2_S:VARCHAR(9):pk0; 2_B:VARCHAR(9):pk0; 0_S:VARCHAR(9):pk0; 0_B:VARCHAR(9):pk0; 3_S:VARCHAR(9):pk0; 3_B:VARCHAR(9):pk0; 4_S:VARCHAR(9):pk0; 4_B:VARCHAR(9):pk0; 5_S:VARCHAR(9):pk0; 5_B:VARCHAR(9):pk0|
|变量|270|变量名:VARCHAR(15):pk1; 变量值:VARCHAR(30):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|变量表|321|变量名:VARCHAR(255):pk0; 变量值:VARCHAR(255):pk0|
|圆柱滚子参数表|42|Dw:REAL:pk1; lw:REAL:pk2; r04:VARCHAR(20):pk0; r04_h:VARCHAR(20):pk0; r04_l:VARCHAR(20):pk0; t1:VARCHAR(20):pk0; delta:VARCHAR(20):pk0; t:VARCHAR(20):pk0; Rc:VARCHAR(20):pk0|
|套圈滚道公差带|32|轴承内径d:REAL:pk1; 四列内组件上偏差:VARCHAR(6):pk0; 双四列内组件上偏差:VARCHAR(6):pk0; 双四列内组件下偏差:VARCHAR(6):pk0; 最小径向游隙:VARCHAR(20):pk0; 最大径向游隙:VARCHAR(20):pk0; 内圈双挡边上偏差:VARCHAR(20):pk0; 内圈双挡边下偏差:VARCHAR(20):pk0; 外圈非双挡边上偏差:VARCHAR(20):pk0; 外圈非双挡边下偏差:VARCHAR(20):pk0; 内圈非双挡边上偏差:VARCHAR(20):pk0; 内圈非双挡边下偏差:VARCHAR(20):pk0; 外圈双挡边上偏差:VARCHAR(20):pk0; 外圈双挡边下偏差:VARCHAR(20):pk0|
|套圈滚道形位公差|7|E:REAL:pk1; 0_dimp_dimpa:VARCHAR(9):pk0; 6_dimp_dimpa:VARCHAR(9):pk0; 5_dimp_dimpa:VARCHAR(9):pk0; 4_dimp_dimpa:VARCHAR(9):pk0; 2_dimp_dimpa:VARCHAR(9):pk0; 0_Sdi:VARCHAR(9):pk0; 6_Sdi:VARCHAR(9):pk0; 5_Sdi:VARCHAR(9):pk0; 4_Sdi:VARCHAR(9):pk0; 2_Sdi:VARCHAR(9):pk0|
|实体保持架倒角部分|10|Dc:REAL:pk1; Ra:VARCHAR(50):pk0; Ra_h:VARCHAR(50):pk0; Ra_l:VARCHAR(50):pk0; Rmax:VARCHAR(50):pk0|
|实体保持架用长铆钉尺寸及允差|12|dm:REAL:pk1; Ddm:VARCHAR(50):pk0; Ddm_h:VARCHAR(50):pk0; Ddm_l:VARCHAR(50):pk0; hm:VARCHAR(50):pk0; hm_h:VARCHAR(50):pk0; hm_l:VARCHAR(50):pk0; R:VARCHAR(50):pk0; dma:VARCHAR(50):pk0; ea:VARCHAR(50):pk0; lo:VARCHAR(50):pk0; Dm1:VARCHAR(50):pk0; hac:VARCHAR(50):pk0|
|宽度下偏差|17|d:REAL:pk1; b_l:VARCHAR(50):pk0|
|带支柱孔滚子厂标|41|序号:TINYINT:pk1; Dw:VARCHAR(5):pk0; lw:VARCHAR(5):pk0|
|平挡圈公差表|6|d0:REAL:pk1; d0_h:VARCHAR(50):pk0; d0_l:VARCHAR(50):pk0|
|挡边a公差表|5|lw:REAL:pk1; a上偏差:VARCHAR(20):pk0; a下偏差:VARCHAR(20):pk0|
|游隙|32|d:REAL:pk1; 2_B:VARCHAR(9):pk0; 2_S:VARCHAR(9):pk0; 0_B:VARCHAR(9):pk0; 0_S:VARCHAR(9):pk0; 3_B:VARCHAR(9):pk0; 3_S:VARCHAR(9):pk0; 4_B:VARCHAR(9):pk0; 4_S:VARCHAR(9):pk0; 5_B:VARCHAR(9):pk0; 5_S:VARCHAR(9):pk0|
|滚子倒角洼穴斜坡|12|Dw:REAL:pk1; r04:VARCHAR(50):pk0; r04_h:VARCHAR(50):pk0; r04_l:VARCHAR(50):pk0; h:VARCHAR(50):pk0; t:VARCHAR(50):pk0|
|滚子公差表|7|Dw:REAL:pk1; lw上偏差:VARCHAR(20):pk0; lw下偏差:VARCHAR(20):pk0; Dw上偏差:VARCHAR(20):pk0; Dw下偏差:VARCHAR(20):pk0|
|滚子尺寸厂标|178|序号:TINYINT:pk1; Dw:VARCHAR(5):pk0; lw:VARCHAR(5):pk0|
|滚子尺寸国标|127|序号:TINYINT:pk1; Dw:VARCHAR(5):pk0; lw:VARCHAR(5):pk0|
|滚子标准公称尺寸|145|Dw:REAL:pk0; Lw:REAL:pk0; rsmin:REAL:pk0; rsmax:REAL:pk0|
|滚子直径|47|Dw:REAL:pk1|
|滚子粗糙度表|4|Dw:REAL:pk1; _Dw:VARCHAR(50):pk0; _Dws:VARCHAR(50):pk0|
|滚道宽度公差|3|rollerLength:INTEGER:pk0; 上偏差:VARCHAR(255):pk0; 下偏差:VARCHAR(255):pk0|
|粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0; _dis:VARCHAR(20):pk0; _d2s:VARCHAR(20):pk0; _Dd2s:VARCHAR(20):pk0; _Ddis:VARCHAR(20):pk0|
|计算稿单|133|段号:VARCHAR(12):pk0; 顺序号:REAL:pk1; 节号:VARCHAR(10):pk0; 内容:VARCHAR(180):pk0; 变量名:VARCHAR(10):pk0; 变量值:VARCHAR(50):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|记录|334|序号:INTEGER:pk1; 型号:VARCHAR(50):pk0; 日期:VARCHAR(50):pk0|
|越程槽|14|Dw:REAL:pk1; mmax:VARCHAR(50):pk0; m1max:VARCHAR(50):pk0; m2max:VARCHAR(50):pk0|
|轴承宽度公差|17|d:INTEGER:pk0; B_Upper:VARCHAR(255):pk0; B_Lower:VARCHAR(255):pk0|
|长铆钉直径|12|Dw:REAL:pk1; dm:VARCHAR(10):pk0|
|非装配倒角允差|21|公称尺寸:REAL:pk1; 上偏差:VARCHAR(20):pk0; 下偏差:VARCHAR(20):pk0|
|非装配倒角尺寸|20|rs:REAL:pk1; r2:VARCHAR(20):pk0; r3:VARCHAR(20):pk0; r5:VARCHAR(20):pk0; r8:VARCHAR(20):pk0|


### DGBData - 副本.db

SHA-256 `e037edcd7f62a7b8e63e867d3515fa5d745caf23e5228b787e024613ead216d9`

|表名|行数|列与主键（单位 BLOCKED）|
|---|---:|---|
|B级内圈技术条件|10|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|B级外圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|B级总图内圈技术条件|11|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|B级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|B级粗糙度表|11|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|C级内圈技术条件|9|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|C级外圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|C级总图内圈技术条件|10|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|C级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|C级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|D级内圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|D级外圈技术条件|14|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|D级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|D级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|D级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|E级内圈技术条件|13|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|E级外圈技术条件|15|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|E级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|E级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|E级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|G级内圈技术条件|13|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|G级外圈技术条件|15|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|G级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP9:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|G级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|G级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|fc_f0|40|Dw_Dpw:REAL:pk0; fc:VARCHAR(20):pk0; f0:VARCHAR(20):pk0|
|model|145|model:VARCHAR(50):pk1; d:INTEGER:pk0; Dd:INTEGER:pk0; B:INTEGER:pk0; rsmin:REAL:pk0|
|主参数|16|model:VARCHAR(50):pk1; Dw:VARCHAR(20):pk0; Z:VARCHAR(20):pk0; Dwp:VARCHAR(20):pk0; fai:VARCHAR(20):pk0|
|倒角尺寸表|25|rsmin:REAL:pk0; d:INTEGER:pk0; rsmax_r:REAL:pk0; rsmax_a:REAL:pk0; rs_r:VARCHAR(255):pk0; rs_r_Upper:VARCHAR(255):pk0; rs_r_Lower:VARCHAR(255):pk0; rs_a:VARCHAR(255):pk0; rs_a_Upper:VARCHAR(255):pk0; rs_a_Lower:VARCHAR(255):pk0; r3:VARCHAR(255):pk0; r3_Upper:VARCHAR(255):pk0; r3_Lower:VARCHAR(255):pk0; r8:VARCHAR(255):pk0; r8_Upper:VARCHAR(255):pk0; r8_Lower:VARCHAR(255):pk0|
|变量|195|变量名:VARCHAR(15):pk1; 变量值:VARCHAR(30):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|变量表|96|变量名:VARCHAR(255):pk0; 变量值:VARCHAR(255):pk0|
|实体保持架倒角|10|Dc:REAL:pk1; Ra:VARCHAR(50):pk0; Ra_h:VARCHAR(50):pk0; Ra_l:VARCHAR(50):pk0; Rmax:VARCHAR(50):pk0|
|密封圈89|109|model:VARCHAR(50):pk1; Ddm1:VARCHAR(20):pk0; Ddm1_h:VARCHAR(20):pk0; Ddm2:VARCHAR(20):pk0; Ddm2_h:VARCHAR(20):pk0; Ddm3:VARCHAR(20):pk0; Ddm3_h:VARCHAR(20):pk0; Ddm4:VARCHAR(20):pk0; Ddm4_h:VARCHAR(20):pk0; dm1:VARCHAR(20):pk0; dm1_h:VARCHAR(20):pk0; dm2:VARCHAR(20):pk0; dm2_h:VARCHAR(20):pk0; dm3:VARCHAR(20):pk0; dm3_h:VARCHAR(20):pk0; dm4:VARCHAR(20):pk0; dm4_h:VARCHAR(20):pk0; Pm:VARCHAR(20):pk0; Bm1:VARCHAR(20):pk0; Bm1_l:VARCHAR(20):pk0; Bm2:VARCHAR(20):pk0; Bm2_l:VARCHAR(20):pk0; Bm3:VARCHAR(20):pk0; Bm4:VARCHAR(20):pk0; Bm5:VARCHAR(20):pk0; Bm5_l:VARCHAR(20):pk0; Bm6:VARCHAR(20):pk0; Bm6_h:VARCHAR(20):pk0; DdH:VARCHAR(20):pk0; DdH_h:VARCHAR(20):pk0; dH:VARCHAR(20):pk0; dH_h:VARCHAR(20):pk0; SH:VARCHAR(20):pk0; SH_l:VARCHAR(20):pk0; H:VARCHAR(20):pk0; Rm1:VARCHAR(50):pk0; Rm2:VARCHAR(50):pk0; Rm3:VARCHAR(50):pk0|
|密封槽89|109|model:VARCHAR(50):pk1; Dd2_h:VARCHAR(20):pk0; Dd3:VARCHAR(20):pk0; Dd3_h:VARCHAR(20):pk0; Dd4:VARCHAR(20):pk0; Dd4_h:VARCHAR(20):pk0; b:VARCHAR(20):pk0; b_h:VARCHAR(20):pk0; b1:VARCHAR(50):pk0; R1:VARCHAR(50):pk0; d2_l:VARCHAR(50):pk0|
|止动槽|50|Dd:REAL:pk1; Dd1max:VARCHAR(9):pk0; Dd1min:VARCHAR(9):pk0; a0max:VARCHAR(9):pk0; a0min:VARCHAR(9):pk0; a234max:VARCHAR(9):pk0; a234min:VARCHAR(9):pk0; bmax:VARCHAR(9):pk0; bmin:VARCHAR(9):pk0; r0:VARCHAR(9):pk0|
|洛轴非装配倒角尺寸|20|rs:REAL:pk1; r2:VARCHAR(20):pk0; r3:VARCHAR(20):pk0; r5:VARCHAR(20):pk0; r8:VARCHAR(20):pk0|
|游隙|32|d:REAL:pk1; 2_B:VARCHAR(9):pk0; 2_S:VARCHAR(9):pk0; 0_B:VARCHAR(9):pk0; 0_S:VARCHAR(9):pk0; 3_B:VARCHAR(9):pk0; 3_S:VARCHAR(9):pk0; 4_B:VARCHAR(9):pk0; 4_S:VARCHAR(9):pk0; 5_B:VARCHAR(9):pk0; 5_S:VARCHAR(9):pk0|
|统一图册|109|model:VARCHAR(50):pk1; Dw:VARCHAR(20):pk0; Z:VARCHAR(20):pk0; Dwp:VARCHAR(20):pk0; dm:VARCHAR(20):pk0; L:VARCHAR(50):pk0; ai_h:VARCHAR(50):pk0; De:VARCHAR(50):pk0; De_h:VARCHAR(50):pk0; Dd2:VARCHAR(50):pk0; Dd2_h:VARCHAR(50):pk0; Re:VARCHAR(50):pk0; Re_h:VARCHAR(50):pk0; Dk:VARCHAR(50):pk0; ZG:VARCHAR(50):pk0; di:VARCHAR(50):pk0; d2:VARCHAR(50):pk0; d2_l:VARCHAR(50):pk0; Ri:VARCHAR(50):pk0; Dc1:VARCHAR(50):pk0; Dc:VARCHAR(50):pk0; S:VARCHAR(50):pk0; Rc:VARCHAR(50):pk0; Rc_h:VARCHAR(50):pk0; K:VARCHAR(50):pk0; rrc:VARCHAR(50):pk0|
|计算稿|289|段号:VARCHAR(15):pk0; 顺序号:REAL:pk1; 节号:VARCHAR(10):pk0; 内容:VARCHAR(180):pk0; 变量名:VARCHAR(10):pk0; 变量值:VARCHAR(50):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|记录|1|序号:INTEGER:pk1; 型号:VARCHAR(50):pk0; 日期:VARCHAR(50):pk0|
|轴承宽度公差|8|d:INTEGER:pk0; 0B_Upper:VARCHAR(255):pk0; 0B_Lower:VARCHAR(255):pk0; 2B_Upper:VARCHAR(255):pk0; 2B_Lower:VARCHAR(255):pk0; 3B_Upper:VARCHAR(255):pk0; 3B_Lower:VARCHAR(255):pk0|
|钢球标准尺寸|126|Dw:REAL:pk1; Inch:VARCHAR(8):pk0; deltab:VARCHAR(50):pk0|
|长铆钉尺寸及允差|9|dm:REAL:pk1; Ddm:VARCHAR(50):pk0; Ddm_h:VARCHAR(50):pk0; Ddm_l:VARCHAR(50):pk0; hm:VARCHAR(50):pk0; hm_h:VARCHAR(50):pk0; hm_l:VARCHAR(50):pk0; R:VARCHAR(50):pk0; dma:VARCHAR(50):pk0; ea:VARCHAR(50):pk0; lo:VARCHAR(50):pk0; Dm1:VARCHAR(50):pk0; hac:VARCHAR(50):pk0|
|防尘盖89|109|model:VARCHAR(50):pk1; DdF:VARCHAR(20):pk0; DdF_h:VARCHAR(20):pk0; DdF_l:VARCHAR(20):pk0; dF:VARCHAR(20):pk0; dF_h:VARCHAR(20):pk0; DdF1:VARCHAR(20):pk0; DdF2:VARCHAR(20):pk0; DdF3:VARCHAR(20):pk0; BF:VARCHAR(20):pk0; BF1:VARCHAR(20):pk0; BF2:VARCHAR(20):pk0; SF:VARCHAR(20):pk0; alfaF:VARCHAR(20):pk0; hF:VARCHAR(20):pk0; NF:VARCHAR(20):pk0; RF:VARCHAR(20):pk0; RF1:VARCHAR(20):pk0|
|非装配倒角允差|21|公称尺寸:REAL:pk1; 上偏差:VARCHAR(20):pk0; 下偏差:VARCHAR(20):pk0|
|非装配倒角尺寸|15|rsmin:REAL:pk1; r3:VARCHAR(20):pk0; r3_h:VARCHAR(20):pk0; r3_l:VARCHAR(20):pk0; r8:VARCHAR(20):pk0; r8_h:VARCHAR(20):pk0; r8_l:VARCHAR(20):pk0|


### DGBData.db

SHA-256 `4b0e9c56a4d216cf952ce13e31676c4e509130530b872d724a2dfe4c6186878f`

|表名|行数|列与主键（单位 BLOCKED）|
|---|---:|---|
|B级内圈技术条件|10|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|B级外圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|B级总图内圈技术条件|11|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|B级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|B级粗糙度表|11|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|C级内圈技术条件|9|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|C级外圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|C级总图内圈技术条件|10|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|C级总图外圈技术条件|12|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|C级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|D级内圈技术条件|11|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|D级外圈技术条件|14|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|D级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|D级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|D级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|E级内圈技术条件|13|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|E级外圈技术条件|15|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|E级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP89:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|E级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|E级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|G级内圈技术条件|13|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SI:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KI:VARCHAR(9):pk0; ΔBS:VARCHAR(9):pk0; VBS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|G级外圈技术条件|15|d:REAL:pk1; ΔDMP:VARCHAR(9):pk0; VDP9:VARCHAR(9):pk0; VDP01:VARCHAR(9):pk0; VDP234:VARCHAR(9):pk0; VDMP:VARCHAR(9):pk0; SE:VARCHAR(9):pk0; SD:VARCHAR(9):pk0; KE:VARCHAR(9):pk0; VCS:VARCHAR(9):pk0; deltaCir7891:VARCHAR(9):pk0; deltaCir234:VARCHAR(9):pk0; deltaCur:VARCHAR(9):pk0|
|G级总图内圈技术条件|19|d:REAL:pk1; d_l:VARCHAR(9):pk0; ZVDP9:VARCHAR(9):pk0; ZVDP01:VARCHAR(9):pk0; ZVDP234:VARCHAR(9):pk0; ZVDMP:VARCHAR(9):pk0; ZKIA:VARCHAR(9):pk0; ZSD:VARCHAR(9):pk0; ZSIA:VARCHAR(9):pk0; B_l:VARCHAR(9):pk0; B_lX:VARCHAR(9):pk0; ZVBS:VARCHAR(9):pk0|
|G级总图外圈技术条件|20|d:REAL:pk1; Dd_l:VARCHAR(9):pk0; ZVDdp89:VARCHAR(9):pk0; ZVDdp01:VARCHAR(9):pk0; ZVDdp234:VARCHAR(9):pk0; ZVDdp234B:VARCHAR(9):pk0; ZVDdmp:VARCHAR(9):pk0; ZKea:VARCHAR(9):pk0; ZSDd:VARCHAR(9):pk0; ZSea:VARCHAR(9):pk0; ZVcs:VARCHAR(9):pk0|
|G级粗糙度表|12|套圈直径:REAL:pk1; _Dds:VARCHAR(20):pk0; _Dde:VARCHAR(20):pk0; _Dd:VARCHAR(20):pk0; _ds:VARCHAR(20):pk0; _di:VARCHAR(20):pk0; _d:VARCHAR(20):pk0|
|fc_f0|40|Dw_Dpw:REAL:pk0; fc:VARCHAR(20):pk0; f0:VARCHAR(20):pk0|
|model|145|model:VARCHAR(50):pk1; d:INTEGER:pk0; Dd:INTEGER:pk0; B:INTEGER:pk0; rsmin:REAL:pk0|
|主参数|16|model:VARCHAR(50):pk1; Dw:VARCHAR(20):pk0; Z:VARCHAR(20):pk0; Dwp:VARCHAR(20):pk0; fai:VARCHAR(20):pk0|
|倒角尺寸表|25|rsmin:REAL:pk0; d:INTEGER:pk0; rsmax_r:REAL:pk0; rsmax_a:REAL:pk0; rs_r:VARCHAR(255):pk0; rs_r_Upper:VARCHAR(255):pk0; rs_r_Lower:VARCHAR(255):pk0; rs_a:VARCHAR(255):pk0; rs_a_Upper:VARCHAR(255):pk0; rs_a_Lower:VARCHAR(255):pk0; r3:VARCHAR(255):pk0; r3_Upper:VARCHAR(255):pk0; r3_Lower:VARCHAR(255):pk0; r8:VARCHAR(255):pk0; r8_Upper:VARCHAR(255):pk0; r8_Lower:VARCHAR(255):pk0|
|变量|195|变量名:VARCHAR(15):pk1; 变量值:VARCHAR(30):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|变量表|118|变量名:VARCHAR(255):pk0; 变量值:VARCHAR(255):pk0|
|实体保持架倒角|10|Dc:REAL:pk1; Ra:VARCHAR(50):pk0; Ra_h:VARCHAR(50):pk0; Ra_l:VARCHAR(50):pk0; Rmax:VARCHAR(50):pk0|
|密封圈89|109|model:VARCHAR(50):pk1; Ddm1:VARCHAR(20):pk0; Ddm1_h:VARCHAR(20):pk0; Ddm2:VARCHAR(20):pk0; Ddm2_h:VARCHAR(20):pk0; Ddm3:VARCHAR(20):pk0; Ddm3_h:VARCHAR(20):pk0; Ddm4:VARCHAR(20):pk0; Ddm4_h:VARCHAR(20):pk0; dm1:VARCHAR(20):pk0; dm1_h:VARCHAR(20):pk0; dm2:VARCHAR(20):pk0; dm2_h:VARCHAR(20):pk0; dm3:VARCHAR(20):pk0; dm3_h:VARCHAR(20):pk0; dm4:VARCHAR(20):pk0; dm4_h:VARCHAR(20):pk0; Pm:VARCHAR(20):pk0; Bm1:VARCHAR(20):pk0; Bm1_l:VARCHAR(20):pk0; Bm2:VARCHAR(20):pk0; Bm2_l:VARCHAR(20):pk0; Bm3:VARCHAR(20):pk0; Bm4:VARCHAR(20):pk0; Bm5:VARCHAR(20):pk0; Bm5_l:VARCHAR(20):pk0; Bm6:VARCHAR(20):pk0; Bm6_h:VARCHAR(20):pk0; DdH:VARCHAR(20):pk0; DdH_h:VARCHAR(20):pk0; dH:VARCHAR(20):pk0; dH_h:VARCHAR(20):pk0; SH:VARCHAR(20):pk0; SH_l:VARCHAR(20):pk0; H:VARCHAR(20):pk0; Rm1:VARCHAR(50):pk0; Rm2:VARCHAR(50):pk0; Rm3:VARCHAR(50):pk0|
|密封槽89|109|model:VARCHAR(50):pk1; Dd2_h:VARCHAR(20):pk0; Dd3:VARCHAR(20):pk0; Dd3_h:VARCHAR(20):pk0; Dd4:VARCHAR(20):pk0; Dd4_h:VARCHAR(20):pk0; b:VARCHAR(20):pk0; b_h:VARCHAR(20):pk0; b1:VARCHAR(50):pk0; R1:VARCHAR(50):pk0; d2_l:VARCHAR(50):pk0|
|止动槽|50|Dd:REAL:pk1; Dd1max:VARCHAR(9):pk0; Dd1min:VARCHAR(9):pk0; a0max:VARCHAR(9):pk0; a0min:VARCHAR(9):pk0; a234max:VARCHAR(9):pk0; a234min:VARCHAR(9):pk0; bmax:VARCHAR(9):pk0; bmin:VARCHAR(9):pk0; r0:VARCHAR(9):pk0|
|洛轴非装配倒角尺寸|20|rs:REAL:pk1; r2:VARCHAR(20):pk0; r3:VARCHAR(20):pk0; r5:VARCHAR(20):pk0; r8:VARCHAR(20):pk0|
|游隙|9|d:REAL:pk0; 2_B:VARCHAR(255):pk0; 2_S:VARCHAR(255):pk0; 0_B:VARCHAR(255):pk0; 0_S:VARCHAR(255):pk0; 3_B:VARCHAR(255):pk0; 3_S:VARCHAR(255):pk0; 4_B:VARCHAR(255):pk0; 4_S:VARCHAR(255):pk0; 5_B:VARCHAR(255):pk0; 5_S:VARCHAR(255):pk0|
|游隙_旧）|32|d:REAL:pk1; 2_B:VARCHAR(9):pk0; 2_S:VARCHAR(9):pk0; 0_B:VARCHAR(9):pk0; 0_S:VARCHAR(9):pk0; 3_B:VARCHAR(9):pk0; 3_S:VARCHAR(9):pk0; 4_B:VARCHAR(9):pk0; 4_S:VARCHAR(9):pk0; 5_B:VARCHAR(9):pk0; 5_S:VARCHAR(9):pk0|
|统一图册|109|model:VARCHAR(50):pk1; Dw:VARCHAR(20):pk0; Z:VARCHAR(20):pk0; Dwp:VARCHAR(20):pk0; dm:VARCHAR(20):pk0; L:VARCHAR(50):pk0; ai_h:VARCHAR(50):pk0; De:VARCHAR(50):pk0; De_h:VARCHAR(50):pk0; Dd2:VARCHAR(50):pk0; Dd2_h:VARCHAR(50):pk0; Re:VARCHAR(50):pk0; Re_h:VARCHAR(50):pk0; Dk:VARCHAR(50):pk0; ZG:VARCHAR(50):pk0; di:VARCHAR(50):pk0; d2:VARCHAR(50):pk0; d2_l:VARCHAR(50):pk0; Ri:VARCHAR(50):pk0; Dc1:VARCHAR(50):pk0; Dc:VARCHAR(50):pk0; S:VARCHAR(50):pk0; Rc:VARCHAR(50):pk0; Rc_h:VARCHAR(50):pk0; K:VARCHAR(50):pk0; rrc:VARCHAR(50):pk0|
|计算稿|289|段号:VARCHAR(15):pk0; 顺序号:REAL:pk1; 节号:VARCHAR(10):pk0; 内容:VARCHAR(180):pk0; 变量名:VARCHAR(10):pk0; 变量值:VARCHAR(50):pk0; 上偏差:VARCHAR(50):pk0; 下偏差:VARCHAR(50):pk0|
|记录|1|序号:INTEGER:pk1; 型号:VARCHAR(50):pk0; 日期:VARCHAR(50):pk0|
|轴承宽度公差|8|d:INTEGER:pk0; 0B_Upper:VARCHAR(255):pk0; 0B_Lower:VARCHAR(255):pk0; 2B_Upper:VARCHAR(255):pk0; 2B_Lower:VARCHAR(255):pk0; 3B_Upper:VARCHAR(255):pk0; 3B_Lower:VARCHAR(255):pk0|
|钢球标准尺寸|126|Dw:REAL:pk1; Inch:VARCHAR(8):pk0; deltab:VARCHAR(50):pk0|
|长铆钉尺寸及允差|9|dm:REAL:pk1; Ddm:VARCHAR(50):pk0; Ddm_h:VARCHAR(50):pk0; Ddm_l:VARCHAR(50):pk0; hm:VARCHAR(50):pk0; hm_h:VARCHAR(50):pk0; hm_l:VARCHAR(50):pk0; R:VARCHAR(50):pk0; dma:VARCHAR(50):pk0; ea:VARCHAR(50):pk0; lo:VARCHAR(50):pk0; Dm1:VARCHAR(50):pk0; hac:VARCHAR(50):pk0|
|防尘盖89|109|model:VARCHAR(50):pk1; DdF:VARCHAR(20):pk0; DdF_h:VARCHAR(20):pk0; DdF_l:VARCHAR(20):pk0; dF:VARCHAR(20):pk0; dF_h:VARCHAR(20):pk0; DdF1:VARCHAR(20):pk0; DdF2:VARCHAR(20):pk0; DdF3:VARCHAR(20):pk0; BF:VARCHAR(20):pk0; BF1:VARCHAR(20):pk0; BF2:VARCHAR(20):pk0; SF:VARCHAR(20):pk0; alfaF:VARCHAR(20):pk0; hF:VARCHAR(20):pk0; NF:VARCHAR(20):pk0; RF:VARCHAR(20):pk0; RF1:VARCHAR(20):pk0|
|非装配倒角允差|21|公称尺寸:REAL:pk1; 上偏差:VARCHAR(20):pk0; 下偏差:VARCHAR(20):pk0|
|非装配倒角尺寸|15|rsmin:REAL:pk1; r3:VARCHAR(20):pk0; r3_h:VARCHAR(20):pk0; r3_l:VARCHAR(20):pk0; r8:VARCHAR(20):pk0; r8_h:VARCHAR(20):pk0; r8_l:VARCHAR(20):pk0|

## CSV读取补充证据

本机 `D:/RotorStudio/ui_rotorstudio-9857bcc7afce658be15dfd2b559a55cb12b55bbd/NetLib/CSharpLib/FileOperation.cs:172` 的 FileIO.Csv2DataTable 先 DetectTextEncoding，再读首行拆列（逗号/Tab/分号），数据按同样分隔符拆分并Trim。遇行异常会返回已读的部分表；未来adapter应检查完整性并失败关闭，不沿用这种部分成功。该文件哈希已纳入audit.json，不修改原实现。
