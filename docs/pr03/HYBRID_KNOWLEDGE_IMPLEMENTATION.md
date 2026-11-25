# PR-03 混合工程知识查询：运行与验收

## 范围与接口

本 PR 沿用一个 Conversation Agent 和一个知识工具 `lookup_engineering_knowledge`。
不引入推荐 Agent、规则引擎或 RoBAS 求解功能。

- **普通概念**：模型可以直接解释。若需要外部依据，可调用知识工具。
- **RoBAS 支持项、精确目录数值**：调用知识工具；没有本地目录时不编造。
- **工程选型问题**：模型可查询来源明确的说明，解释影响因素；不能将资料匹配等同于适用性认可。
- **知识工具无资料**：允许模型回答稳定的一般原理，必须说明缺乏外部证据；不能生成厂家数值、RoBAS 目录值或求解结果。
- **用户确认参数**：仍经可信的 `update_design_brief` 完成，知识工具只读。

新调用接口：`lookup_engineering_knowledge(query, catalog_query=None)`。
DeepSeek 只能看到 `query` 和可选的 `catalog_query`；旧 `KnowledgeRepository.lookup(topic,query)` 仅内部兼容，不进入模型工具 schema。

### 精确目录查询

```json
{"query":"系统支持哪些材料？","catalog_query":{"entity_type":"material","operation":"list"}}
```

```json
{"query":"查询6206型号目录静载荷原值","catalog_query":{"entity_type":"bearing_model","operation":"get","name":"6206","field":"C0_source"}}
```

`entity_type` 限于 `material`、`lubricant`、`bearing_model`，`operation` 限于 `list`、`get`，字段限于数据库中确实存在的列。型号名称必须精确匹配；对原表尾随 `*` 的基本型号允许去掉该符号后匹配，其他型号后缀不得自动继承。材料和润滑剂原始数字**保留字符串原值**，不根据工程经验修正数值。来源包括 ZIP SHA-256、单文件 SHA-256、CSV 行号或 SQLite 主键。

原始表的 `C/C0/nmax` 值保留原单位定义待核实状态，不在查询工具里自行乘以1000或解释为新轴承结构设计性能。

### 本地目录提取

原始 RoBAS 数据因来源授权限制不直接纳入源代码仓库。
使用已获得授权的原始 `RoBAS_Resources.zip` 在本机执行：

```bash
python scripts/extract_robas_catalog.py --archive /path/to/RoBAS_Resources.zip --output .bearing_agent/robas_catalog.json
```

查询模块默认读取 `.bearing_agent/robas_catalog.json`，也可设置 `ROBAS_CATALOG_PATH` 为实际路径。

2026-11-24 对提供的原始文件核对：SHA-256 `d5b072f08f3a76e283d35215e91097d88a1702e6ff5f3c6675cc726d3e73b626`；导出材料13条、润滑剂31条、`bearing.db/T_SKFA01`型号418条。示例原值：材料“高碳铬轴承钢”泊松比字段 `3.60E-07`；目录型号 `6206 *` 的 `C0` 原值 `11.2`（这里不推断原库单位和工况适用性）。

### 工程知识语义检索

知识正文和元数据留在 `knowledge_records.json`，每条有唯一 ID、标题、内容、适用条件、限制及来源。语义检索用离线本地模型，构建可重建的向量缓存；通过相关性下限筛选最多3条候选，相关度不足返回 `NOT_FOUND`，不再无条件返回前三条。相关性不代表证据已覆盖用户询问的具体数值。

单独安装可选依赖：

```bash
python -m pip install -e ".[dev,semantic]"
```

推荐本地缓存的中文模型：`BAAI/bge-small-zh-v1.5`。请提前在具备网络和许可的环境下载到模型缓存；运行期只从本地加载，不隐式下载。可用 `BEARING_KNOWLEDGE_EMBEDDING_MODEL` 指定本地路径或模型名称。语义模型不可用时返回 `retrieval_method=lexical_fallback`，该模式只支持明确的词面重合，不承诺理解口语改写；无明确相关性返回 `NOT_FOUND`，不可谎称执行了 Embedding。此时专门测试记录降级状态；验收语义检索时必须用真实模型且确认 `retrieval_method=embedding`。

