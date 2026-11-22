# PR-02 · DeepSeek ReAct Conversation Agent（待验收）

> GitHub PR #4 为 Draft，**叠加在尚未合并的 PR-01 #3 上**。本 PR 只实现单一 DGB 需求 Conversation Agent、工具①②与真实 DeepSeek 测试入口；不合并后续阶段功能。

## 一、架构及职责

- `conversation.py`：基于 `langchain.agents.create_agent`（LangGraph 运行时）的有界单 Agent 回合；模型自主决定工具调用、提问与回答；回合有 `turn_id`，可查看当前只读 `draft()`。
- `agent_prompt.py`：自然语言参数抽取、明确证据、范围/单位、用户不知道、临时插问以及工程资料未审核时的回复约束；不会把当前缺项变成固定问卷。
- `agent_tools.py`：仅暴露 `update_design_brief`、`get_design_status`；`session_id`、`message_id`、完整用户原话均由程序注入，模型不得指定。工具调用限额、重复调用拒绝和真实结果 trace。写入走 PR-01 `DesignBriefService`，工具顺序受单进程串行锁控制。
- `conversation_store.py`：SQLite 存放最简用户/助理对话回合，**不是第二份工程参数副本**；从当前 DesignBrief 加载唯一可信的参数状态；已提交或不确定中断的同一 turn ID 不自动重放工具写入。
- `llm_client.py`：DeepSeek Chat Completions / LangChain ChatOpenAI 客户端，使用 `DEEPSEEK_API_KEY`；默认 `deepseek-flash`、`https://api.deepseek.com`。
- `chat_cli.py`：终端聊天，`/status` 状态、`/brief` 草案、`/trace` 工具摘要、`/new` 新会话及 `/exit` 退出。
- `tests/test_pr02_conversation.py`：使用 scripted 模型通过**真实 LangGraph 执行路径**测试工具调用，但不访问外网、不消耗 API。
- `examples/pr02_live_eval.py`：20 个可重复的 DeepSeek 黄金案例，真实逐轮请求模型，并核对最终 SQLite 状态；测试报告保存到被 Git 忽略的本地目录。

设计边界：无 Supervisor、无第二规划 Agent、无问句优先级算法、无材料/润滑专家推荐、无知识检索、无 RoBAS、无 CAD。用户层 DesignBrief 的完整交付仍属于 PR-05。

## 二、安装与基本演示（Windows PowerShell）

```powershell
conda activate bearing-agent
cd "D:\RotorStudio\bearing_agent_system"
git fetch origin
git switch -c feature/pr02-deepseek-react --track origin/feature/pr02-deepseek-react
python -m pip install -e ".[dev]"

# 安全设置：只在当前 PowerShell 会话输入，不写入代码/日志
$secure = Read-Host "DeepSeek API Key" -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
Remove-Variable secure
$env:DEEPSEEK_MODEL = "deepseek-flash"
$env:DEEPSEEK_THINKING = "disabled"

python -m bearing_agent_system.chat_cli --model deepseek-flash --session demo-001
```

如果本地已经存在同名分支，请改用 `git switch feature/pr02-deepseek-react` 和 `git pull --ff-only`。数据库默认保存在被 Git 忽略的 `.bearing_agent/brief.sqlite3`。不应把 API Key 发到聊天、GitHub issue、测试报告或提交里。

### 对话测试建议

1. “我要设计深沟球轴承，尺寸25×52×15mm，内圈18000rpm，外圈固定。”
2. “径向载荷300N，没有轴向载荷，温度大约60℃。”
3. “先解释游隙，暂时不想填写材料。”
4. 输入 `/status` 或 `/brief`，核对 JSON 数据是否正确。
5. “把内圈转速改为15000rpm。”，检查 `revision` 和 SQLite 实际值。
6. “外径不能超过52mm。”，检查约束列表而非确认 `D=52`（如果原来已经确认了 D=52，该语句应仅添加约束）。
7. “把刚才外径上限改为60mm。”，检查旧约束 ID 的替换；使用 `/trace` 看更新结果。

