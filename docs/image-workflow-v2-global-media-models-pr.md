# 生图 V2：全局媒体模型适配与稳定性修复说明

> 文档状态：PR 提交前合并审查版
>
> 目标仓库：`CarlosShaoting/LazyRAG`
>
> 目标分支：`workflow_dev`
>
> 对比基线：`5b586402a21a638b29f37bec21ed5b0f0491466d`
>
> 关联历史 PR：`CarlosShaoting/LazyRAG#7`
>
> 审查日期：2026-10-20

## 1. 一分钟结论

这是一组针对现有 `image-workflow-v2` 的修复，不新增第四条业务分支，也不改变用户的工作流入口。

本 PR 主要解决两类问题：

1. 修复工作流在图片绑定、静态表情包批量处理、产物发布和子步骤推理配置上的不稳定行为；
2. 移除普通生图和图片局部编辑对 Seedream 5.0、火山方舟 Key 及工作流级环境变量的硬编码，改为复用 LazyMind 已配置的全局媒体模型。

合并后，用户只需在 LazyMind 模型设置中配置 `image_generator` / `image_editor`；工作流不再自行指定 Provider、模型名称或读取 `ARK_API_KEY`。表情包、普通生图和局部编辑三条分支因此遵循同一套全局模型配置原则。

## 2. 问题背景

历史 PR #7 引入了生图 V2 工作流，但普通生图和局部编辑通过工作流包内的 `baoyu.py` 固定调用 Seedream 5.0。实际使用中存在两个直接后果：

- 用户即使已经在 LazyMind 中配置了可用的图片模型，仍可能被要求额外设置火山方舟环境变量；
- 工作流不能随全局媒体模型切换 Provider，与表情包分支及 LazyMind 的统一模型配置方式不一致。

此外，实际任务运行还暴露出一组会造成“进度停滞、部分结果被当成完成、源图解析失败或后续步骤拿不到产物”的稳定性边界：

- 上传图片在 Workflow binding、`/static-files/` URL 和宿主机路径之间解析不一致；
- JPEG 元数据较大时，固定读取前 8 KiB 可能误判有效图片；
- 静态表情包的渲染和字幕步骤可能在只处理第一项后提前结束；
- 模型可直接写入部分关键 artifact slot，导致状态与真实媒体产物不完全一致；
- 子工作流没有继承当前对话的推理深度；
- 局部编辑默认输出为固定方图，不能可靠保留源图比例；
- 用户在后续补充的比例要求，尤其“竖版、横版、方图”等自然语言比例，可能未覆盖初始要求。

## 3. 改动一：稳定生图 V2 的执行链路

### 3.1 统一图片输入解析

- 优先解析带类型的 Workflow 图片/视频 binding，再进入通用宿主机路径解析；
- 对绝对 `/static-files/` URL，优先映射回共享上传目录中的真实本地文件；
- 局部编辑在调用模型前验证“最终解析并暂存的源图”，而不是只验证外层传输引用；
- 图片探测改为在限定上限内增量读取，避免因为 JPEG 的 EXIF/ICC 等元数据较大而把有效图片判为无效。

这部分改动保证上传图从首页进入工作流后，普通参考生图、局部编辑和表情包分支看到的是同一份可读取源文件。

### 3.2 关键状态改为确定性发布

工作流路由、普通生图准备结果和局部编辑契约由工作流包内的 publisher 工具原子发布；模型不再直接写这些受保护的 artifact slot。

这样可以保证：

- 路由结果与 `state.yml` / `workflow.yaml` 声明一致；
- 局部编辑的 `requested_edit`、`edit_scope`、`preserve` 和 `do_not` 同步提交；
- publisher 失败时不会留下“部分成功”的工作流状态；
- 后续节点读取到的是完整、结构化且经过验证的输入。

### 3.3 防止静态表情包批次提前结束

对 `render_static` 和 `caption_static` 增加批次完成约束：

- 渲染步骤必须按顺序尝试 `static_plan` 中的全部状态；
- 字幕步骤必须按顺序处理全部无字幕图片；
- 单张图片成功只代表中间结果，不能提前结束当前步骤；
- 所有条目处理完后才能一次性保存最终列表 artifact。

这直接修复了多状态表情包可能只产出一张、或第一张完成后工作流就进入下一步的问题。

### 3.4 继承工作流推理配置

`WorkflowClient` 现在将当前对话的有效 `thinking_depth` 传递给子步骤，同时保留原有 `enable_tool_retrieval` 行为。该变更只增加可选字段，不改变现有调用方的默认行为。