不把知识目录 ID 塞入 Prompt，不为每条知识写关键词规则。枚举字段增加最小的明确用户选择校验，阻止问答/否定句误写为 `confirmed=true`；其余设计参数仍由 PR-01 服务受信写入。

### 运行验证

```bash
python -m pytest -q tests -m "not live"
python -m ruff check .
python examples/pr03_semantic_smoke.py --allow-download  # 首次运行明确允许下载中文模型；以后省略此参数
python examples/pr03_live_eval.py --model deepseek-flash --max-cases 8
```

本次新增的测试覆盖精确字段与型号匹配、原始数值不修改、语义编码器选点、目录缺失时安全返回。需要另外运行真实 DeepSeek 设计多轮验证：参数未确认不得保存、目录未安装不能假装有支持项、工具无资料可以解释一般概念、RoBAS数值来源可追溯。

**当前状态**：仍为 Draft PR；实现与单元测试不等于真实 API 或工程数值求解验收；未获用户明确批准不合并。


### 用户推荐采纳（沿用三个工具和 ReAct）

现有 `update_design_brief` 工具增加三种操作，不增加独立 Agent 或新的工具：

- `operation=propose`：只能登记**工程选项类** path/value（例如润滑方式、材料、保持架），SQLite 保存一条当前待采纳推荐，**不修改 DesignBrief**，不会把模型建议伪装成用户确认。数值优化变量、尺寸、载荷、硬约束不能通过此入口写入。
- `operation=accept`：用户后续说“就按你推荐的来”等明确采纳语句时，将当前原话作为批准证据；参数直接从同会话 SQLite 推荐记录读取，不需要复述具体推荐值，且不能越过已修改的 DesignBrief revision。
- `operation=delegate`：用户当轮明确授权指定领域“你来决定/指定”，模型先执行对应工程知识查询并提出具体候选，才能在同轮采用**初步、未工程校核**的选择。仅要求推荐不代表授权采用；知识记录只是相关背景，不能宣称专业校核合格。

采纳记录的 `source.kind=derived`、`source.ref=proposal_id` 和 `note` 区分用户接受与用户授权，`evidence_status=UNVERIFIED`；`/brief` 还展示当前 `pending_recommendation`。任何人工已保存的不同值都不会被推荐悄悄覆盖。当前每会话只保留一条可采纳推荐，更早的推荐自动失效。

离线回归：`python -m pytest -q tests -m "not live"`，重点检查 `tests/test_pr03_recommendation_adoption.py`。真实 DeepSeek 需单独执行多轮：先“请推荐一种润滑方案，暂不采用”，再“按你推荐的来”，通过 `/brief`、`/trace` 验证；“润滑你来推荐和指定”在工程依据不足时允许拒绝自动采用。

**边界**：本阶段是对话授权和初步选项采纳的基础设施，并非专业工程参数推荐算法或 RoBAS 校核；跨轮旧用户数字自动补交仍需独立评估。

### 最终 PR-03 审查验收事项

