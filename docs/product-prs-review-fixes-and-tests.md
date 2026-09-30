# cst/product_prs：问题、修复记录与测试总表

更新日期：2026-09-30。后续发现的问题和修复继续追加在此文档，保留问题编号、原因、代码修改、验证结果和未完成验收；不按严重程度分级。Review 在前，测试在后。

## Review 范围和当前状态

比较基线为 `upstream/main@9cbc57c5deb3b5fdded71c6b051041c1bff3aa30`；导入来源为 `origin/workflow_dev@5b586402a21a638b29f37bec21ed5b0f0491466d`。历史行为修复在 `4b26e452a`、`b0962fbbc`，本次继续在 `cst/product_prs` 修改。原问题不是单纯重复文件：产品业务实际改变了 manager、runner、图推进、产物事务、公共 Repository 和共享 UI 的控制规则。

R1–R7 的行为修复保留；本次处理 A01–A12 的新增控制层特例，以及错误目录和重构中发现的契约遗漏。代码修改和本地回归不等于真实模型、浏览器或供应商端测完成，未执行的验收列在末尾。

### 必须保留的原有行为

- `MarkdownArtifactEditor.tsx/.scss`、`SlotComponents.tsx`、`WorkflowPanel.scss`、现有 Writer 工作流和 `algorithm/lazymind/document_tools` 与上述 main 基线无差异；没有替换原 Markdown 编辑/保存/冲突恢复逻辑。
- 公共面板只新增可选声明和通用扩展挂载。未声明新能力的包继续使用原工具、任务展示和编辑方式，不因包名被自动套用产品策略。
- `launch_user_input/current_user_input` 仅增加上下文；manager 原样传递本轮 `user_input`。PPT 对“继续”的解释留在 PPT 提示词。
- 图片 V1 供应商路径、搜索校验和字幕仍保留；V2 复用公共实现，KB/Web 的工具错误不直接升级为流程失败。
- 原子产物仍使用既有 `artifactfile`、`artifactgraph`、Attempt 事务和 revision 表；未再建一套产品存储表。鉴权、用户来源、CAS、幂等仍在可信 Host。

## 已有行为问题及修复

### R1：上传图片编辑缺少必需源图产出

已用 `publish_edit_contract` 从当前 attempt 的 `remote_inputs.source_image` 读取实际绑定，校验图片和四项编辑约束后发布 `authoritative_image` 与 `edit_contract`。上传绑定优先于模型传入的 URL；多图、缺图、不完整约束均拒绝执行，不能通过模型猜路径或读取另一次运行的最新产物补齐。

两个必需输出共同约束步骤完成。验证使用真实 SubAgent context 和实际图片文件，检查发布图片字节与上传图一致；不是只检查提示词包含字段名。

### R2：产品正文转换损坏代码、URL 与证据事实

已去掉对整个 Markdown 的状态翻译、`null` 替换和外部证据否认。正文原样交给已有 Writer 发布机制，代码块、业务枚举、链接和来源编号不改写。产品提示词也明确要求保留这些内容，定向修订不能顺带重构未选中正文。

产品仍复用现有 Writer 能力；没有新增第二套共享 Markdown 编辑器，也没有改动 Writer 文档保存契约。

### R3：阶段导航替用户批准决定

已删除自动接受逻辑。结束当前阶段和切换到当前阶段修订不会接受任何决定；带未处理硬阻断项进入其他阶段会被拦截。显式暂缓可作为草稿携带，但决定仍为 proposed，不得作为 accepted 基线。

产品界面展示决定原文、依据和完整结构，提供逐项确认/暂缓。请求绑定用户实际看到的 session state version、decision ID 和 proposal hash；版本变化返回冲突后需重新查看，网络重试复用原命令，不能刷新 hash 后偷偷确认新内容。后端保留 owner 检查和幂等处理。

