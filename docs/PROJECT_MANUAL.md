# 项目事实说明书

更新：2026-11-20。开发前核对实际分支与git rev-parse HEAD；不得把文档中的业务基线当当前HEAD。

当前仓库GB412/bearing_agent_system，GitHub PR#1；阶段PR-00；分支docs/pr-00-robas-quasi-static-input-audit；修改业务基线02861ea09e77906f4360ed1e3e9c7268a0c9ea1f。当前修改未提交，提交引用见追加变更记录。原基线没有本文件，本次补建。

事实、进度和问题入口：[MASTER_PLAN](00_MASTER_PLAN.md) 第10/14节；[PR-00报告](pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md) B01–B10；[测试证据](pr00/VALIDATION.md)；[变更记录](PROJECT_CHANGELOG.md)。状态词汇与证据分级见MASTER_PLAN第14节。

43记录/324字段源码及资源审计工件已完成，工程冻结BLOCKED。材料/润滑是CSV读取，不是SQLite物性表。原版UI已只读查看，历史DGB留存DATA已核对；本次没有执行真实EXE求解，没有同次目标工况案例，不宣称收敛或工程有效。完整输入转换与对话Agent均NOT_IMPLEMENTED。审计工具等级和实际测试以VALIDATION为准。

后续技术限制：Python3.11+/Pydantic/LangGraph；StateManager唯一受信写入入口；不得伪造用户确认/硬约束来源；保留既有PR-01安全契约，不用预校核代替DLAP性能验证。当前不实现业务、不修改原版DATA/SQLite/EXE、不改Bearing_CAD架构、不合并、不开始PR-01。规划冲突先报告。
