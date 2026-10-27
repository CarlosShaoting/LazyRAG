# 生图 V2：全局模型适配、交互补全与交付体验修复说明

> 文档状态：PR #9 review 修复版
>
> 目标仓库/分支：`CarlosShaoting/LazyRAG:workflow_dev`
>
> 对比基线：`5b586402a21a638b29f37bec21ed5b0f0491466d`
>
> 关联历史 PR：`CarlosShaoting/LazyRAG#7`
>
> 审查日期：2026-10-27

## 1. 一分钟结论

本次是在 PR #7 引入的 `image-workflow-v2` 基础上做闭环修复，不新增业务入口，也不改变三条既有路线：普通生图、图片局部编辑、表情包制作。

改动集中在四个目标：

1. 普通生图和局部编辑不再写死 Seedream/火山 Key，统一使用 LazyMind 已配置的全局媒体模型；
2. 将方案、角色、图片制作阶段的人工确认真正接入执行链路，支持用户提出修改后定向重跑；
3. 静态和动态表情包按单张产物逐步发布，并校验计划数量，避免“首张成功即整批完成”；
4. 重整 WorkflowPanel：去除重复预览，保留历史节点内容，增加清晰的最终产物区、单项下载与整包下载。

用户只需在 LazyMind 中配置模型，不需要为工作流额外配置环境变量。对话模型也不限定为 Doubao；工作流会沿用当前会话选择的可用模型身份，并由服务端从模型配置中解析凭据。

## 2. 问题背景

PR #7 之后的实际运行暴露出以下问题：

- 普通生图和局部编辑固定调用 Seedream 5.0，并要求工作流读取 `ARK_API_KEY`；
- 后续“继续”或审批消息可能覆盖最初的用户需求；
- 人工确认节点存在于 UI/声明中，但没有完整控制实际执行与修改重跑；
- 表情包批次可能只处理部分状态，或等全部结束后才一次性显示；
- 动态分支未指定数量时只计划 3 张，且单批上限与产品预期不一致；
- 角色页重复展示嘴眼锚定图，图片制作页依赖横向滚动，最终结果区会遮挡部分产物；
- 工作流完成后切回前序节点仍显示最终产物；
- 面向用户暴露了 `failure_units`、整包审查提示和“展示源码”等内部信息；
- 上传图在 binding、`/static-files/` URL 与宿主机路径之间存在解析边界；
- 当前会话模型身份未稳定传入工作流，可能回退到不可用默认模型。

## 3. 执行链路修复

### 3.1 全局媒体模型适配

`workflows/image-workflow-v2/scripts/media.py` 通过请求作用域解析媒体角色：

| 场景 | 使用角色 |
| --- | --- |
| 无参考图的普通生图 | `image_generator` |
| 带参考图的普通生图 | `image_editor` |
| 图片局部编辑 | `image_editor` |
| 表情包图片/视频 | 既有全局图片与视频角色 |

工作流不再指定 Provider、模型名或读取工作流专属 API Key。缺少所需角色时返回明确的 `MEDIA_CAPABILITY_DEPENDENCY_MISSING`，不会静默跨 Provider 回退，也不会生成占位结果。

### 3.2 当前会话模型身份透传

启动 Workflow 时只保存当前会话模型的非敏感身份（`source`、`model` 等）；实际执行时由 Core 按任务所有者重新读取模型配置和凭据。密钥不会写入任务参数或 artifact。

同 Provider 约束避免把一个 Provider 的凭据误用于另一个 Provider。`thinking_depth` 与原有 `enable_tool_retrieval` 继续向子步骤透传。

### 3.3 图片输入与比例边界

- 优先解析带类型的 Workflow 图片/视频 binding，再进入通用宿主机路径解析；
- `/static-files/` URL 映射回共享上传目录中的权威文件；
- 局部编辑验证最终解析和暂存后的源图；
- 图片探测采用有上限的增量读取，兼容较大的 EXIF/ICC 元数据；
- 未指定比例时保留源图真实比例及 EXIF orientation；
- 后续输入中的数值比例或“竖版/横版/方图”等自然语言比例优先于启动请求。