旧 `product-workflow-default` 自动确认不会被重放成用户确认；读取历史 workspace 或继承 seed 时重新开放待确认项，保留审计历史。真实 SQLite repository 回归验证了 finish 持久化、重复命令、旧 hash/错误 owner 拒绝、刷新恢复及提案变化后重新确认。

### R4：普通图片路线忽略搜索和知识库

普通准备步骤已接通已有图片搜索/校验及 KB 查询。实际检索结果进入参考摘要和生成提示词，通过校验的图片发布为 `material_images`。各来源独立执行，KB 失败或无命中不影响 Web 检索，也不丢弃其他来源的成功结果。工具异常、空结果和成功分别记录在 `retrieval_results` 及材料摘要中，不直接升级为准备步骤或整个流程失败。

例如 KB 服务不可用、Web 找到有效图片时，继续使用 Web 图片，摘要如实标明 KB 未取得资料。即使所有来源都失败，仍保留各工具的失败记录，明确没有取得经过验证的外部参考，不把失败改写成“无需外部资料”，也不伪造知识库事实。产物发布/存储本身的错误仍正常上报，不被检索容错吞掉。用户明确取消参考要求时才跳过检索尝试。

V1 的图片校验、搜索和字幕实现提取到安装包公共模块 `image_workflow_support.py`，V1 通过原函数名转出，V2 复用该模块。这样不需要安装包或不可变工作流包里存在另一个工作流源码目录。V1 通用供应商路线保留；V2 是明确的 Seedream 路线，不替代 V1 的既有供应商能力。

### R5：启动需求与本轮指令混用

启动输入与本轮输入分别传递。图片 V2 的纯“继续/确认/重试”不再替代需求；明确修改可覆盖冲突的启动条件。普通图片比例及表情包数量/字幕读取有效需求，准备阶段保存的比例修订在后续确认时继续有效。编辑约束同时保存当时的用户需求，供下一步精确绑定使用。

修改后仅验证图片 V2 使用新增字段；Writer/PPT 等既有 `user_input` 协议不改写。

### R6：Mermaid 分支条件被丢弃

支持的普通流程图保留边标签与回边，独立图使用独立 SVG marker。子图、特殊箭头及 sequence/state 等超出简化渲染器支持的语法，展示明确说明和完整转义源码，不能画出缺失分支的“成功”图。移除了原有几类会丢失结构的替代渲染器。

当前不承诺这些复杂图形都有图形化预览；保证不静默遗漏原文。若必须完整图形化，应另行接入完整 Mermaid 实现并验证。

### R7：独立钳制宽高导致源图变形

改为按同一缩放系数计算宽高，并在供应商尺寸约束和取整后检查比例误差。标准横图、竖图、方图和可表示宽图保持比例；极端比例无法同时满足像素和边长约束时，报错要求用户选择支持的画幅，不静默拉伸或裁剪。

## 公共控制层问题及本次修改

### A01：manager 为 PPT 单独改写“继续”

原 `_ppt_step_user_input` 按 `ppt-workflow` 名称把控制输入清空。已移除 helper 及其普通/hand-off 调用；两种推进原样传递用户文本。PPT `scenario/state.yml` 在各阶段提示中说明从启动上下文和已绑定产物继承原需求，不把“继续”当成新主题。已有附加上下文字段继续复用。

### A02：manager/SDK 持有产品工具和隐式 session 重定向

产品阶段查询、读取和 relay 工具移到 `algorithm/lazymind/chat/host_extensions/product_project.py`，HTTP 客户端移到同目录的 `product_client.py`。公共 manager、SDK 删除产品方法、`product_tools` 开关及 `_relayed_session_id` 字典重定向。

可信扩展由 `runtime.host_extensions` 声明选择，`product-project-v1` 是安装能力名，复制包无需使用特定 workflow ID。ChatService 是扩展组合入口；未知扩展明确报错。扩展注册不是 workflow ID 白名单。