- **用户选择可信性**：仅讨论脂/油润滑时不得擅自确认润滑模式；游隙和配合仍可查询概念，但依据 DesignBrief/v2 不再进入任何用户参数写入或提案。
- **模型可见工具合同**：`lookup_engineering_knowledge(query, catalog_query=None)`；概念查询使用 `RELATED_EVIDENCE`（相关但非充分），`NOT_FOUND` 表示相关性不足；目录查询具有 `FOUND`、`CATALOG_UNAVAILABLE`、`INSUFFICIENT_EVIDENCE` 等明确状态。
- **来源日志**：`/trace` 除记录 ID、网页 URL 外，还保存 `retrieval_method`、本地 `source_id`、源文件 SHA-256、行号/主键和原始字段名，避免本地目录更新后无法重现。
- **Embedding 真实验收**：`python examples/pr03_semantic_smoke.py` 默认只加载已有缓存，不会联网；只有 `--allow-download` 才明确允许下载。该脚本要求实际 `retrieval_method=embedding`，核查口语改写和无关查询的区分效果。当前 0.53 相似度下限是**小规模真实中文样本校准后的暂定值**，不能因 DummyEncoder 测试通过而宣称已完成中文语义能力验收。
- **真实 DeepSeek 验收**：`examples/pr03_live_eval.py` 评分器按新状态协议；一般术语允许直接回答，只有具体厂家出处/目录请求才要求工具调用。实时模型完成与否以实际 API 记录和人工核对为准。
- **RoBAS 资源**：默认路径 `.bearing_agent/robas_catalog.json` 是本地生成文件，**不会提交 GitHub**；也可用 `ROBAS_CATALOG_PATH` 指向已提取完整 JSON。未放置资源时返回 `CATALOG_UNAVAILABLE` 是符合预期的安全状态。

本文件是 PR-03 的**唯一当前实施与验收文档**；旧 `IMPLEMENTATION.md` 仅作为初版历史说明。


### 简化材料/润滑剂选择合同（PR-03 最终补丁）

不增加 Agent、工具、Embedding 规则或模糊别名库。**用户最终输入目录原始标准名称**；程序可接受确切目录 ID（用于已有待采纳提案），实际存储 `_id` 字段为目录规范 ID，未来适配层通过 ID 查询原始名称和物性。

- 涵盖 `engineering.materials.inner_ring_id`、`outer_ring_id`、`ball_id`、
  `engineering.cage.material_id`、`engineering.lubrication.lubricant_id`。
  `engineering.lubrication.mode` (`oil/grease/other`) 不需要目录即可按原规则保存，
  不应把润滑方式与具体润滑剂混为一谈。
- `CatalogChoices.resolve(path, name_or_id)` 读取 `ROBAS_CATALOG_PATH`（默认
  `.bearing_agent/robas_catalog.json`），要求 `RoBASCatalog/v1`、目录 ID 和名称唯一；
  只接受**完全一致**的标准名称或实际记录 ID，拒绝大小写猜测、拼写修正、
  相似材料或未经核实的等价牌号。
- 用户直接写入、`propose` 生成推荐、`accept/delegate` 采纳都由
  `SQLiteDesignBriefStore` **统一执行目录校验**，而不是单靠 Prompt。
  `propose` 保存规范 ID，`accept/delegate` 在提交前重新查目录；
  若记录消失或目录不可用则拒绝，不修改已确认 DesignBrief。
- 无匹配时返回 `CATALOG_NOT_FOUND`；目录未安装返回 `CATALOG_UNAVAILABLE`；
  目录结构损坏/名称重复返回 `CATALOG_ERROR`。未命中不等于材料不适合；
  Agent 可继续用现有 `lookup_engineering_knowledge` 的 `list/get`
  展示合法名称，请用户重新选择。
- `tests/conftest.py` 使用**合成目录**做离线单测，不能据此证明真实 RoBAS
  已安装、某一材料真正存在或其物性适合工况。运行真实 DeepSeek 前先确认
  本地目录已由授权来源准备，缺失时无需修改测试期假数据来伪造生产选项。

工程边界：目录存在仅证明系统记录可用，**不等于材料物性已经核验或润滑剂适用**。
RoBAS 历史 CSV 润滑剂物性可能是润滑油数据，不能将任意记录当作润滑脂。
未来计算时应保留目录来源版本/哈希进行一致性检查，不静默继承未经核验的原始数值。

验证：`python -m pytest -q tests -m "not live"`、`ruff check .`；
新增 `tests/test_pr03_catalog_guard.py` 覆盖规范 ID、无效选项、目录缺失、
重复名称、跨类型错配、提案与采纳时目录发生变化等场景。
