# Bearing Agent System

多 Agent 轴承设计系统的新一轮开发仓库。当前从深沟球轴承（DGB）需求分析开始，先实现一个能够多轮理解用户需求、补齐拟静力学计算输入并生成结构化设计任务的对话 Agent。

## 当前阶段

**PR-00：RoBAS 8.11 DGB 拟静力学输入审计与规划。**

当前仓库以规划和审计文档为主，尚未实现 Agent、优化器或求解器集成代码。第一版限定 DGB、RoBAS 拟静力学 Mode=-1；优化模块暂不加入 Agent。

## 关键文档

- [总体规划](docs/00_MASTER_PLAN.md)
- [PR-00 审计任务与验收标准](docs/pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md)
- [DGB 43 条 DATA 记录输入矩阵（工作底稿）](docs/parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md)

## 基本原则

- 对话结果应能转换为 RoBAS 拟静力学输入模板；五个内部几何优化变量暂留给后续优化模块。
- 推荐值只有用户接受后才标记为 confirmed；确认状态仅使用 confirmed / unconfirmed。
- 所有参数保留来源、单位和必要的版本/记录标识。
- 不静默继承未经确认的参考 DATA 默认值，不编造材料、润滑或工程阈值。
- 代码实现、自动化测试、原版源码对照、Windows 实机运行和工程审核分别报告，不混为一谈。

## 当前不在范围内

参数优化算法、代理模型、优化 Agent、多轴承类型完整支持、动力学求解、CAD/二维图纸/三维模型集成。