为保留同一轮“切换后继续执行”，公共工具提供显式 `bind_successor` Host 回调：只接受当前 source session、同 conversation、同 workflow 和固定 revision 的服务端结果，再通过 SDK 确认目标 session 可读。成功后，普通推进和 hand-off 工具共用更新后的绑定；这个回调不暴露给模型。产品扩展调用它后要求读取真实 Ready frontier；finish 才返回通用终止控制。没有让公共工具读取产品专用重定向字典。

### A03：输入白名单依赖产品名称

新增 `runtime.trigger_inputs`，编译器验证所有名称都是已声明 external material。触发工具只暴露并接受该列表；未声明沿用既有输入规则，显式空数组表示不允许模型提供任何材料。使用可空列表保留“未声明”和“空列表”的差别。可信 `workspace_seed/stage_approval/upstream_*` 不由模型自由伪造。

### A04：runner 按产品步骤名设置预算、工具和失败策略

删除 `product_policy.py`。轮数、超时和工具调用配额从固定 revision 的 `runtime.execution_limits` 读取，通用实现位于 `workflow/execution_policy.py`。编译器校验步骤存在、轮数 1–64、超时 1–3600 秒、配额 1–100；改工作流 ID 不改变行为。产品每个步骤的预算在包内声明。

删除 runner 的产品 builtin tools 开关、硬编码工具过滤和产品工具失败即终止逻辑；继续使用既有工具声明和普通工具错误处理。工具错误是否可恢复不再由产品工具名表决定。

### A05：远程执行器提前解释业务输入

execution depth、参考样例、字数的别名和业务校验下沉到产品 `scripts/tools.py` 的路线发布工具。远程执行器只传输通用输入，不在调用工作流工具前把产品参数错误直接升级为执行失败。未修改其他工作流的输入解释。

### A06：产品覆盖工作目录和错误协议

移除产品 workspace 子目录覆盖；统一使用 execution spec 的 workspace。HTTP 错误按共同 envelope 解码；仅声明了预算的步骤使用通用超时包装。没有“产品才读错误消息、其他包丢失错误详情”的分支。

### A07：ArtifactSink/Attempt 执行产品发布语义

`productstate` 改为通用 `workflow/publication`，`attempt/product_outputs.go` 改为 `transactional_outputs.go`。是否延迟选择、失败撤回、成功统一选择及使消费者失效，来自 `runtime.transactional_outputs`。`runtime.publication` 明确发布步骤与必需输出；编译器要求这些输出由发布步骤产生。

Core 只核对冻结输入、有效 revision、必需产物及内容摘要并记录 `workflow.published`。产品的阶段、Workspace/Manifest 对应关系、正文/HTML/Markdown 配对、assessment 和描述摘要一致性移到包内 `_validate_product_publication`，在发送任何产物之前校验；没有因移走 Go 产品代码而放弃原校验。

### A08：图求值完成后暗改 workspace_seed witness

移除 transition handler 和远程读取器里的产品步骤/slot 特判。`runtime.published_input_aliases` 声明继承来源，编译器检查来源属于已发布输出、目标为 external input、两端类型相同。读取 runtime snapshot 时先投影别名，再进行图求值与冻结，因此 Ready witness、持久化 binding 和远程读取都指向同一 revision。

Snapshot 输入使用通用读取与内容摘要；JSON 返回 JSON，文本返回文本。发布前及远程读取时检查冻结摘要，发现内容变化会拒绝。已发布版本不被后来的 working selection 替换。

### A09：人工编辑的快照/COW 依赖产品 ID

两个编辑入口改读固定 revision 的 `transactional_outputs` 能力，再复用 `artifactfile.Snapshot` 和已有 COW 路径。普通 Writer 不声明该能力，保持原保存、草稿与冲突恢复逻辑。没有根据 workflow ID 决定文件生命周期。

### A10：公共 Repository 重复实现产品领域模型与默认值

