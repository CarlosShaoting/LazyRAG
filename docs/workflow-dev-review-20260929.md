# workflow_dev 逻辑与功能冲突 Review（2026-09-29）

## 审查结论和范围

**本文不对问题分级。R1–R7 全部必须修复并逐项验证，重复功能、兼容性和逻辑衔接事项也必须逐项处理并说明结果；完成全部处理和端测验收后，才能合入 main。** 确认了 7 个行为问题，结论只依据控制流、数据流、已有功能对照和具体行为复现；CI、lint、类型检查及旧测试维护问题不列为 findings。并未发现“把所有已有功能整包重新覆盖”的证据，但存在功能重叠、产品工作流执行语义替换及新的共享层耦合，不能把整个分支都算作新增能力。

| 项目 | 核验值 |
|---|---|
| 拉取前本地分支 | `workflow_dev@cebaa36ac` |
| 已拉取 origin | `5b586402a21a638b29f37bec21ed5b0f0491466d`，PR #8 合并提交 |
| 审查主仓库 | `LazyAGI/LazyMind upstream/main@d8eb8f1a9d72fa8a7b5d92094eca81e12f4ce541` |
| 共同基线 | `5c8df649106b30c7a65b0be7d4b4f4d8e9659c72` |
| PR 增量 | 83 文件，32 新增、51 修改，+15,243 / -1,179；[完整文件清单](reviews/workflow-dev-20260929/file-inventory.md) |
| 分支独有提交 | 10 个，包括产品 #8、PPT #5、图片 V2 及文档/测试 |
| main 独有提交 | `e21907e04` 安装包优化 #769、`d8eb8f1a9` SubAgent 完成契约 #750 |
| 合并检查 | 无文本冲突；已核对临时合并中 #750 的产物类型/完成判断与本分支产品策略同时保留 |

采用 `upstream/main...workflow_dev` 审查分支真正引入的变更，再单独检查 main 的新增提交。不能用两端文件差异，把尚未合并的 #769/#750 误报成同事删除了主仓库代码。main 的 LazyLLM 指针已更新到 `ab67c189`，分支仍是 `cf4892ee`；合并时应保留 main 的更新。

本地已有子模块状态、未跟踪文档和 node_modules 保留，未 reset/stash/覆盖。审查没有修改业务代码、提交或推送，也没有创建主仓库 PR。

## 可执行 Review findings

### R1：上传源图编辑缺少 authoritative_image 产出，下一步无法运行

