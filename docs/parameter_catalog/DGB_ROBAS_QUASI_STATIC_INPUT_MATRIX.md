# DGB RoBAS 8.11 拟静力学 43 条输入记录盘点（PR-00 工作底稿）

- 状态：初始盘点，非最终审计结论
- 协议范围：DGB 球轴承，Mode=-1，43 条记录
- 基线：Bearing_CAD 当前 main 的 robas_data.py、robas_ball_input.py 和 robas-solver02-ball-data-mapping.md
- 注意：本表依据当前迁移文档整理。原版 C#、SQLite、Windows UI 逐字段复核前，不视为最终正确映射。

## 状态标记

- MAPPED-CODE：当前 Bearing_CAD 有代码映射，原版适用性仍需核对。
- PROFILE：当前主要来自原版 DATA 参考 profile。
- OPT：后续优化变量，当前留待优化。
- USER-GAP：需要用户/工况来源，但当前 API 未完全暴露。
- AUDIT：必须从原版 C# / SQLite / UI 进一步核实。
- UNKNOWN：当前证据不足。

| 序号 | 记录标签 | 字段 | 当前初步来源/说明 | 状态 |
|---:|---|---|---|---|
| 1 | rec 1 | Mode, kDCR, kDOF, klcOpt, kFnOpt, kPrtOpt, kPrtFreq, kPltFreq, kAGraf, kLifeFreq, kTherm, maxStps, nStps, intMet | Mode=-1；其余为 BaseSolver/profile 配置，nStps 有有限覆盖 | PROFILE/AUDIT |
| 2 | rec 2.1 | stpInit, stpMin, stpMax, fTime, Tol, qFac | BaseSolver 数值设置，当前来自参考 DATA | PROFILE/AUDIT |
| 3 | rec 2.2 | kFD11, kFD21, kFD31, kFD12, kFD22, kFD32, kMD11, kMD21, kMD31, kMD12, kMD22, kMD32 | 载荷/力矩控制标志，来自 profile；需与工况分量对应 | PROFILE/USER-GAP |
| 4 | rec 2.3 | finName, pltNames1..pltNames9 | 输出文件名，受支持的原版文件名配置 | PROFILE |
| 5 | rec 3.1 | runId | 每次运行生成的标识 | MAPPED-CODE |
| 6 | rec 3.2 | kUnit, kBrg, nRe, nCseg, kRaceFlex, kReGeoImp, kRaceGeoImp1, kRaceGeoImp2, kFlngInd11, kFlngInd12, kFlngInd21, kFlngInd22 | kUnit=1、kBrg=1；nRe 对应 Z；其他多为 profile/求解配置 | OPT/PROFILE |
| 7 | rec 3.3 | kStaticConstraint1..5, kAngVel, kStif, kChrn, kReMat, kRaceMat1, kRaceMat2, kHsngMat, kShftMat, kLifeCons | 静态约束、运动/刚度开关和材料模式码 | PROFILE/AUDIT |
| 8 | rec 3.4 | kRotLoad, kRotFrame, kReIP, kRaceIP1, kRaceIP2, kNumPltElem, kPltElemInd1..6 | 旋转载荷/参考系/输出元素索引；部分索引按 nRe 派生 | PROFILE/DERIVED |
| 9 | rec 3.5 | kCoolant, kBaseTemp, kHTC, kGeoMod, kMatPropMod | 冷却、热边界、几何/材料属性模式 | PROFILE/AUDIT |
| 10 | rec 4 | brgBore, brgOD, shftID, hsngOD, raceWidth1, raceWidth2 | bore/OD/width 可由设计几何映射；shftID、hsngOD 当前迁移逻辑有派生公式，需原版来源复核 | MAPPED-CODE/DERIVED |
| 11 | rec 5A | bReDia, pitchDia, freeConAngDeg, freeIntCls, raceCurFac1, raceCurFac2, shoulderDia1, shoulderDia2, shimThickness1, shimThickness2, rmsAspHt1, rmsAspHt2 | bReDia=Dw；pitchDia=Dpw；raceCurFac1/2 暂对应 fo/fi；freeIntCls、shim、粗糙度等部分继承 profile | OPT/PROFILE/AUDIT |
| 12 | rec 7.0 | kPoctype, kCagePocImp, kCageGsImp, kRaceGsImp, kPocHydro, kGsHydro, kCageMat, kCageIP, nGL, iCageGuide1..4 | 保持架/流体模型设置；部分由 DGB SetAnalysisValue 写入，材料模式和其他字段来自 profile | PROFILE/AUDIT |
| 13 | rec 7.1 | cageDia1, cageDia2, cageWidth, cageCls1, cageCls2, bPocCls1, bPocCls2, cageAngCut, cageConeAng | 当前 DGB cage 几何有源码顺序派生；部分字段仍继承 profile | MAPPED-CODE/PROFILE |
| 14 | rec 7.2.x | cageGsDia1, cageGsWidth1, cageGsPos1, cageGsCls1 | 当前代码按保持架几何派生 | MAPPED-CODE/DERIVED |
| 15 | rec 7.2.x | cageGsDia2, cageGsWidth2, cageGsPos2, cageGsCls2 | 当前代码按保持架几何派生 | MAPPED-CODE/DERIVED |
| 16 | rec 8.1 | density, elasticModules, poissonRatio, thermalExpansion, specificHeat, conductivity, strainLimit, hardness, wearCoeff, misis | 滚动体材料属性；材料记录或 profile，字段完整性需 SQLite 核查 | PROFILE/AUDIT |
| 17 | rec 8.2.1 | 同 rec 8.1 的 10 个材料字段 | 外圈材料属性 | PROFILE/AUDIT |
| 18 | rec 8.2.2 | 同 rec 8.1 的 10 个材料字段 | 内圈材料属性 | PROFILE/AUDIT |
| 19 | rec 8.3 | density, elasticModules, poissonRatio, thermalExpansion, conductivity | 轴材料属性；当前 CAD 不含轴材料 | PROFILE/USER-GAP |
| 20 | rec 8.4 | density, elasticModules, poissonRatio, thermalExpansion, conductivity | 轴承座材料属性；当前 CAD 不含座材料 | PROFILE/USER-GAP |
| 21 | rec 8.5 | 同 rec 8.1 的 10 个材料字段 | 保持架材料属性，需与 rec 7.0 材料模式一致 | PROFILE/AUDIT |
| 22 | rec 8.6.0 | sProb, brgWbDis | 材料/寿命全局参数，当前来自原版全局默认或 profile | PROFILE/AUDIT |
| 23 | rec 8.6.1 | fcO1, fcLP1, shExLP1, depExLP1, fcGZ1, shExGZ1, fcIH1, shExIH1, depExIH1, wbDis1 | 外圈材料寿命属性 | PROFILE/AUDIT |
| 24 | rec 8.6.2 | 同 rec 8.6.1 的 10 个寿命字段 | 内圈材料寿命属性 | PROFILE/AUDIT |
| 25 | rec 8.6.3 | 同 rec 8.6.1 的 10 个寿命字段 | 滚动体材料寿命属性 | PROFILE/AUDIT |
| 26 | rec 8.6.4 | rmsAspSlp1, shearLmt1, aspTrac1, facMat1, facCont1, facProc1, facMatLF1, facProcLF1, hardnessLF1 | 外圈接触/寿命属性 | PROFILE/AUDIT |
| 27 | rec 8.6.5 | 同 rec 8.6.4 的 9 个字段 | 内圈接触/寿命属性 | PROFILE/AUDIT |
| 28 | rec 8.6.6 | facMatRe, facContRe, facProcRe, facMatLFre, facProcLFre, hardnessLFre | 滚动体接触/寿命属性 | PROFILE/AUDIT |
| 29 | rec 9.0 | roomTemp, raceFit1, raceFit2, angVelOrt, resStress1, resStress2, facStrLimit | 室温、配合、角速度方向和残余应力等；用户安装/工况数据或 profile | USER-GAP/PROFILE |
| 30 | rec 9.1.1 | appLoadX, appLoadY, appLoadZ, appDispX, appDispY, appDispZ | 外加载荷分量、位移约束；需用户提供并明确 DATA 坐标轴 | USER-GAP |
| 31 | rec 9.1.2 | appMomY, appMomZ, appMis11, appMis21, appMis12, appMis22, rpm1, rpm2 | 力矩、错位、内外圈转速；API 当前只暴露速度，不完整暴露其他项 | USER-GAP |
| 32 | rec 9.1.3 | hsngTemp, shftTemp, raceTemp1, raceTemp2, reTemp, cageTemp | 壳体、轴、滚道、滚动体和保持架温度；用户/热边界或 profile | USER-GAP/PROFILE |
| 33 | rec 9.2 | pctDisp, rpmRange11, rpmRange21, rpmRange12, rpmRange22 | 转速扫描范围；部分端点与 BaseBC 转速 setter 联动，其余来自 profile | PROFILE/USER-GAP |
| 34 | rec 9.5 | pocLubFilm, wvRatio, avRatio, cageGcPosX/Y/Z, cageAngPosX/Y/Z | 润滑膜/速度比和保持架初始位置等；需核实用户输入、派生或 profile | PROFILE/AUDIT |
| 35 | rec 9.6 | baseTemp, cFlowRate, cPres, reHTC, cageHTC, aveTime, skipTime | 热边界和求解时间参数 | PROFILE/USER-GAP |
| 36 | rec 9.7 | xRo, xMu, xCp, xK | 原版润滑剂/流体物性参数 | ROBAS_DATABASE/PROFILE |
| 37 | rec 10.0 | kTrac, kTracType, kCPTrac, kCPTracType, kCRTrac, kCRTracType, kRFTrac, kRFTracType, kRRTrac, kRRTracType, iTherm | 牵引/接触/热模型选择开关 | PROFILE/AUDIT |
| 38 | rec 10.1C | reRaceTC1..4 | 滚动体-滚道接触模型参数 | ROBAS_DATABASE/PROFILE |
| 39 | rec 10.3 | reRaceFilm, strParam | 滚动体-滚道油膜/模型参数 | ROBAS_DATABASE/PROFILE |
| 40 | rec 10.5.1B | reCageTC1..4, reCageFilm | 滚动体-保持架接触/润滑模型参数 | ROBAS_DATABASE/PROFILE |
| 41 | rec 10.5.2B | cageRaceTC1..4, cageRaceFilm | 保持架-滚道接触/润滑模型参数 | ROBAS_DATABASE/PROFILE |
| 42 | rec 10.6 | pocVis, gsVis | 保持架 pocket/guide 黏度；当前 API 仅在对应模式下允许覆盖 | ROBAS_DATABASE/PROFILE |
| 43 | rec 11 | gravityVecX, gravityVecY, gravityVecZ | 重力向量；当前来自 profile 或显式设置 | USER-GAP/PROFILE |

## 初步结论

- 本表列出了 43 条记录的字段组，但多数尚未完成原版源码和 SQLite 级别逐字段审计。
- 当前迁移代码能更新部分几何、运行条件、材料、润滑和 solver 字段；不能据此认为所有 43 条记录均已由用户需求覆盖。
- profile 值必须逐字段判断是否可安全复用，并要求 profile 身份、来源、哈希和适用性确认。
- bReDia、nRe、pitchDia、raceCurFac1、raceCurFac2 是五个优化变量的初步映射；PR-00 必须核对原版 SetAnalysisValue、字段方向、单位和真实 DATA。
- 五变量暂不赋值时，不生成可执行 DATA；保留模板和缺项报告。