阶段导航、项目聚合、决定及历史移到 `backend/core/product` 独立领域服务；领域 handler 也从 workflow facade 移出，由 routes 注册。公共 Repository 只提供 `AtomicCommand` 事务原语；owner/CAS/幂等及原有 session/input/artifact API 保留。

删除 Go `productStageDefaults` 及自动导入默认资源。原差异为 direction 1400/1800、design 3500/5000、PRD 4500/6000、review 1800/3000、handoff 3500/5000（Python/Go）。现在没有显式偏好时由包内路线验证器决定默认值；Go 只恢复用户已存在的偏好。

七阶段及其文档格式仍是 `product-project-v1` 领域协议的一部分，由业务服务、包和业务组件共同遵守；它不是支持任意阶段的通用引擎。新增领域阶段需要升级该扩展协议，不能向通用 Store/manager 添加分支。

### A11：relay 自动升级包并返回固定 Ready 步骤

创建下一阶段使用 source session 的 `WorkflowRevisionID`。只在摘要中只读查询最新包以提示更新，不在 relay 时切版本。新 session 创建后重新读取实际持久化输入绑定，通过该 revision 的 graph projection 得到 Ready，删除 `route_product_stage` 常量。

服务端返回 source/session/conversation/workflow/revision 身份供显式 Host 绑定校验。测试构造新 head 与旧 pinned revision、改名入口，验证没有隐式升级和错误 Ready，并检查未注入字数默认值。

### A12：共享 UI 依据产品 ID 覆盖包声明

移除 WorkflowPanel、TaskCenter 和 chatLayout 的产品 ID 判断。包内 `ui.task_presentation` 声明任务分组、隐藏步骤与最终文件展示；`ui.group_downloads` 选择通用下载聚合；`ui.extensions` 请求已安装控件。`WorkflowExtensions` 注册业务组件，`WorkflowTaskProgress` 不包含产品步骤名。

原来在面板中删除 `_outline_report` 和重设 layout 的做法，改为产品包自身 slots/tabs 的声明；同时把 PRD/review/handoff 检查报告的 `exposed` 改为 false，确保编译契约一致。产品决定控件内部保留业务 API，下载聚合保留每个原操作的保存/禁用回调。

## 本轮补充发现与修复

### C01：Core error constructors 没有登记

用户提供的 `TestCoreErrorConstructorsAreCatalogued` 日志涉及六种不同产品错误。`common/error_catalog_workflow_publication.go` 登记这些旧业务错误及新的通用发布错误；非法数据映射为 400，冻结/内容变化/发布不完整映射为 409。没有删除测试或给扫描器加忽略规则。该用例单独 `-count=1 -v` 运行通过。

### C02：拆分后不能丢失校验或冻结内容

补充包内完整发布预检；manifest 摘要与绑定正文不一致时零产物发布。补充 ContentSnapshot 的绑定摘要和远程读取/发布时比对，防止移除产品读取分支后丢失冻结约束。

### C03：声明的空值与 UI 可见性不一致

`trigger_inputs: []` 不能被序列化为未声明；改用可空字段，并增加复制包/空白名单测试。隐藏 outline report 时同步修改 slot 的 exposed 标记，实际包编译检查已覆盖。只调整 UI tabs 而不调整公开声明会导致安装失败，现已修正。

### C04：阶段切换不能只创建新 session 后结束

拆分工具时发现，如果 relay 一律作为 stop tool，聊天发出的“继续”会只准备下一阶段而不执行。已改为 A02 的显式绑定回调，普通工具可在同一轮读取新 session；只结束操作停止模型。测试同时拒绝错误来源和意外 revision 升级。

## 边界与兼容说明

main 已有的 `workflow/ppt_incremental_pages.go` 仍按 PPT 身份处理旧页插入；这是基线已有逻辑，本次未新增或扩展。它需要单独设计旧会话迁移才能安全改成声明式能力，不能直接删除后破坏现有 PPT 页面保留行为。本次 A01 处理的是增量新加的 manager 输入改写，不代表整个主仓库已经不存在任何历史特例。

