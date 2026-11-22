# PR-03：有来源的工程知识查询（最小实现）

## 本 PR 做什么

在已有 Conversation Agent 上增加第三个只读工具
`lookup_engineering_knowledge(topic, query)`。数据来自随包安装的
`src/bearing_agent_system/knowledge_records.json`。这是小型结构化目录，不是 RAG、
推荐算法或 RoBAS 的完整数据库迁移。

- 支持主题：`bearing_model`、`clearance`、`material`、`lubrication`、`fit`。
- 有匹配资料：`FOUND`，逐条返回事实、来源链接、适用范围、限制和审核状态。
- 没资料：`NOT_FOUND`，不从模型记忆猜测产品数值或配合公差。
- 非法主题/空查询：`INVALID_TOPIC` / `INVALID_QUERY`。
- 工具不写 DesignBrief、不新增 confirmed、不改变修订号。
- 通用术语允许 Agent 直接解释；具体型号、标准表数值应先查资料。

## 初始数据及证据边界

| 资料 | 本地事实 | 来源 | 状态 |
|---|---|---|---|
| 6206 单列深沟球轴承 | d=30、D=62、B=16 mm | [SKF 6206 产品页](https://www.skf.com/si/products/rolling-bearings/ball-bearings/deep-groove-ball-bearings/productid-6206) | 已记录来源，未做专业审核 |
| CN 与 C3 | CN 为普通径向游隙、C3 比普通等级大 | [NTN 工程 FAQ](https://ntnamericas.com/technical-resources/faqs/) | 已记录来源，未做专业审核 |

`review_status=SOURCE_DOCUMENTED_NOT_ENGINEERING_REVIEWED` 表示**出处已记录，不代表
工程人员已审核，更不代表用户已选择该项**。6206 数据仅包含所引产品的主要外形尺寸；
CN/C3 数据没有具体游隙数值范围。工具和模型不应据此声称寿命达标、配合适用或已完成
工程设计。

## 数据审核与后续 PR-04 准备

PR-00 定位到 RoBAS `Resource/materialDB.csv`、`Resource/lubricantDB.csv`
和轴承型号 SQLite，但这些原始资源不在 Agent 仓库里，历史审计也发现
个别物性异常、表间关联缺口。**本 PR 不复制、编造或自动批准这些记录**。

PR-04 前须由专业人员或受控资料核实：材料物性、润滑剂牌号及适用条件、
6206 游隙区间和装配后的工作游隙、k6/H7 适用前提等，再选取少量明确适用工况的配置。
没有审核数据时，推荐工具应返回无可验证配置，而不是硬编码默认方案。

## 如何测试

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests -m "not live"
ruff check .
python -m bearing_agent_system.chat_cli --model deepseek-flash
```

可以在 CLI 自然问“6206 的标准外形尺寸是多少？出处是什么？”、“CN 和 C3 有何区别？
6206 具体游隙范围是多少？”、“GCr15 的导热率是多少？”。

验收要求：前两问应引用实际查到的资料、明确局限；第三问在当前目录中应表示
无法给出可靠数值；所有知识查询只读；原有参数写入及多轮对话测试回归通过。

离线 scripted-model 测试只能验证代码调用链及确定性行为；**真实 DeepSeek 是否会在需要时
自主调用第三工具，仍需本地有效 API 凭据复测**。本 PR 不调用 RoBAS EXE。
