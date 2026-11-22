# PR-00 实际验证与限制

日期：2026-11-20；Windows；`C:/Python314/python.exe`，Python3.14.0、pytest8.4.2。项目目标Python3.11+；本次未另运行3.11版本。

业务基线02861ea09e77906f4360ed1e3e9c7268a0c9ea1f；Bearing_CAD对照4460a784846d7df978579f49e8685a18da336e81。原始审计 JSON 曾记录两者，现已从本项目删除；本表只保留历史运行记录，不代表本分支可以直接重跑原采集器。

|实际命令 / 环境|结果|证明范围|
|---|---|---|
|目标仓库 `python docs/pr00/tools/collect_pr00.py`|成功：43记录、324字段、7个SQLite实读schema、101个C#文件哈希|只读盘点；无EXE/工程验证|
|目标仓库 `python -m pytest docs/pr00/tests -q -p no:cacheprovider`（临时目录在D:/引导设计轴承框架/audit_work）|初次10 passed；增加链接与gate检查后最终结果追加于下方|字段唯一性/计数/五槽、属性断链、CSV映射、SQLite模型结构、矩阵完整性；本地原资源哈希未变；C#每列serialize位置；真实留存案例324值回读与CRLF roundtrip|
|Bearing_CAD目录 `python -m pytest tests_v2/test_robas_ball_input.py -q -p no:cacheprovider --basetemp D:/引导设计轴承框架/audit_work/pytest_ball_final`|23 passed in 0.22s，无skip|已有球轴承映射与本地案例测试；未执行真实求解器|
|Bearing_CAD目录同时收集 test_robas_ball_input.py / test_robas_analysis_api.py|收集失败：ModuleNotFoundError: cadquery|完整API联测BLOCKED；未安装/修改范围外依赖|
|在目标仓库用绝对路径调用外部球轴承测试的中间尝试|收集失败：ModuleNotFoundError: bearing_cad|已改为Bearing_CAD目录重跑，上行23通过；未把失败当通过|
|原版UI @oai/sky 只读|已观察工况/润滑/外圈材料/solver页面|不是同次UI生成DATA闭环，不证明构建等同源码|
|真实EXE求解、外部计算性能、模型/工程验收|未运行|不得宣称收敛、性能达标或工程审核通过|

审计脚本对getter/setter与构造器做静态文本提取，不编译C#；source_references含词法候选。非优化字段BLOCKED并不代表无法找到代码，表示单位/工程适用性/确认尚有缺口。原版参考值一律不提升为用户确认。

自审修正：初次collector未处理rec3.1同一行的string.Format，断言失败后修正并成功重跑；一次复制命令使用错误cwd，未写入文件，已改正目标绝对路径；git diff --check发现矩阵EOF空行，已去除并修正collector输出。以上均未触及原版文件。未隐藏失败或虚构测试。

当时没有完整 Agent/输入构建测试。为保持新仓库专注，PR-00 的一次性审计脚本、JSON 和对应 pytest 文件已清理；下面通过数字是**历史运行结果**，不是当前分支可重跑的测试。全套 API 测试仍 BLOCKED。

最终重跑：PR-00审计pytest **12 passed in 0.09s**；git diff --check通过（无输出）。原版资源/源码哈希检查通过。

补查更正：最初误将RoBAS.Utility.MathMethod温标转换记为缺失；本地源码实际存在，现已修正B08并新增静态回归检查；增加C#格式化参数展开后与Python全部324列顺序比较。补查CSharpLib.FileOperation.cs:172的CSV读取链并纳入哈希；原12项测试记录对应此前工件，更新工件测试另记。

温标/CSV补查后的独立验证：14 passed in 0.10s；git diff --check通过。14项包含全部324列C#参数顺序逐项对照、±273.15转换与润滑+273差异；没有重新运行EXE或完整API。
