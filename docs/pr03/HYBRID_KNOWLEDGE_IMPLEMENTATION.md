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
为避免旧测试失效，`lookup_engineering_knowledge(topic=...,query=...)` 兼容旧式接口。

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

知识正文和元数据留在 `knowledge_records.json`，每条有唯一 ID、标题、内容、适用条件、限制及来源。语义检索用离线本地模型，构建一个可重建的向量缓存，并用余弦相似度返回最多3条相关知识。相关性不代表证据已覆盖用户询问的具体数值。

单独安装可选依赖：

```bash
python -m pip install -e ".[dev,semantic]"
```

推荐本地缓存的中文模型：`BAAI/bge-small-zh-v1.5`。请提前在具备网络和许可的环境下载到模型缓存；运行期只从本地加载，不隐式下载。可用 `BEARING_KNOWLEDGE_EMBEDDING_MODEL` 指定本地路径或模型名称。语义模型不可用时返回 `retrieval_method=lexical_fallback`，不可谎称执行了 Embedding。此时专门测试记录降级状态；验收语义检索时必须用真实模型且确认 `retrieval_method=embedding`。

不把知识目录 ID 塞入 Prompt，不为每一条知识写关键词规则。已有安全写入工具不改。

### 运行验证

```bash
python -m pytest -q tests -m "not live"
python -m ruff check .
python examples/pr03_live_eval.py --model deepseek-flash --max-cases 8
```

本次新增的测试覆盖精确字段与型号匹配、原始数值不修改、语义编码器选点、目录缺失时安全返回。需要另外运行真实 DeepSeek 设计多轮验证：参数未确认不得保存、目录未安装不能假装有支持项、工具无资料可以解释一般概念、RoBAS数值来源可追溯。

**当前状态**：仍为 Draft PR；实现与单元测试不等于真实 API 或工程数值求解验收；未获用户明确批准不合并。