自然语言映射为：竖版/portrait → `9:16`，横版/landscape → `16:9`，方图/square → `1:1`。

### 3.4 请求合并与失败重试

- 首次启动请求作为基础需求；
- “继续、确认、下一步、重试”等控制消息不覆盖原需求；
- 用户的真实修改意见作为 update 合并，并覆盖冲突的旧要求；
- 模型或媒体服务的短暂失败按受控策略重试，不把部分成功误报为任务完成。

## 4. 人机确认与定向重跑

三条路线统一使用原有四阶段交互：

1. **方案**：确认路由、数量、文案与风格；
2. **角色**：确认标准角色、身份提示词和嘴眼锚定网格；
3. **图片制作**：确认普通图/编辑候选图，或表情包批量产物；
4. **最终结果**：只读交付与下载。

本次将确认点落实到工作流运行时：

- `rerun_when` 被编译、投影并用于审批后的重跑决策；
- 到达声明的审批边界时 Host 停止自动推进；
- 每个 step 只执行模型明确选择的当前目标；动态模式把结果交回当前 ChatAgent，自动模式沿用 DriverAgent 审核后再触发 ChatAgent，不再由图片 Workflow 的 Host 循环连续推进多个 step；
- 用户后续消息由 ChatAgent 结合完整语义和当前 Workflow 投影判断。“同意继续”可推进当前边界，“不要继续”、疑问、附条件同意或夹带修改要求不会因包含“继续”而被自动批准；
- 用户提出修改时，按该阶段声明重新执行受影响步骤；
- “此步骤不需审批”和“以后此工作流无需审批”仍按现有偏好机制生效。

这样既保留原设计中的用户控制，也不会要求模型自行猜测是否需要停下。

## 5. 静态与动态表情包完整性

### 5.1 逐项发布

静态渲染、静态字幕、动态关键帧、视频和 GIF 都改为每完成一项就保存一项。WorkflowPanel 因此能够逐张出现产物，用户不必等整批结束后才看到结果。

### 5.2 数量与完成条件

- 静态分支单批上限保持 12 张；
- 动态分支单批上限调整为 6 张；
- 动态任务未指定数量时由方案阶段提出数量并交由用户审批，不把示例中的 3 张当作硬编码完成条件；
- 终止判断同时校验计划数量和输出基数；
- 单项成功只是中间进度，不能满足整包完成条件；
- 允许声明可选输出，但不会把缺失的必需产物视为成功。

## 6. WorkflowPanel 与最终交付

### 6.1 角色页和图片制作页

- 角色页只保留标准角色、身份提示词和一张 2×2 嘴眼锚定网格；
- 隐藏旧快照中的逐张锚定图列表，避免重复展示；
- 图片制作页使用只读网格按顺序展示逐项产物，不出现添加控件和横向滚动条；
- 产物到达一张就新增一张卡片。

### 6.2 最终结果页

- 明确显示任务类型、产物数量和完成总结；
- 以网格展示全部最终产物，区域可滚动，不遮挡第 5、6 张；
- 每项支持单独下载；
- 多项产物支持一键打包 ZIP 下载；
- 完成后切回方案、角色、图片制作页时仍显示各自节点内容；
- 仅对 `image-workflow-v2` 隐藏“展示源码”，其他工作流保持原行为；
- 不展示 `pack_review`、`failure_units` 和“整包检查发现需调整项”等内部审查信息。

## 7. 评审入口

| 模块 | 主要文件 | 评审重点 |
| --- | --- | --- |
| 工作流执行 | `algorithm/lazymind/chat/workflow/workflow_manager.py`、`runner.py` | 审批边界、请求合并、逐项完成条件、模型身份 |
| Workflow SDK | `algorithm/lazymind/workflow_sdk/client.py`、`workflow_toolkit.py` | artifact 增量写入与并发版本 |
| Core 工作流 | `backend/core/workflow/...`、`backend/core/subagent/...` | `rerun_when`、审批推进、非敏感模型身份 |
| V2 契约 | `workflows/image-workflow-v2/workflow.yaml`、`scenario/state.yml` | 节点依赖、审批声明、静态/动态数量 |
| 媒体与工具 | `workflows/image-workflow-v2/scripts/media.py`、`tools.py` | 全局角色、比例、逐项发布、基数校验 |
| 最终交付 UI | `WorkflowPanel/ImageWorkflowDelivery.tsx`、`index.tsx`、`WorkflowPanel.scss` | 节点隔离、网格、下载、隐藏内部信息 |
| 回归测试 | `tests/algorithm/...`、`backend/core/..._test.go`、`WorkflowPanel/*test.tsx` | 三条路线和关键边界 |

