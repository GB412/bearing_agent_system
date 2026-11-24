# PR-03：有来源的工程知识查询（初版历史记录）

> **历史版本声明（2026-11-24）**：本文件记录 PR-03 初版的关键词目录方案，**不再代表当前工具接口或验收协议**。当前运行实现是“RoBAS 精确目录 + 可选中文语义检索”，模型可见接口仅为 `lookup_engineering_knowledge(query, catalog_query=None)`，不再暴露 `topic`。状态以精确查询的 `FOUND/CATALOG_UNAVAILABLE`、概念检索的 `RELATED_EVIDENCE/NOT_FOUND` 等为准。请以 [PR-03 当前混合检索实施与验收](HYBRID_KNOWLEDGE_IMPLEMENTATION.md) 为唯一现行说明；下面仅作为历史资料保留。

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
| 内外圈配合原则 | 一般旋转套圈配合需防蠕动，实际需看载荷与材料 | [NTN 配合技术说明](https://ntnamericas.com/technical-resources/shaft-housing-fits/) | 已记录来源，未做专业审核 |
| 脂润滑通用特性 | 润滑脂更容易留存在轴承布置中 | [SKF 选脂说明](https://www.skf.com/il/products/super-precision-bearings/principles/bearing-selection-process/lubrication/suitable-grease) | 已记录来源，未做专业审核 |

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


## 第二轮完善：防止相关知识被误当作充分证据

这轮补充三个关键边界，仍然只使用小型本地目录和单个 Conversation Agent：

1. **匹配与答案覆盖程度分开**：`FOUND` 表示目录确实有可回答的事实；
   `NOT_FOUND` 表示无匹配资料；新增 `INSUFFICIENT_EVIDENCE` 表示有相关出处，
   但不足以给出用户要求的具体公差、游隙数值、黏度、载荷、型号变体信息。
   `INSUFFICIENT_EVIDENCE` 的 `results` 为空，背景来源单独放在
   `related_sources`，不得将其当作已回答的工程数据。
2. **范围收敛**：型号 `6206` 不得错误匹配 `62060` 或 `16206`；
   `6206-2RS` 不能自动继承只有开式 `6206` 的证据。CN/C3概念仍可查，
   但具体微米游隙范围不能从等级名称推出。k6/H7的具体配合公差、
   润滑脂牌号或黏度，以及6206的额定动载荷，都必须另有明确资料。
3. **来源跟踪**：每次知识工具调用的 `/trace` 记录结果的
   `knowledge_status`、`knowledge_ids`、`knowledge_source_urls`；
   不记录完整的模型自由查询作为所谓事实。目录初始化检查记录 ID 唯一、
   HTTPS 出处、数值事实单位、审核状态及适用范围，避免误将不完整记录对外暴露。

这些是**小目录的保守覆盖检查**，不是一般自然语言语义理解系统。
中文复杂说法仍可能逃过关键词判定；必须结合真实 DeepSeek 测试和专业人工复核，
不能宣称只靠正则保证工程数值绝不幻觉。

## 真实 DeepSeek API 专项验收（显式启用）

```powershell
conda activate bearing-agent
cd "D:\RotorStudio\bearing_agent_system"
git fetch origin
git switch feature/pr03-engineering-knowledge
git pull --ff-only origin feature/pr03-engineering-knowledge
python -m pip install -e ".[dev]"

# 不需要 API Key 的全套确定性回归：
python -m pytest -q tests -m "not live"
ruff check .
python examples/pr03_live_eval.py --help

# 如有 DeepSeek API Key，仅在当前终端安全输入：
$secure = Read-Host "DeepSeek API Key" -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
Remove-Variable secure
$env:DEEPSEEK_THINKING = "disabled"

# 真实模型：先 4 案例，再 8 案例（有付费 API 费用）：
python examples/pr03_live_eval.py --model deepseek-flash --max-cases 4
python examples/pr03_live_eval.py --model deepseek-flash --max-cases 8

# 复杂模型对照，可选：
python examples/pr03_live_eval.py --model deepseek-v4-pro --max-cases 8 --report artifacts/pr03_live/pro_results.json
```

默认报告写入 `artifacts/pr03_live/knowledge_results.json`，此路径被 Git 忽略，
包含用户测试句、模型自然语言回复、工具摘要、来源 URL、Token 使用与失败原因；
**不得含 API Key**，也不要将真实个人或商业机密对话原文公开提交。

本轮真实验收案例包括 SKF 6206 主要尺寸和出处、CN/C3 概念、CN/C3 具体游隙区间
不足、k6/H7 公差不足、GCr15 导热率缺失、脂润滑黏度证据不足、
SKF 6206-2RS 变体不能由 6206 自动证明，以及通用脂润滑特性。
这些案例要求知识查询**只读**；要求来源链接必须是工具实际返回的 URL。

离线 scripted 测试和测试评分器只能验证代码逻辑，不能代替真实模型调用；
**在无密钥情况下，真实 DeepSeek 验收状态仍为未执行**。
真实报告中的结构化校验也只是基础检查；仍需人工核对答复内容是否恰当、
是否发生跨厂商/型号的错误套用及是否含无出处的推断。

## PR-03 验收边界

不得新增专业参数默认值或在知识查询中直接修改 DesignBrief，
不新增 Agent，不开发 RAG 或 PR-04 的配置推荐/提案接受，
不引入 RoBAS 资源或声称源记录已通过工程人员审核。
GitHub CI/本地回归通过后，PR 仍保持 Draft，等待实测和用户批准后再合并。