程序会真实调用 DeepSeek，不使用 Mock 自动生成交互回复。API 无法访问或密钥未配置时会明确报错，不会回退成假模型。

## 三、自动化与真实测试严格分离

```powershell
# 本地确定性和离线脚本模型测试：无需 API Key
python -m pytest -q tests -m "not live"
ruff check .
python examples/pr01_demo.py

# 有密钥时，明确启用 5 个真实付费 API 场景
$env:RUN_DEEPSEEK_LIVE = "1"
python -m pytest -q tests/test_live_deepseek.py -m live

# 真实 DeepSeek 20 案例逐步测试及落盘报告
python examples/pr02_live_eval.py --model deepseek-flash --max-cases 5
python examples/pr02_live_eval.py --model deepseek-flash --max-cases 20
python examples/pr02_live_eval.py --model deepseek-v4-pro --max-cases 20 --report artifacts/pr02_live/pro_results.json
```

首批 20 案例包括：一次多字段提取、零值、估计值、外径上限、未知电机套圈转速、轴径/内径澄清、未知优化槽、估计球径不可锁定、厘米换算、Z 范围、功耗优化偏好、后续修改转速、约束替换/撤销、插入概念解释、阶段进度查看、任意顺序输入以及寿命硬约束。评测只自动判断结构化事实，**问句自然度、专业适用性和重复追问需人工审查**。未达到目标时报告失败案例，不得宣称成功。

## 四、调用预算、成本与模型适配说明

- 业务工具调用默认每用户回合最多 6 次，另由 LangGraph recursion_limit 限制模型/工具往复；不会自动重试可能已生效的写入。
- 默认 `DEEPSEEK_THINKING=disabled`。DeepSeek 思考模式的 Tool Calling 要求在模型请求之间完整回传 `reasoning_content`，而此适配器尚未完成真实联调；若设置 enabled 会明确拒绝，而非悄悄忽略或造成 HTTP 400。后续可作为兼容性专门任务。
- 默认没有专业知识工具③、推荐工具④、完整性/用户整份确认工具⑤；不能宣称用户层需求已通过正式交付或 RoBAS 模板可运行。
- API key 和生产数据库不上传 GitHub。真实测试必须由拥有密钥的环境执行，**没有凭据时只报告离线结果，不能冒称已完成真实 DeepSeek 连接**。

## 五、验收门禁

1. PR-01 的基础回归全通过；新脚本模型调用通过真实 LangGraph 路径，测试中所有数据库事实须与最终 SQLite 一致。
2. 用户原话数字/单位/上下限验证仍由 PR-01 受信写入负责；工具错误后禁止自然语言虚假成功表述。
3. 多轮会话、同 session 独立回合与重试 ID 的基本一致性测试。
4. 真正的 DeepSeek API：单轮工具、模型→工具→模型、多轮修订、未知值、查看草案与打断场景留有真实测试记录和错误原因；这是**合并前必须完成的单独验收**。
5. GitHub 自动化 CI 只跑不收费离线测试与代码规范，不能作为真实 API 通过证据。

## 六、2026-11-23 实测回归：修复模型未保存却声称“已记录”