本地部署专用的 Compose 文件、端口配置、个人路径以及 `backend/core/realtime` 实验均未纳入差异。

## 8. 现有评审意见说明

### 8.1 “可选 output artifact key 是否合法”

这些 key 只是步骤允许发布的输出声明。对四个批量 V2 步骤，运行器不会因为写入第一项就停止；完成条件还会按计划校验输出基数。因此“可选声明”不会把一张产物当作整包完成，也不会绕过必需产物校验。

### 8.2 “host file resolution 是否影响 chat 主页面渲染”

该改动仅发生在后端把 Workflow binding/静态 URL 解析为可读本地文件的阶段，不改变聊天消息结构、前端路由或主页面渲染协议。WorkflowPanel 的展示变化在独立组件中按 `workflow_id === image-workflow-v2` 限定，并有前端回归测试覆盖。

### 8.3 “review 一下 static file URL 处理逻辑”

绝对 `http://` / `https://` 地址只有在 URL path 以 `/static-files/` 开头时才会转入本地上传目录解析；这里不发起网络请求，也不信任 URL host。这样浏览器侧的 `http://localhost:<port>/static-files/...` 签名地址可以在容器内复用共享文件，而不会错误访问容器自身的 localhost。

解析仍统一经过 `_resolve_upload_relative_path`：先 URL decode 并规范化分隔符，再拒绝空段、`.`、`..`，最后用 `candidate.relative_to(root)` 保证结果位于上传根目录。回归测试覆盖 localhost 绝对 URL、明文 `..`、百分号编码 `..` 和反斜杠穿越；其他外部 URL 不会被当成本地文件。

### 8.4 “review image_request.py 的影响范围”

该帮助文件没有接入通用 Chat 消息渲染或普通对话 prompt。当前调用点仅位于 `workflows/image-workflow-v2/scripts/tools.py` 和 `media.py`，用于区分不可变启动需求、纯控制消息和后续真实修改意见。

函数无存储和网络副作用：只有与完整正则匹配的“继续/确认/重试”等短消息会被视为控制消息，其他输入按 update 合并；相关分类、比例覆盖和审批继续场景由 V2 工具测试覆盖。因此影响范围限定在生图 V2 的需求解释。

### 8.5 “推理强度为什么在这个 PR 实现”

这是执行稳定性修复，而不是新增模型策略。WorkflowManager 已从当前会话配置构造 WorkflowClient；如果不透传 `thinking_depth`，工作流子步骤可能回到 SDK 默认值，与发起任务的会话设置不一致。该差异会直接影响 `classify_request`、方案生成和审查步骤的表现。

字段是可选且有白名单的：仅 `low`、`medium`、`high`、`max` 被发送；调用方未设置时不改变原 payload。它不选择 Provider、模型或凭据。独立 SDK 测试覆盖未设置、关闭工具检索及不同推理强度组合。如维护者希望进一步拆分，该改动可单独摘出，但保留在本 PR 能保证修复后的工作流沿用发起会话的完整执行配置。

### 8.6 2026-10-27 review 阻塞项修复

开发侧复现了三个新增边界，本次已按最小范围修复并加入回归：