本分支的产品能力尚处于这次 PR 的迭代中。测试新实现应同步新的产品包 revision 并新建会话；不要只替换 Host 二进制后用旧的、没有声明新能力的产品 session 验收。运行中 session 不被自动升级。既有 main Writer/图片/PPT 未声明新能力时按原协议运行。

历史详细探针保留在 [架构 Review](product-prs-architecture-review-20260930.md)，早期行为交接在 [原 Review](product-prs-review-and-tests-20260930.md)。二者是对应提交的历史记录，当前状态以本文为准。以后新增问题继续追加编号和证据，修复后更新同一条记录，不把未测写成通过。

## 同事从已有本地仓库接手

在同事现有仓库中执行，`origin` 应指向他自己的 fork；若目标本地分支已存在，先换一个未使用的分支名，不覆盖未提交修改：

```bash
git fetch https://github.com/CarlosShaoting/LazyRAG.git cst/product_prs
git switch -c cst/product_prs FETCH_HEAD
git push -u origin cst/product_prs
gh pr create --repo LazyAGI/LazyMind --base main --head '他的GitHub用户名:cst/product_prs' --title 'Fix workflow boundaries and preserve Writer behavior' --body-file docs/product-prs-review-fixes-and-tests.md
```

将示例用户名替换为实际 fork owner。后续修复在他自己的同一分支提交、push，即可更新提交到主仓库的 PR；不需要重新 clone，也不从整个 dev 覆盖 main。

## 测试：本次自动化验证

2026-09-30 本地执行，所有下列命令退出码为 0；Go 最终一轮禁用结果缓存。结果没有依赖 GitHub CI 状态。

| 范围 | 结果 |
|---|---|
| `TestCoreErrorConstructorsAreCatalogued` | 单独 `-count=1 -v`：PASS；没有修改该测试 |
| Go `workflow/... product common doc skillv2/...` | 38 个有测试的 package 通过，另有 5 个无测试 package；覆盖真实 SQLite 的发布、产物选择、决定、固定 revision relay |
| Core 顶层编译 | `go test . -run '^$'` 通过，包含领域路由注册 |
| Python 产品/图片/PPT/公共执行器/SDK/Writer | 22 个独立测试进程，623 项通过；另有已有参数化子测试通过 |
| 新声明及显式 session 绑定 | 7 项通过；与 selection/runner 再联合执行为 142 项通过，未重复计入前一行 |
| WorkflowPanel 原有面板/store | 18 文件，147 项通过 |
| Writer、任务中心、taskCenter store | 25 文件，270 项通过 |
| Markdown 编辑器、共享修订弹窗、PPT Slot | 5 文件，107 项通过 |
| 产品决定控件与通用扩展挂载 | 2 文件，6 项通过 |
| 前端生产构建 | Vite build 通过；已有 bundle 大小警告 |
| 实际内置工作流编译 | Go `TestBundledWorkflowsCompileForRuntime` 通过，包括产品、图片 V2、PPT |
| Writer 保真与补丁检查 | 核心 Writer/Markdown 文件对 main 无差异；`git diff --check` 通过 |

新增回归不是仅检索源代码字符串：包含 ArtifactSink 真实写库后不提前选择、Attempt 成功/失败/取消/幂等、发布别名的图 witness、缺产物与 stale 输入拒绝、改名包仍启用声明、旧 head 存在新版本仍固定 revision、默认字数不由 Go 注入、manifest 与正文不一致时零发布、Host session 错误来源/版本拒绝、无声明时不挂载业务 UI。