- **症状**：真实 DeepSeek 回复“已记录 GCr15 / 已记录脂润滑”，但 `tools=0`、SQLite revision 不变；下一轮又可能把自己过去的回复写进“已确认”总结。
- **实现**：`reply_guard.py` 仅判断是否出现新写入声明；`conversation.py` 在本轮**没有成功写入且未发生写入校验失败**时，给予原来的单一 Agent **恰好一次**重新判断机会，复用本轮可信 `user_message`、`session_id` 和两个原工具，不创建新的用户会话记录，也不扩大工具预算。
- **防线**：无论模型是否再次声称成功，最后的保存结果都用 `update_design_brief` 的实际 `applied_changes` 和最新 SQLite `get_design_status` 重新构造；只允许报告实际已成功写入的字段。对用户要求总结/查看进度的输入，直接按照数据库已确认、近似/待确认、缺项生成汇总，排除没有真实保存的历史语言承诺。
- **防止过度处理**：询问概念时不需要工具或纠正；查看此前状态不触发纠正；一个纠正尝试后仍没写入要说“尚未保存”，禁止无限纠正；工具拒绝写入时不盲目重试。模型正常提出的下一步问题在不包含未经核实成功声明时保留。
- **测试**：增添遗漏调用→成功纠正、遗漏两次→明确未保存、纠正写入失败、只写入脂润滑却声称同时保存 GCr15、历史假确认污染总结、近似温度分组、只解释概念不调用工具、当轮“目前选脂润滑”不误作状态请求等脚本模型用例。
- **范围**：这次只修假保存与假确认。未处理外径“以内”、未明确旋转套圈、模糊“固定吧”、中文“摄氏度”等其他实测问题；它们需要单独的回归修复。
- **验证口径**：CI 跑不收费的脚本模型 + PR-01 回归；真实 DeepSeek 是否在第一次漏调用后自主执行纠正仍需要本地 API 复测，不能以 Mock 成功宣称真实效果已证明。

## 七、针对真实 API 案例再次修复：状态误判与失败后成功（覆盖第六节旧版回复策略）

实际复现：
1. 用户要求“根据目前工况分析保持架；不要把建议当作已确认”，旧 `reply_guard` 因“目前/已确认”等字面词强制覆盖成状态清单。
2. 用户输入“油润滑”，第一次写入枚举失败，Agent 第二次合法提交 `oil` 并成功写入 revision=5；旧实现仍因检测到“曾失败”显示未通过。

改造后：
- **不再根据用户关键词推断意图，也不再把整个正常解释换成状态总结**。专业解释/动态提问由单一 Agent 自主完成。模型可在最终文本中单独输出 `[[DESIGN_STATUS]]` 来显式请求后端渲染 DB 真实汇总，或者用户在 CLI 使用 `/status`、`/brief`；这不是新增的第三个工具。
- **工具回执按字段、按调用顺序对账**：每次写入在 trace 中保留 `attempted_paths`、`applied_changes`、`rejected_changes`，不记录候选值；先失败后成功的同一字段视为已解决，只有最后仍未解决的字段才提示失败。批量原子拒绝后只修好部分字段，其他字段仍显示未保存。
- **自然语言与写入事实分离**：用户可看到后端独立生成的“本轮实际已写入”回执；模型的普通解释和追问保留。不依赖模型自述判断是否写入成功。若本轮仍有未解决写入错误，安全起见只显示可信字段结果，避免模型在文本中继续宣称虚假修改。保留一个**极窄的“新写入声明”文本兜底检测**用于一次自动纠正和裁掉未经核实的保存承诺；它不再承担用户意图路由，也不能被描述成严格的语义校验器。
- **限制及后续**：自然语言是否对已保存字段进行了完全正确的复述，仍不能由关键词安全地证明。正式状态证据应以程序回执、`[[DESIGN_STATUS]]` 渲染的清单和 `/status` 为准。若未来要求对所有模型句子提供数学意义的状态一致性保证，应引入单独的结构化最终回复契约；本 PR 不额外新增强制 JSON 输出或第三个 Agent。
- **回归**：真实 API 场景的脚本模型重放包含保持架分析、第一次 `油润滑` 枚举错误→第二次 `oil` 成功、混合多字段原子失败后部分纠正、先成功后再次试图错误替换、正常解释不应丢失、显式状态标记，以及原有 SQLite/PR-01 回归。CI 不代替真正的 DeepSeek 真实 API 测试；本次变更仍需用户在同一交互场景下实测。

本 PR 保持 Draft；未合并，不进入下一 PR。