- 删除图片 Workflow 的审批文本白名单、正则匹配和 Host 侧 `approved` 自动改写。审批与修改意图由 ChatAgent 按完整消息语义判断，原话不被 Host 截断或归类；
- 删除图片 Workflow 连跑多个 step 的 Host 专用循环。一次工具调用只执行模型明确选择的 step，结果中的成功、失败、取消、中断和审批边界均原样返回给 ChatAgent；自动模式继续使用通用 DriverAgent 对每个终态 step 做质量审核；
- `render_static`、`render_keyframes`、`render_dynamic`、`caption_dynamic`、`caption_static` 的专用提示，以及渐进步骤移除 `save_artifacts` 终止条件的行为，统一限定到规范化后的 `image-workflow-v2`；其他工作流的同名步骤保持自身声明；
- 渐进步骤的通用保存说明与专用逐项保存契约保持一致，不再同时要求“一项一存”和“合并一次保存”；
- 绝对 `/static-files/` URL 只允许 localhost/loopback、`host.docker.internal` 或 `LAZYMIND_PUBLIC_URL` / `LAZYMIND_SERVER_URL` 配置的 origin 映射成本地上传文件；其他站点继续作为远程 URL 处理。

## 9. 兼容性与风险边界

- 无数据库迁移；
- 无公开 API schema 变化，OpenAPI 生成客户端保持最新；
- 无新增前端、Go 或 Python 运行时依赖；
- 不删除旧 `image-workflow`；
- 不修改用户已有模型配置；
- 不把模型密钥写入 Workflow task 参数；
- 不改变其他工作流的“展示源码”和 artifact 展示；
- 不跨 Provider 静默复用凭据；
- Provider 仍可按自身约束规范化尺寸，极端比例无法满足时明确失败。

共享改动主要是审批运行时、Workflow SDK 增量 artifact 写入以及宿主机文件解析；三者均有独立回归测试。

## 10. 本地验证结果

| 检查项 | 结果 |
| --- | --- |
| 图片工作流、文件解析、Workflow SDK、路由与运行器 Python 测试 | `319 passed, 18 subtests passed` |
| Python flake8 | `algorithm`、`backend`、`evo` 通过 |
| 文档检查 | `2 passed` |
| 仓库策略 | workflow naming、migration immutability、test locations 通过 |
| Go 定向包 | `workflow/graphengine`、`workflow`、`subagent` 全部通过（Linux + CGO） |
| 前端类型检查 | `pnpm typecheck` 通过 |
| WorkflowPanel | `19 files, 165 tests passed` |
| OpenAPI | auth、core、scan、channel-gateway 均为最新 |
| 前端 ESLint | 通过 |
| 前端生产构建 | 通过，仅有仓库既有的 Sass、动态导入和包体提示 |
| Git 差异 | `git diff --check` 通过，无冲突标记 |

`backend/core` 全仓测试也在 Linux + CGO 下执行。本次涉及的全部包通过；全仓仍报告 4 组与本 PR 差异无关的基线/容器问题（错误目录登记、Windows checkout 的 CRLF golden fixture、容器 `file://` Git 限制、既有迁移断言），相关失败文件相对 `carlos/workflow_dev` 没有任何改动。本 PR 不扩大范围去修改这些无关模块。

## 11. 实际运行验证

8093 本地部署已验证：

- 普通生图使用全局 `image_generator`，无需工作流专属 Key；
- 局部编辑使用全局 `image_editor`，并能保留源图比例；
- 静态表情包经过人工确认节点后完成批量生成和最终交付；
- 动态表情包完成图片、视频/GIF 链路；
- 用户审批“继续”可以推进，修改意见会触发相应阶段重跑；
- 最终结果有总结、完整网格、单项下载和整包下载。

本地验证使用的具体 Provider/模型只是环境配置，工作流代码没有绑定这些名称。

## 12. 合并前检查清单

1. PR base 保持 `CarlosShaoting/LazyRAG:workflow_dev`，head 保持现有 PR #9 分支；
2. 搜索确认 V2 工作流没有 `Seedream 5.0`、`seedream-5`、`ARK_API_KEY` 等硬编码；
3. 确认普通生图/局部编辑只依赖对应全局媒体角色；
4. 确认任务参数仅保留非敏感模型身份；
5. 确认三个业务分支均在声明的阶段等待审批，并支持修改重跑；
6. 确认静态与动态批次按计划数量完成，动态单批不超过 6；
7. 确认最终交付只显示用户产物，不显示内部审查字段；
8. 确认 CI 以 `workflow_dev` 为基线执行。

完成上述检查后，建议继续更新现有 PR #9，而不是删除后新建；它本来就是 PR #7 的后续优化分支。