### 3.5 区分启动需求和继续指令

新增统一的图片请求合并逻辑：

- 首次启动指令作为不可变的基础需求；
- “继续、确认、下一步、重试”等控制消息不会覆盖原始图片需求；
- 用户后续输入的真实需求变更会作为 update 合并，并覆盖冲突的初始要求。

这避免了后续工作流步骤把“继续”误当成新的生图提示词，同时允许用户在运行中追加或修改比例等要求。

## 4. 改动二：普通生图和局部编辑改用全局媒体模型

### 4.1 Provider 中立的媒体适配层

工作流脚本从 `scripts/baoyu.py` 重命名并重构为 `scripts/media.py`：

- 删除固定 Provider 和固定 Seedream 模型名称；
- 删除对工作流级 `ARK_API_KEY` 的读取和校验；
- 文本生图调用请求作用域中的 `image_generator`；
- 带参考图的普通生图和局部编辑调用请求作用域中的 `image_editor`；
- 继续复用 LazyMind 现有的模型角色解析、图片落盘、来源登记和签名 URL 逻辑。

具体由哪个供应商和模型执行，完全取决于用户在 LazyMind 中的全局模型配置，而不是工作流代码。

### 4.2 缺少模型时显式失败

工作流在媒体预检和实际调用阶段检查所需角色。如果用户没有配置对应模型，会返回清晰的 `MEDIA_CAPABILITY_DEPENDENCY_MISSING`，引导用户回到 LazyMind 模型设置，而不是提示配置某个 Provider 的环境变量，也不会静默切换模型或生成占位结果。

### 4.3 三条分支的最终模型行为

| 分支 | 使用的全局角色 | 说明 |
| --- | --- | --- |
| 普通文本生图 | `image_generator` | 没有参考图时生成新图片 |
| 带参考图的普通生图 | `image_editor` | 将参考图作为输入，不绑定具体 Provider |
| 图片局部编辑 | `image_editor` | 只对解析后的权威源图生成新图片，不覆盖原文件 |
| 静态/动态表情包 | 原有全局媒体角色 | 保留现有图片、视频、字幕和 FFmpeg 工具链 |

## 5. 局部编辑的比例规则

局部编辑采用以下优先级：

1. 用户后续更新中明确提出的比例；
2. 启动请求中明确提出的比例；
3. 没有明确要求时，保留权威源图的实际比例。

支持显式数值比例 `1:1`、`16:9`、`9:16`、`4:3`、`3:4`、`3:2`、`2:3` 和 `21:9`，同时识别以下自然语言：

- 竖版、竖向、纵向、portrait、vertical → `9:16`；
- 横版、横向、宽屏、landscape、widescreen → `16:9`；
- 方图、正方形、square → `1:1`。

保留源图比例时会读取真实像素尺寸和 EXIF orientation，在媒体模型允许的边长范围内计算 Provider 中立的输出尺寸。若用户明确指定比例，则明确要求始终优先。

## 6. 主要文件及评审入口

本 PR 的代码和测试差异共 22 个文件，另包含本文档。建议按以下顺序评审：

| 模块 | 主要文件 | 评审重点 |
| --- | --- | --- |
| 媒体模型适配 | `workflows/image-workflow-v2/scripts/media.py` | 全局角色调用、失败语义、比例处理、可信产物发布 |
| 工作流契约 | `workflows/image-workflow-v2/workflow.yaml`、`scenario/state.yml`、`scenario/scenario.md` | publisher-owned slots、步骤依赖与用户可见说明 |
| 工作流工具 | `workflows/image-workflow-v2/scripts/tools.py` | 确定性路由、编辑契约、媒体预检及 artifact 读写 |
| 请求合并 | `algorithm/lazymind/chat/workflow/image_request.py` | 启动需求、控制消息和后续更新的优先级 |
| 文件解析 | `host_file_resolution.py`、`static_file_url.py`、`image_generation_support.py` | binding、本地源图和大元数据图片的兼容性 |
| 子步骤执行 | `runner.py`、`workflow_manager.py`、`workflow_sdk/client.py` | 全批次约束和推理深度透传 |
| 回归测试 | `tests/algorithm/...` | 全局媒体角色、失败无残留、比例、输入解析和工作流契约 |

## 7. 合并前后的行为对比