位置：[图片状态机 98–113](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/workflows/image-workflow-v2/scenario/state.yml#L98)，`scripts/tools.py:578`。

上传分支明确要求模型只保存 `edit_contract`，禁止复制源图，并称运行时会自动填充 `authoritative_image`。但 V2 的 `validate_image_ref` 只是调用 V1 的只读验证器，后者不理解“自动发布”也不保存产物；仓库中没有相应复制实现。`edit_prepare` 又把该图片声明为 required，`generate_edit_candidate` 要求恰好一个该产物。因此遵守提示词执行就会缺必需产出。另一个问题是提示词让验证器接收字符串 `source_image`，而被复用的验证器期望实际 URL/路径。

修复：增加读取当前 attempt 精确输入绑定的发布函数，将源图和 contract 一起发布；或明确实现可靠的输入别名解析与复制。不要通过去掉 required 或允许模型猜路径掩盖问题。自动化应使用真实 SubAgent context 验证输入绑定到发布的全链路。

### R2：产品“面向读者”转换会破坏正式正文、代码、URL 和证据事实

位置：[writer_bridge.py 805–840](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/workflows/product_solution_delivery/scripts/writer_bridge.py#L805)。

`_present_reader_facing_markdown` 对整个 Markdown 做正则替换，不区分界面标签与用户业务内容。复现中 `{"status":"accepted","value":null}` 变成 `{"status":"已确认","value":尚未建立}`，URL `/accepted` 也被改写。更严重的是“当前运行已核验 WEB-001，结论有公开资料支持”被直接替换成“本轮未使用外部资料”。此函数用于正文组装、定向修订和章节发布，修改的是保存下来的正文，不只是 UI 标签。

修复：只翻译明确的结构化内部字段；正文保留代码块、行内代码、链接目标、业务枚举和证据结论。用 Markdown AST 处理确需展示调整的节点，不能从出现某个来源编号就推导“没有外部证据”。加入生成和修订路径的保真回归。

### R3：继续、切换甚至结束阶段会自动接受尚未确认的高风险决定

位置：[product_relay.go:701](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/backend/core/workflow/store/product_relay.go#L701)、[product_decisions.go:158](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/backend/core/workflow/store/product_decisions.go#L158)。

`RelayProductStage` 无论 action 是否为 finish、是否勾选接受产物，都先调用 `productAutoAcceptDecisions`。后者把未暂缓的 proposed 决定全部改为 accepted，actor 是 `product-workflow-default`，随后才调用 hard-stop 检查。不可逆/跨租户决定因此同样被自动放行。静态调用链显示 finish 同样经过此函数；Go 探针直接调用实际自动接受函数，证实待确认项从 1 清到 0。该探针没有运行完整 HTTP relay 链路。前端没有展示这些决定供逐项处置，而 Python 契约仍称高风险决定必须明确确认、不能作为已确认基线。记录一个系统来源并不能补足用户没有做过的决定。

修复：阶段导航与决定接受分开；高风险项要求指定 decision_id、内容 hash 和实际确认动作。finish 不应批准任何决定；允许草稿继续时保留 proposed/deferred。恢复可操作的确认/暂缓 UI 或等价明确对话工具，并测刷新、重复命令、决定变更后的重新确认。

### R4：图片普通生成路线忽略显式搜索/知识库素材需求

位置：[tools.py:258](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/workflows/image-workflow-v2/scripts/tools.py#L258)、状态机 `ordinary_prepare`。

分类函数能返回 `needs_external_material=true`，但普通准备步骤唯一工具只把输入拼成 prompt，固定写入“不需要外部事实”，没有读取这个路由标记、调用搜索或发布 `material_images`。用户要求“搜索真实照片作为参考”的请求会直接进入无参考生成。原 `image-workflow` 已有 `collect_materials` 和图片校验，V2 在这条路线遗漏了已有能力。

修复：按实际材料需求接通已有搜索/KB 与校验函数；失败时说明无法取得素材，并让用户决定是否接受无参考生成。测试不能只断言 prompt 保留了“搜索”两个字。

### R5：将当前步骤输入当成不可变启动输入，继续后会丢失原始比例/要求

位置：[baoyu.py:230](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/workflows/image-workflow-v2/scripts/baoyu.py#L230)、[baoyu.py:307](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/workflows/image-workflow-v2/scripts/baoyu.py#L307)，`tools.py:259/473`。

这些函数把 `ctx.params.user_input` 称为 immutable launch request。实际上 `workflow_manager._step_request_input` 对图片工作流会转发当前消息；Core 仅在该值为空时恢复 `session.IntentContext`。在需要用户继续的手动执行/失败恢复等情况下，“继续”可以成为下一步的这个字段。用已保存的 16:9 prompt 加当前输入“继续”调用真实生成函数，传给供应商适配器的比例是默认 1:1；准备阶段同样可能把继续文字当生图主题。

修复：显式冻结启动请求及其解析参数，当前修改要求单独绑定；不要仅因为函数命名 immutable 就认为数据不可变。覆盖“继续/continue”、失败后继续、用户真实修改比例和字幕等不同语义。

### R6：自制 Mermaid 渲染器删除了分支条件，HTML 与 Markdown 不再同义

位置：[writer_bridge.py:513](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/workflows/product_solution_delivery/scripts/writer_bridge.py#L513)。

解析流程图时用 `re.sub(r'\|[^|]*\|', '', line)` 删除 edge label，边结构只保留起点终点。实际输出 SVG 中“已付款→是→发货／否→取消”的“是／否”全部消失。PRD 和交付文档的审批、权限、异常规则依赖这些条件；源码放在折叠区不等于默认图已表达同一规则。

修复：复用完整 Mermaid 渲染能力，或用保留边标签/方向/条件的解析器；不支持的语法显示明确的源码/文本降级，不生成貌似正确但语义缺失的图。加入条件、循环、子图和多图共存测试。

### R7：宽/长源图被独立裁剪宽高，局部编辑静默改变画幅

位置：[baoyu.py:118](https://github.com/CarlosShaoting/LazyRAG/blob/5b586402a21a638b29f37bec21ed5b0f0491466d/workflows/image-workflow-v2/scripts/baoyu.py#L118)。

先按目标像素数放大，再对宽、高分别 clamp 到 512–4096。4000×500 的 8:1 图会变成 4096×728（约 5.63:1），这不只是 8 像素取整误差，违背编辑函数“不指定比例则保留源比例”的契约。竖长图有对称问题。

修复：宽高按同一缩放系数求解，再校验供应商的比例/总像素约束；不能同时满足时明确拒绝或让用户选画幅，禁止悄悄压缩原画幅。自动化无需调用真实供应商即可验证计算。

## 功能是否以前已经有，以及是否覆盖/重复

以下按主仓库代码和提交历史核对，不能把同事 PR 的功能列表直接当“全新实现”。

| 功能 | main 已有实现 | 本分支实际改变 | Review 判断 |
|---|---|---|---|
| PPT 大纲、可编辑 HTML、页面重试、KB、导出 | #754 `fae93aa0b` 及更早版本 | 在原工具内扩展 | 已有基础能力，不能重新计为新增；本次继续使用原有工具链 |
| PPT 三套风格 | runtime 原有 `cmd_style_samples` / `cmd_style(sample_id)` | 新增 `style_flow`，将三选一和 AI 底图开关解耦，接通 UI/状态机 | 属于流程接通和隔离修复，不是首次发明三套风格 |
| PPT 并发模型 | 原来全局 set/reset LLM/VLM | 改成阶段和并发子任务显式传 callable | 有效增量；保留页面复用/发布路径，需双会话真机验收 |
| PPT 精确改字/样式 | main 已有 preview/apply 及单目标操作 | 多目标原子编辑、旧稿视觉锚点、代理语义 | 扩展已有编辑，不是第二套编辑系统 |
| 产物历史、回滚、图片预览 | 共享 `SlotComponents` 已有 | 图片/HTML 幻灯片改双栏历史布局；新增紧凑显示 | 展示替换，影响所有使用这些组件的工作流，需要普通文件/文本回归 |
| 工作流 Tab 跟随 | main 已有自动聚焦和持久化焦点 | 明确 following/free、按 Tab ID 稳定定位、条件步骤恢复 | 有效 UI 增量；并非首次实现工作流面板 |
| 图片生成/编辑/静动态表情包 | 原 `image-workflow` 已有，#724/#713/#703 等持续维护 | 新增独立 `image-workflow-v2`，20 步分支、角色/嘴眼锚点、视频样片、字幕校验 | **两套入口并存，功能高度重叠**；必须声明推荐入口和迁移策略 |
| 图片搜索、校验、字幕/GIF | 原包已有 `image_search_and_validate`、`validate_image_ref`、字幕函数 | V2 动态加载 V1 源文件复用 | 不是复制一份实现，但形成跨包运行依赖；V2 普通路线还漏掉素材收集（R4） |
| 图片模型适配 | main 通用 `AutoModel(role)` | 增加 `run_image_model_instance`，V2 普通/编辑固定 Doubao Seedream | 不是泛化升级；已有其他供应商配置不等价于 V2 可运行，需要清晰配置引导 |
| 产品七阶段与 Writer | #640 `0445895a4`、#738 `0e7b4fc0f` 已有阶段、Writer、大纲/章节、编辑发布 | 新增两层路由、一 Session 一阶段、跨阶段 relay、返回阶段定向修订 | 业务流程实质重写；七种产物不是首次加入 |
| 产品 Workspace/Manifest/决定概念 | 原 workflow 已嵌入相关 Skill 业务契约，已有基础材料加载 | 新增真正的 Host 发布事件、共享输入、接受/暂缓 API | 持久化接通是新增；不能把原业务契约算新设计；自动接受与契约矛盾（R3） |
| 产品双格式 | 原文档/章节主要是 Writer Markdown，竞品/原型是 HTML | 七阶段配对 HTML+Markdown，增加默认成果视图 | 有效增量，但全局改写及有损 Mermaid 会破坏一致性（R2/R6） |
| 文件冻结、版本、CAS、幂等 | #772 `5f76eaab3` 的通用 workflow store、artifactfile、controlstore 等已存在 | 产品复用基础模块，另加 publication 和 attempt 输出选择策略 | 没有新建第二套文档数据库；但业务专用逻辑进入多个共享层，要测试旧 revision、取消和失败 |
| 工作区 | 已有 conversation workspace 与 task workspace | 产品 task 目录投影到 conversation 下的散列子目录 | 属于已有机制的路径策略扩展；应验证多项目、重试和旧执行恢复 |
| 通用执行轮数/工具限额 | 共享 AgentExecutor/runner 已有 | 为产品 publisher-owned 契约增加限额/超时策略 | 有 workflow ID 和契约门控；普通工作流保留原分支，产品实际超时/取消仍需验收 |
| 主仓库最新完成契约 | #750 已在 main | 分支尚未包含，文本自动合并可保留 | **同步时不可用分支旧 runner 整文件覆盖 main**；保留 main 的完成判断和分支的产品执行策略 |

重复/覆盖必须处理的事项：

- 不要再次提交 #754/#738/#772 的整包旧实现；当前 review 应继续以共同基线增量检查。
- 图片 V1/V2 可以暂时兼容并存，但需要确定默认推荐与旧会话保留方式。V2 的动态加载应移到共享模块或固定其依赖；当前“不可变包”测试仍在源码仓库中运行，没有证明单独分发 V2 时 V1 必然可用。
- 产品“发布组”对业务确有意义；避免在通用 runner/store 中不断增加 workflow ID 特判。优先复用现有冻结、命令账本和图失效机制，并用适配器约束边界。
- 双格式显示不应另建有损正文/图表转换规则。优先共用已有 Markdown/图表呈现链路，保持正文唯一来源。

## 与 upstream main 的逻辑衔接及证据边界

- **SubAgent 完成判断：** main 的 #750 改必需产物解析、产物类型验证和最终完成判定；本分支改产品专用工具集、轮数和工具失败处理。合并结果可同时保留这两部分，没有发现二者在同一判断处相互替代。产品输出必须继续遵守 main 的真实产物校验，不能以总结文字替代文件。分支单独运行时尚不包含 #750，不能直接用旧 `runner.py` 覆盖 main。
- **产品发布与共享产物存储：** 产品输出先保存为未选中草稿，再按发布组统一切换；其他工作流仍走原来的逐产物选择和下游失效链路。这是针对产品的语义扩展，不是第二套文档数据库。复核点是新修订失败时仍保留旧发布组，以及成功发布后只让对应消费者失效；不能把这两条路径混用。未观察到仅因该分支就必然发生覆盖的代码证据。
- **产品提示词与 Host 行为：** 已确认的冲突是“高风险必须显式确认”与 Host 默认自动接受相矛盾（R3），以及“正文保真/双格式同义”与正文替换、删图表条件相矛盾（R2/R6）。这些是执行逻辑问题。
- **图片状态机与工具能力：** 已确认上传源图输出契约和工具实际保存行为不一致（R1）；素材需求识别和普通生成准备不衔接（R4）；当前消息被当作冻结请求（R5）；保留源比例与尺寸计算不一致（R7）。V1 与 V2 的功能重叠另见上表。
- **PPT 和共享 UI：** 本次改动主要接通已有风格能力、拆开底图开关、扩展多目标编辑，以及调整面板跟随和历史显示。未找到可确定复现、足以列为 finding 的新增逻辑冲突；不能由此认定真机交互已验收。共享面板仍需覆盖 Writer、旧 PPT 和普通工作流，具体操作见文末测试部分。

7 个问题的局部行为证据：[Python 复现代码](reviews/workflow-dev-20260929/reproduce_python.py)、[输出记录](reviews/workflow-dev-20260929/reproductions-python.log)，以及 [Go 决定复现代码](reviews/workflow-dev-20260929/reproduce_product_test.go)、[输出记录](reviews/workflow-dev-20260929/reproductions-go.log)。其中模型和外部 I/O 被替代；R1/R3/R5 结合调用链与局部函数复现判断，尚未跑完整 UI 链路。

本次没有调用真实模型、生成付费媒体或操作真实用户项目。已有 CI、构建及测试统计不作为本 Review 结论，也不把陈旧测试断言本身当成业务缺陷。没有改动用户已有子模块内容。

## 交给同事：复制该分支到自己的 fork，并直接向 LazyMind 主仓库提 PR

目标工作方式可行：**同事持有自己的修复分支，后续直接往自己的分支 push，同一个 LazyMind 主仓库 PR 自动更新。** 不需要每次先让 CarlosShaoting 合并，再转提主仓库。

先在 GitHub 将 `LazyAGI/LazyMind` fork 到同事自己的账号，保持 fork 关系；仅新建一个无关联空仓库可能无法直接发起跨仓库 PR。以下 `<同事账号>` / `<fork仓库名>` 由同事替换，建议使用独立 clone，避免碰现有工作目录。

```bash
git clone https://github.com/<同事账号>/<fork仓库名>.git LazyMind-workflow-fix
cd LazyMind-workflow-fix
git remote add upstream https://github.com/LazyAGI/LazyMind.git
git remote add review-source https://github.com/CarlosShaoting/LazyRAG.git
git fetch upstream main
git fetch review-source workflow_dev

# 指定本次被审查的提交，保留原作者和全部历史。
git switch -c codex/workflow-review-fixes 5b586402a21a638b29f37bec21ed5b0f0491466d
git merge upstream/main
git submodule update --init --recursive

# 在这里修复 R1–R7，补充对应逻辑复现，更新实际操作验收记录，再提交。
# 只 git add 本次负责的文件，避免夹带本地配置、数据或 node_modules。
git push -u origin codex/workflow-review-fixes

# 使用 GitHub CLI，或在网页选相同的 base/head。
gh pr create --repo LazyAGI/LazyMind \
  --base main --head <同事账号>:codex/workflow-review-fixes \
  --draft --title "fix(workflow): integrate and validate product, PPT and image workflows" \
  --body-file docs/reviews/workflow-dev-20260929/pr-description-template.md
```

PR 描述必须写清：base=`LazyAGI/LazyMind:main`，head=同事 fork 的 `codex/workflow-review-fixes`；原始来源为本次 workflow_dev SHA；保留原提交作者；对 R1–R7 逐项附修复与实际行为验证结果；列出尚未端测项。上例 `docs/reviews/workflow-dev-20260929/pr-description-template.md` 已附交接模板，应由提交者根据最终修复结果填写，不能直接把本 Review 的“失败”改写成“已通过”。

后续更新同一 PR：

```bash
git add <修复文件和测试>
git commit -m "fix(workflow): address review findings"
git push
```

需要更易合并时，可由提交者把 PPT、图片、产品拆成三个 PR，但要基于最新 main **只选择各自尚未合入的增量提交**；三个 PR 都从同一个聚合分支直接开，会各自重复携带全部功能。产品修复者若只负责 PR #8，应与另外两组作者协调，不能把整个 workflow_dev 的缺陷都标为产品实现引入。

本文及证据当前仅保存在本地，尚未推送到源分支。交接时需要把 review 文档和 `reviews/workflow-dev-20260929` 一并提交或提供给对方；这里没有替对方创建 fork/分支/PR，也没有发送消息。

## 测试：测什么、怎么测

**交付给修复者的要求：先按下列操作复现业务问题，修复后验证实际行为，再补真实模型端到端验收。所有问题处理并完成验收前，不得合入主仓库。** 本文审查对象是整个 `workflow_dev` 相对主仓库的增量，包含 PPT、图片 V2、产品方案，不仅是刚合并的产品 PR #8。

### 测试准备与结果记录

1. 在自己的 LazyMind fork 创建修复分支，完整接入本文末尾指定的 `workflow_dev` 提交，再合并最新 `upstream/main`。不要复制整个目录覆盖 main，也不要重复 cherry-pick 已在 main 的历史 PR。
2. 使用干净 checkout、项目要求的 Python/Go/Node 环境，执行 `git submodule update --init --recursive` 和前端依赖安装。先安装工作流新 revision，再新建会话；旧会话要单独验证，不能用旧 revision 验收新代码。
3. 准备一个普通生图模型、图片编辑模型；V2 普通生图/编辑目前硬编码 Seedream，还需要其 `ARK_API_KEY`。动态表情包另需视频模型和 FFmpeg。缺少依赖时验收的是明确失败/配置引导，不能算生成成功。
4. 每条端测记录：父仓库/子模块 SHA、工作流 revision、平台、模型与供应商名称、会话/attempt 标识、输入、预期、实际、关键截图/产物。不要提交 API Key。失败重试、刷新和跨会话场景都保留前后 revision 证据。

### A. 先验证这 7 个逻辑问题

复现文件位于 [review 证据目录](reviews/workflow-dev-20260929/)。这些小脚本用于复现下述具体行为，不以 CI、构建或测试通过率判断是否可合并。调用真实生产函数，模型/外部 I/O 在需要处被替代，**不等同于真实模型端测**。

```bash
# 仓库根目录；使用已安装项目 algorithm 依赖和 pytest 的 Python 环境。
PYTHONPATH=algorithm:algorithm/lazyllm python -m pytest -q \
  docs/reviews/workflow-dev-20260929/reproduce_python.py

# 同时运行 Python 及 Go 回归探针；自动生成临时 Go overlay，不改生产包。
python docs/reviews/workflow-dev-20260929/run_regressions.py
```

| 用例 | 怎样复现 | 修复后的验收标准 | 当前结果 |
|---|---|---|---|
| R1 上传源图编辑 | 上传 PNG，要求只改帽子颜色；按 `edit_prepare` 提示词只保存 `edit_contract` | 自动发布实际源图对应的 `authoritative_image`，两个 required 输出齐全，下一步能执行 | 缺少 `authoritative_image` |
| R2 产品正文保真 | 研发交付文档包含 JSON `null`、业务状态 `accepted`、带 `/accepted` 的 URL，以及“当前运行已核验 WEB-001” | 代码、URL、原始业务状态及证据结论不被展示层翻译/反转 | JSON 损坏、链接改变、已核验变成未使用资料 |
| R3 高风险决定 | 构造 proposed 的跨租户/不可逆决定，执行“结束本轮” | 结束、修订、切换不隐式接受该决定；显式接受才改变基线 | 自动记录为 accepted，hard stop 从 1 变成 0 |
| R4 真实参考素材 | 输入“搜索上海外滩真实照片作为参考，制作16:9旅游海报” | 实际检索、校验并绑定参考图；检索失败应保留明确缺口 | 标记需要外部素材，但不收集任何图片 |
| R5 审批后原始意图 | 已保存 16:9 普通生图 prompt，下一次执行输入为“继续” | 生成仍使用启动请求的 16:9，控制消息不能覆盖业务参数 | 传给生成器的是 1:1 |
| R6 流程图语义 | `A{已付款?} -->\|是\| B[发货]`、`A -->\|否\| C[取消]` | HTML 图保留“是／否”分支条件；与 Markdown 同义 | SVG 两条边都没有条件 |
| R7 宽图局部编辑 | 使用 4000×500 源图，不指定改比例 | 保持 8:1，或在供应商不支持时明确拒绝/要求选择；不能静默变形 | 输出尺寸计算为 4096×728，约 5.63:1 |

### B. 真实模型/UI 验收矩阵（本次尚未执行）

| 范围 | 操作步骤 | 必须检查 |
|---|---|---|
| 产品入口 | 分别直接请求方向、竞品、方案、PRD、原型、评审、交付七阶段；再给多阶段目标 | 进入选定阶段；多阶段只执行本轮授权阶段；缺少上游时明确草稿/缺口 |
| 产品两层路由 | 方案分别输入简单 UI 调整、跨租户权限变更；给 light 偏好但包含强风险约束 | 第二层按实际决定选择 light/heavy；不能用轻量偏好消除风险项 |
| 产品材料复用 | 上传材料→方向→竞品→方案→PRD，同一会话衔接 | 不重复上传、不换项目；材料、版本、来源可追溯；补充要求传到下一阶段 |
| 产品定向修订 | 完成 PRD 后只改某条业务规则；另一次明确要求改大纲 | 默认保留无关正文；结构修改走对应路径；旧版仍可查 |
| 产品双格式 | 七阶段各查看 HTML 与 Markdown；对表格、条件图、状态值、URL、代码逐项比对 | 同版同义；真实图片可显示；下载后可读；不能因润色改业务规则 |
| 产品草稿/发布 | 已有完整交付后编辑正文；在新输出一半时取消/模拟失败，再重试发布 | 旧完整交付仍可读；新草稿可见；不出现半套发布；成功后才更新下游版本 |
| 产品决定 | 加入高风险决定；分别点击继续、修订、切换、结束，再显式确认/暂缓 | 操作语义准确；未确认决定不变 accepted；暂缓不等于批准；刷新后持久化 |
| 产品并发/幂等 | 双窗口同项目操作；重复同一幂等键、不同请求体同键、旧 state_version、网络超时后重试 | 恰好一个后继 Session；旧版本拒绝；同键不同请求拒绝；不重复接受/创建 |
| 产品权限 | A 创建项目；B 调用 summary、artifact、relay、decision 接口 | B 不读到 A 的内容/路径，不修改决定；错误可理解 |
| PPT 四组合 | auto/preview_choice × AI 底图开/关，每种生成 4 页 | 三选一不依赖底图；大纲前唯一风格；不显示跳过步骤空页 |
| PPT 并发 | 两个会话同时生成，模型/主题不同；取消或重试其中一个 | 模型 callable、页文件、进度互不串；另一会话不被清空模型适配器 |
| PPT 精确编辑 | 单选、Shift 多选、同组编辑、弹窗内调整选择；测试父子目标及重叠删除 | 修改范围准确；一次提交原子生效；不破坏未选元素/背景 |
| PPT 旧稿/外部稿 | 无 data-el 的旧页面、整页栅格背景加前景代理 | DOM 路径正确定位；显现被改代理；删前景不删底图 |
| PPT 风格及恢复 | 选 B 后继续；完成后补素材/开启底图；失败页重试 | 保留选定风格；条件步骤恢复；有效页面复用；页序不变 |
| PPT 跟随/版本 | 手动切 Tab、恢复跟随、刷新、失败/审批等待、条件 Tab 增减；回滚旧版 | 当前步骤和正在看的页区分清楚；Tab 身份不跳错；回滚不删后来版本 |
| PPT 导出 | 多选编辑后导出 PPTX，逐页对照 HTML，检查文字/图片/备注 | 文件打开正常；编辑结果和页序正确；不存在制作元话语泄漏 |
| 图片普通生成 | 1:1、16:9、9:16；中英文约束；搜索参考、上传参考、缺凭证、继续重试 | 模型/尺寸/参考图与要求一致；失败不给假成功；R4/R5 转绿 |
| 图片局部编辑 | 上传源图与搜索源图两条入口；普通图和宽图；拒绝结果后要求重试 | 不缺 required 输出；新图不覆盖源图；原比例及未编辑部分保留 |
| 表情包静态/动态 | 指定字幕、让系统提议字幕、无字幕、12 张静态、5 张动态、超限 | 互斥路线；字幕逐字且顺序正确；超限有可完成的缩减/分批路径 |
| 动态表情包恢复 | 视频样片拒绝/重试；FFmpeg 缺失；单状态失败；后续改变字幕 | 使用同一角色锚点；已完成项不重复扣费生成；结果 GIF 字幕与批准内容一致 |
| 兼容性 | 在升级前创建旧产品/PPT/图片 Session，升级后继续；另跑 Writer、外部 Agent 工作流 | 固定 revision 可恢复；通用完成契约、工具限额、文件授权不回退 |

以上端测目前都是待验收项；本次没有调用真实模型、生成付费媒体或操作真实用户项目。
