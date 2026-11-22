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
$env:DEEPSEEK_API_KEY = Read-Host "请输入 DeepSeek API Key"
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