| 场景 | 合并前 | 合并后 |
| --- | --- | --- |
| 普通生图 | 固定 Seedream 5.0 | 使用全局 `image_generator` |
| 带参考图生图 | 固定 Provider 适配层 | 使用全局 `image_editor` |
| 局部编辑 | 固定 Seedream 5.0，依赖火山 Key | 使用全局 `image_editor` |
| 模型凭据 | 可能要求额外设置环境变量 | 只使用 LazyMind 模型配置 |
| 缺少媒体模型 | Provider/Key 相关错误 | 明确提示缺少全局媒体角色 |
| 默认编辑比例 | 容易退化为 1:1 | 保留源图比例和 EXIF 方向 |
| 后续自然语言比例 | 可能不生效 | 最新明确要求优先 |
| 多状态静态表情包 | 可能部分完成即结束 | 全部状态处理后统一发布 |
| 产物发布失败 | 可能留下部分状态 | publisher 原子发布，不伪造成功 |

## 8. 兼容性与风险边界

- 不包含数据库迁移；
- 不改变公开 API schema；
- 不修改前端业务组件；
- 不替换或删除原有 `image-workflow`；
- 不修改用户已经保存的全局模型配置；
- 不引入新的 Provider SDK、前端依赖或 Python 依赖；
- 缺少必需模型时保持失败，不做跨 Provider 静默回退；
- Provider 仍可按自身约束规范化尺寸，因此 prompt 与尺寸提示同时保留比例意图；
- 极端长宽比的源图若无法落入当前媒体模型的安全边长范围，会明确失败，而不是强制拉伸。

需要重点关注的共享改动是文件解析和 Workflow SDK 的可选推理字段。两者均有独立回归测试，默认调用行为保持兼容。

## 9. 本地 CI 结果

以下检查均针对最终 PR 分支执行并通过：

| 检查项 | 结果 |
| --- | --- |
| 图片工作流、文件解析、静态 URL 和 Workflow SDK Python 测试 | `202 passed, 18 subtests passed` |
| full-trust / approval-policy 测试 | `13 passed` |
| 文档检查 | `2 passed` |
| Python flake8 | `algorithm`、`backend`、`evo` 及变更工作流脚本全部通过 |
| 仓库策略检查 | workflow naming、migration immutability、test locations 全部通过 |
| Go | `go test ./workflow/graphengine` 通过 |
| OpenAPI | auth、core、scan、channel-gateway 客户端均为最新 |
| 前端类型检查 | `pnpm typecheck` 通过 |
| WorkflowPanel | `18 files, 156 tests passed` |
| 前端生产构建 | `pnpm build` 通过，仅包含既有 Sass、动态导入和包体提示 |
| Git 差异检查 | `git diff --check` 通过，无冲突标记 |

本地环境版本：Python 3.11.17、Go 1.26.5、Node 22.23.1、pnpm 11.25.0。

## 10. 实际运行验证

在 8093 部署上完成过以下真实链路验证：

- 普通生图通过全局 `image_generator` 完成，不需要工作流专属 API Key；
- 局部编辑通过全局 `image_editor` 完成；当时全局配置的模型为 `doubao-seedream-4-0-250828`，但工作流代码没有绑定该模型；
- 3:4 竖图源文件的比例预检得到 `888x1184`，不再固定输出为 `1024x1024`。

这些结果用于确认全局模型路由和源图比例路径可用；本地 CI 负责覆盖失败路径、批量状态、请求更新和文件解析等可重复回归场景。

## 11. 不在本 PR 范围内

- 新增或修改模型供应商配置页面；
- 为用户自动创建 API Key 或环境变量；
- 修改前端 WorkflowPanel 展示样式；
- 改造视频生成 Provider；
- 对所有第三方图片模型做真实在线矩阵测试；
- 修改历史 PR #7 的说明文档。

## 12. 建议的合并检查

1. 确认 PR base 为 `CarlosShaoting/LazyRAG:workflow_dev`；
2. 确认 `baoyu.py` 到 `media.py` 被识别为重命名/重构，而不是保留两套 Provider 路径；
3. 确认搜索不到 `Seedream 5.0`、`seedream-5`、`ARK_API_KEY` 等 V2 工作流硬编码；
4. 确认普通生图和局部编辑分别只依赖所需的全局模型角色；
5. 确认关键 artifact 只能由声明的 publisher 写入；
6. 确认 CI 仍以 `workflow_dev` 为比较基线执行 migration 和差异检查。

综合上述代码审查、专项回归和实际运行结果，本 PR 已具备提交合并评审的条件。