Python 使用仓库 Python 3.11 环境；测试依赖从本机临时目录补充，业务代码仍来自当前工作树。PPT 老测试清理时有 lazyllm stub 的退出日志，但测试主体 87 项及 10 个子测试通过、进程退出码为 0。Go 存在 macOS Keychain SDK 弃用警告。以上均未当作真实端测成功。

### 可重复执行的命令

在 `backend/core`：

```bash
go test ./common -run '^TestCoreErrorConstructorsAreCatalogued$' -count=1 -v
go test ./workflow/... ./product ./common ./doc ./skillv2/... -count=1
go test . -run '^$'
```

在仓库根目录，使用安装好仓库依赖及 pytest 的 Python。模块替身测试分进程，避免互相污染：

```bash
export PYTHONPATH=algorithm:algorithm/lazyllm
python -m pytest -q tests/algorithm/chat/test_workflow_declared_capabilities.py tests/algorithm/chat/test_workflow_selection.py tests/algorithm/chat/test_subagent_runner.py
python -m pytest -q tests/algorithm/chat/workflows/test_product_solution_delivery.py
python -m pytest -q tests/algorithm/chat/test_product_workflow_delivery_contract.py
python -m pytest -q tests/algorithm/chat/test_workflow_review_regressions.py
python -m pytest -q tests/algorithm/chat/test_remote_executor.py
python -m pytest -q tests/algorithm/test_workflow_sdk.py
python -m pytest -q tests/algorithm/test_workflow_toolkit.py
python -m pytest -q tests/algorithm/chat/test_workflow_full_trust.py
python -m pytest -q tests/algorithm/chat/test_image_workflow_v2_tools.py
python -m pytest -q tests/algorithm/chat/test_image_workflow_v2_baoyu.py
python -m pytest -q tests/algorithm/chat/workflows/test_image_workflow_v2_contract.py
python -m pytest -q tests/algorithm/chat/workflows/test_image_workflow_meme_modes.py
python -m pytest -q tests/algorithm/chat/workflows/test_image_workflow_search_validation.py
python -m pytest -q tests/algorithm/chat/workflows/test_image_workflow_caption_renderer.py
python -m pytest -q tests/algorithm/chat/test_image_workflow_prompt_contract.py
python -m pytest -q workflows/ppt-workflow/scripts/tests
python -m pytest -q workflows/ppt-workflow/runtime/scripts/tests
python -m pytest -q tests/algorithm/chat/test_writer_workflow_runtime.py
python -m pytest -q tests/algorithm/chat/test_writer_plugin_draft_stream.py
python -m pytest -q tests/algorithm/chat/test_writer_stream_recovery.py
python -m pytest -q tests/algorithm/chat/test_writer_source_contract.py
```

在 `frontend`：

```bash
node node_modules/vitest/vitest.mjs run --config vitest.workflow-panel.config.ts --maxWorkers=2 --minWorkers=1
node node_modules/vitest/vitest.mjs run src/modules/chat/components/WorkflowPanel/Writer src/modules/chat/components/WorkflowPanel/writer src/modules/chat/components/WorkflowPanel/SlotWriterDocument.test.tsx src/modules/chat/components/TaskCenter src/modules/chat/store/taskCenter.test.ts --maxWorkers=2 --minWorkers=1
node node_modules/vitest/vitest.mjs run src/modules/chat/components/WorkflowPanel/MarkdownArtifactEditor.test.tsx src/modules/chat/components/WorkflowPanel/MarkdownArtifactEditor.real.test.tsx src/modules/chat/components/WorkflowPanel/MarkdownArtifactEditor.table.test.tsx src/modules/chat/components/WorkflowPanel/ArtifactRewriteDialog.test.tsx src/modules/chat/components/WorkflowPanel/ppt/SlotHtmlSlide.test.ts --maxWorkers=2 --minWorkers=1
node node_modules/vitest/vitest.mjs run src/modules/chat/extensions/WorkflowExtensions.test.tsx src/modules/chat/components/WorkflowPanel/ProductProject.test.tsx --maxWorkers=2 --minWorkers=1
node node_modules/vite/bin/vite.js build
```

## 测试：合入前必须执行的真实服务端测

准备配置好 LLM、Seedream `ARK_API_KEY`、图片搜索及含品牌资料的知识库的开发实例；构建本分支并同步这三个工作流的新 revision。保留一份升级前 Writer 文档/会话用于恢复验证。记录每项 session、revision、操作步骤、前后文件和预期/实际结果。

| 场景 | 操作 | 通过条件 |
|---|---|---|
| Writer 旧文档 | 打开已有文档，切换可视/源码模式，编辑表格、代码块、链接、引用，再保存刷新 | 正文和格式保真；原先的历史版本、焦点、展开与恢复行为一致 |
| Writer 定向修订 | 选中文字修订；模拟网络失败/版本冲突后重试；在弹窗外点击 | 只改所选范围；原关闭规则和冲突提示保留；未保存修改不丢失 |
| Writer 流式生成 | 从原入口新建文档，生成中打开编辑区，结束后保存并重开 | 原来的流式展示、草稿恢复及完成状态一致；没有产品导航工具干扰 |
| 产品正文 | 生成/定向修订含 `accepted`、`null`、URL `/accepted`、WEB 来源和 Mermaid 的正文 | 业务值、URL、证据事实不被展示层改写；定向修改不破坏未选中内容 |
| 产品决定 | 留一个硬阻断提案未处理，尝试进入下一阶段；确认/暂缓后刷新；结束项目 | 未处理时拦截跨阶段；暂缓仍是草稿；finish 不自动批准；刷新保留明确操作 |
| 产品并发 | 两个页面打开同一提案，另一页修改提案后在旧页确认；重复提交同一命令 | 旧版本明确冲突；不自动批准新提案；重复命令不重复接受/创建阶段 |
| 图片上传编辑 | 上传一张带唯一标记的横图，只要求改帽子颜色 | 编辑使用该图；身份/背景/画幅保留；下载源图不被覆盖；缺图/多图明确失败 |
| 搜索与 KB | 分别制造 KB 失败/Web 成功、KB 成功/Web 失败、双方无结果或异常 | 保留并使用成功来源；失败/空结果分别记录，不直接使准备步骤失败；双方失败时明确无有效参考，不虚构来源事实 |
| 图片需求延续 | 初始 16:9，先“继续”；准备时改 9:16 后再“继续”；修改表情包数量及逐字字幕 | 不回到默认方图；已保存修订仍生效；最终数量/字幕与修改一致 |
| 编辑极端比例 | 普通横/竖/方图和 8:1 源图分别局部编辑 | 普通比例不变形；不支持比例明确拒绝；用户指定支持的比例后可运行 |
| Mermaid | 有是/否分支和回边的流程图；另测 subgraph、sequence loop、虚线箭头 | 支持图保留条件；不支持语法完整源码可见，无缺边假图 |
| PPT | 选风格生成，取消/重新选择多元素后局部修订，预览并导出 | 不误关 PPT 选择弹窗；修改范围正确；未选页/元素保留；导出可打开 |
| 固定包与复制包 | 改 workflow ID 后重复输入、阶段切换、发布、编辑、下载；在阶段间发布一个新 head | 行为来自声明；下一阶段仍使用 source revision，Ready 为实际图结果；无重复新 session |
| 发布失败与重试 | 让 finalizer 缺一个双格式文件或让存储中断，再修复重试 | 失败不替换已发布产物；成功一次性切换；旧版本可读且没有重复发布 |
| 旧图片工作流 | 明确选择原 `image-workflow`，用原配置生成并添加字幕 | 原供应商路线和字幕逻辑仍可用，未被 V2 自动替代 |

真实供应商调用、完整浏览器端到端操作和真实导出文件的人工验收尚未执行。上述项目全部完成并记录结果后，再判断是否可合入主仓库。
