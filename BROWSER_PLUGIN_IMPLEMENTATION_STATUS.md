# LazyMind 浏览器插件实施状态

> 更新时间：2026-09-07
> 分支：`cst/browswer_plugin`  
> 当前结论：PRD 没有要求嵌入网页。Docker、Local 和 Desktop 已统一为“Chrome/Edge 扩展打开独立有头窗口”；页面感知和浏览器控制 MVP 已形成完整代码链路，但按 PRD 的严格文字仍不能判定全部验收通过，主要缺口是超长正文完整传输、产品内授权/设备撤销闭环和无登录态边界验收。已有 Electron 内嵌代码保留但默认关闭。

### 2026-09-07 飞书富文本真实 E2E 与 VLM 视觉定位兜底

- Chat 侧在当前请求确实配置了 `vlm` 角色时才新增 `browser_visual_locate`：内部调用 Browser MCP 截图，将图片暂存到共享上传目录，再复用现有 `vision_extractor`/`AutoModel(model='vlm')` 识别目标位置；截图用后删除，主模型上下文只接收结构化坐标，不接收 JPEG Base64。没有 VLM 时不暴露该工具，16 个基础 Browser MCP 工具仍可正常使用。
- VLM 必须返回严格 JSON，坐标按截图实际尺寸校验，再换算成浏览器 CSS 视口坐标；越界、无图、非法 Base64、未知图片格式和目标不可见都会明确失败，不会盲点页面。
- Chrome/Edge 扩展与保留的 Electron 内嵌控制器均新增 `click_at` 和 `type_focused`，Browser MCP 工具从 13 个增加到 15 个。富文本写入可设置 `verify_text`，最多等待 3 秒确认页面确实出现目标文字，未出现时返回 `TYPE_NOT_APPLIED`。
- 飞书 Wiki 的快照若出现精确的“编辑”模式标签，会显式标注当前已经可编辑，避免模型误点该标签并把辅助用 readonly textbox 错判为文档只读。
- 修复 Browser Hub 动作白名单遗漏 `click_at`、`type_focused` 的问题；新增测试保证所有已发布 Browser MCP 动作都能通过 Hub，避免工具已经展示给模型却在运行时返回 `unsupported browser action`。
- 修复飞书正文占位符“结构上可见、点击时报 `ELEMENT_NOT_VISIBLE`”：无障碍树可能把占位符引用到 DOM 文字节点而非 HTMLElement。Chrome/Edge 与 Electron 控制器现在优先使用 CDP `DOM.getContentQuads` 求点击范围，失败时使用文字 `Range`，最后逐级回退到可见父元素。
- 已完成单元测试链路：截图解析、VLM 调用、临时文件清理、截图到视口的坐标缩放、越界拒绝、文字节点点击范围，以及 Chrome/Electron 坐标校验。
- 已在 `make local-up` 的真实 Chrome 152、飞书登录态页面完成端到端写入：`browser_open` → `browser_click` 点击正文占位文字 → `browser_type_focused` 写入并通过 `verify_text` → `browser_wait` 命中“已经保存到云端” → `browser_snapshot` 复核。该流程没有使用 VLM、飞书 API、CloudFileToolkit 或写作工具。
- 上述成功流程已固化到内置 `feishu` Skill。当前 `1.2.1` 版本在 `browser_type_focused` 携带 `verify_text` 且成功返回后立即结束，禁止为了重复证明写入结果继续截图、快照、等待或反复检索 spill；只有用户明确要求确认云端保存时才额外等待一次保存提示。MIT 来源许可证和来源说明继续随 Skill 包分发。
- 新版 Skill 已重新打包、更新锁文件、通过冻结锁校验并安装到当前 Local 用户，状态为 enabled。空白正文写入是已真实验证路径；非空正文的任意位置复杂插入仍需要能唯一定位正文块，否则应使用块 API 或明确插入位置，不能盲目覆盖。
- 新增 `browser.click_intersection`：输入同一快照中的行标签 ref 与列标题 ref，浏览器现场读取两个节点矩形，用“列中心 X + 行中心 Y”点击网格交点。该能力用于空单元格没有 ref 的飞书表格，不依赖 VLM，并返回行列名称、矩形、点击坐标及命中/焦点摘要供输入前核对。
- 已在真实飞书「Lazymind v0.4版本进展」表格完成无写入 E2E：同一 revision 定位 `@ 崔绍庭` 行和 `9/7` 列，计算交点 `(1647.375, 602.25)` 并点击；交点点击前命中元素已是 editable div，点击后焦点从 readonly 辅助 textarea 转到 `contenteditable=true` 的正文 div。测试未调用输入工具，文档内容未改变。

### 2026-09-07 Edge 开发版接入

- Chrome 与 Edge 继续共用同一个 Manifest V3 扩展目录和 16 个 Browser Tool，不维护第二套页面抓取或 CDP 控制代码。
- 扩展新增浏览器身份识别：优先读取 User-Agent Client Hints，兼容 `Edg/` UA 回退；配对时分别上报浏览器名称、浏览器版本和扩展版本，不再把 Edge 错记为 Chrome。
- Browser Gateway 已显式接受并测试 `edge-extension://` WebSocket/CORS Origin，设备列表可以区分 Microsoft Edge 与 Google Chrome。
- 扩展依赖 API 同时返回 `chrome://extensions` 和 `edge://extensions`；设置页可选择 Google Chrome/Microsoft Edge，并复制对应管理地址、查看对应加载和配对说明。
- 本地内置扩展源会与已安装版本比较；设置页现在支持更新或重新安装扩展包，避免旧的 Chrome/Edge 开发版停留在 `0.1.1`。
- 当前扩展版本为 `0.2.4`；Edge 开发人员模式可直接“加载解压缩的扩展”使用同一目录，配对提示包含完整的 LazyMind 设置路径。
- 浏览器快照过滤纯零宽字符节点，并通过 CDP 读取程序化打开页面的 URL/标题；扩展控制台和 Core 日志增加快照节点数、角色分布、响应大小及耗时诊断。
- 尚未完成 Microsoft Edge Add-ons 商店上架、企业策略安装模板和 Edge 真机完整操作 E2E；这些不影响开发版手工加载，但仍属于正式发布验收项。

### 2026-09-07 主分支合并、Local 启动与 PRD 审计

- 已将 `upstream/main@4d71affc` 合并到 `cst/browswer_plugin`，合并提交为 `8fab7e58`。
- 合并处理了 Chat Runtime 配置、Core 工具注入、错误目录和 Chat Layout 4 处冲突；同时保留主分支 SideChat/模型选择改动，以及浏览器 `system_mcp_config` 和默认关闭的 Desktop 内嵌实验代码。
- `algorithm/lazyllm` 已从分支记录的旧指针对齐到主分支的 `a48b3a37`，子模块内部无未提交文件。
- 合并回归已通过：Frontend 3 个文件 20 条用例、Core `chat/common/browser/systemdeps`、local-runtime-manager 全量 Go 用例、Python MCP/Runtime Event 24 条用例。
- 已先停止占用 `8090` 的旧 Docker 栈，再执行 `make local-down` 和 `make local-up`。Local Runtime 当前为 `ready`，入口是 `http://localhost:8090`；认证、Core、Chat、Local Proxy、Frontend 等服务均为 `running`。
- 在线检查通过：登录会话、5 分钟配对码、设备列表、非法配对拒绝，以及扩展依赖检测；Local Runtime 已识别 `LazyMind Browser v0.1.1`。
- 本次 Core 重启后，内存中的已配对设备会丢失。真实 Chrome 再次联调前，需要在设置页重新生成配对码并连接扩展。

#### PRD 逐项结论

| PRD 项 | 结论 | 代码现状与严格验收差距 |
|---|---|---|
| 当前页 URL、标题、正文、图片 alt、链接 | 部分满足 | 字段均已实现；正文最多 200 万字符、图片最多 1000 个、链接最多 2000 个，超限会明确标记但仍不满足“正文全文、无明显截断”的严格表述；跨域 iframe 也只能报告限制。 |
| 对话指令自动抓取当前激活页 | 基本满足 | 普通 Chat 会获得第一方 `browser_capture_current_page` 等工具，扩展执行当前激活页抓取；绑定 Workflow/SubAgent 回合仍按现有隔离规则隐藏 Browser Tool。 |
| 首次明确授权、授权后默认开启 | 基本满足 | 当前站点权限必须在扩展弹窗中由用户点击授予，Chrome 会记住 origin 权限；没有安装时的全站静默读取。 |
| 随时撤销授权 | 部分满足 | 用户可在 Chrome 站点权限中撤销，扩展可“断开并清除凭证”，后端也有设备撤销 API；LazyMind 设置页尚无授权站点列表、设备列表和单设备撤销按钮。 |
| 无登录态或未授权时不抓取 | 部分满足 | 生成配对码和设备管理需要登录，远程命令按用户绑定并在无站点权限时拒绝；但扩展本地“测试抓取”未检查配对/登录状态，且前端退出登录不会主动吊销已配对设备凭证，需要补充产品级注销联动和 E2E。 |
| Chrome 优先、Edge 后续 | Chrome 已提测，Edge 开发版已实现 | 同一 MV3 扩展可在 Chrome/Edge 加载，并能正确识别和上报浏览器；Edge 真机完整 E2E、Edge Add-ons 包和商店审核仍待完成。 |
| 打开 URL、截图、操作页面 | 已实现 MVP | 16 个 Browser MCP Tool 覆盖打开、导航、快照、元素/坐标/行列交点点击、元素/焦点输入、选择、按键、滚动、等待、截图、标签页和关闭；Chat 另提供 VLM 视觉定位工具。`open` 创建最大化的独立有头窗口。当前页只读，控制范围限于扩展自己创建的 managed window。 |
| 录屏转 Skill | 未实现 | 语义事件录制、视频/截图轨迹和 Skill 草稿生成仍属于 P1/P2 待办。 |

综合判断：如果本期验收口径是普通 HTML 页面、正文不超过 200 万字符、Chrome 开发者模式安装、普通 Chat 触发，则核心流程具备提测条件；如果完全按 PRD 的“正文全文”和“无登录态不执行任何抓取”逐字验收，目前应判定为**部分满足，不能关闭 PRD**。

Browser MCP 的 `capture/open` Tool 描述已同步为外部 Chrome/Edge 独立窗口，不再向模型描述默认内嵌页面。

### 2026-08-31 Local 联调修复

- 修复 `make local-up` 下 Browser MCP 无法加载：本地依赖解析到了 `mcp 2.1.1`，但当前 LazyLLM Streamable HTTP 客户端使用 MCP 1.x 的三返回值协议，导致 `ValueError: not enough values to unpack (expected 3, got 2)`。现已在 LazyMind 顶层 `algorithm/requirements.txt` 约束为 `mcp>=1.7.0,<2.0.0`，不修改 `algorithm/lazyllm` 子模块。
- 修复模型供应商 HTTP 429 被泛化的 `invalid_request_error` 覆盖后，前端误显示“模型请求格式错误”的问题。对于 `invalid_request/provider_rejected + HTTP 429`，Chat 运行事件现统一输出 `rate_limited`；额度耗尽等更具体错误不被覆盖。
- 已在当前 Local Runtime 安装 `mcp 1.29.1`、只重启 Chat 子进程并确认 Runtime 为 `ready`，没有重新执行 `make local-up`。
- 当前机器已加载并配对开发版扩展，真实 Chrome 已跑通 `browser_open`、`browser_type` 和 `browser_snapshot`。`make local-up` 只启动 Gateway/MCP，首次换机器时仍需由用户在 Chrome 中确认加载扩展。

### 2026-09-01 Local Agent 注册修复

- 日志确认 Browser MCP 已成功协商协议并加载 13 个工具，但 LazyLLM 会把 `browser.open` 等带点号的 callable 名称解释为 Registry 分组，创建 Agent 时抛出 `KeyError: 'browser'`。
- LazyMind Chat 现把模型可见名称规范化为 `browser_open`、`browser_click` 等 Python/Registry 安全别名；MCP callable 闭包仍保留并调用原始 wire method `browser.open`、`browser.click`，没有修改 `algorithm/lazyllm` 子模块。
- 别名处理覆盖非法字符、数字开头、64 字符上限和规范化后重名；已使用真实 LazyLLM `ToolManager` 验证 `browser_open` 能注册成功。
- 已把 `upstream/main@fba729ee` 合并到 `cst/browswer_plugin`，合并提交为 `a3a75b16`。Desktop 冲突同时保留上游 renderer recovery 和本次 Embedded Browser Controller；合并验证后已执行 `make local-down` 清理端口并重新 `make local-up`，Local Runtime 状态为 `ready`。

### 2026-09-01 完全自动化模式

- 按当前产品决策，Chrome/Edge 扩展允许自动点击发送/提交等按钮、按 Enter、输入敏感字段以及发送原按键白名单之外的按键。默认关闭的 Electron 实验驱动仍保持相同动作策略。
- 原 `HIGH_RISK_NAME`、`SENSITIVE_NAME`、`ALLOWED_KEYS` 和 `HUMAN_TAKEOVER_REQUIRED` 判断没有删除，均以注释形式保留，方便后续恢复审批模式。
- MCP 工具说明和 destructive hint 已同步为全自动模式，避免模型继续根据旧说明要求用户手工发送。
- 设备配对、用户隔离、受控页面范围、`http/https` URL 校验和私网显式允许仍然保留；这些属于连接与作用域边界，不会阻止普通网页内的自动操作。

### 2026-09-01 Desktop 快速开发模式

- 新增 `make desktop-dev`：复用已经运行的 `make local-up`，以 Desktop 模式启动 Vite HMR 和源码 Electron，不构建 ZIP/EXE，也不安装应用。
- React/CSS 修改由 Vite 热更新；`desktop/electron/src/*.js` 修改由开发 runner 自动重启 Electron。
- 新增 `make desktop-dev-down`，只停止 Vite/Electron 开发进程，不停止 Local Runtime。
- 开发 renderer 和外部 Runtime 仅允许 loopback URL；Browser WebSocket 已加入 Vite proxy。

### 2026-09-01 统一外部浏览器形态

- Desktop 与 Docker/Local 统一安装和连接同一个 MV3 扩展；Agent 的 `browser_open` 在三种部署形态下都打开扩展管理的独立有头 Chrome/Edge 窗口。
- Desktop 默认不挂载聊天右侧 `WebContentsView`，Core 也不再优先选择 Electron 设备。已经完成的内嵌驱动和拖拽面板代码没有删除，可用 `VITE_DESKTOP_EMBEDDED_BROWSER=true` 显式挂载实验 UI；多设备在线时可再用 `LAZYMIND_BROWSER_PREFERRED_DEVICE_BROWSER=Electron WebContentsView` 固定实验目标。
- “设置 → 系统工具 → 依赖安装 → 浏览器控制扩展”弹窗新增 5 分钟一次性配对码生成与复制入口，避免再通过 curl 找配对码。

## 1. 这次已经完成

### 1.1 Chrome Manifest V3 扩展

目录：`browser-extension/`

已实现：

- 开发者模式直接加载，无需 Node 构建步骤。
- 扩展弹窗配置 LazyMind 地址、输入配对码、显示连接状态、重新连接和清除凭证。
- 配置非本机 LazyMind 地址时，由用户手势申请该 Gateway 的精确 origin 权限。
- 用户点击后按当前 origin 请求站点读取权限；安装时不申请 `<all_urls>`。
- 抓取当前激活标签页：URL、origin、标题、正文、文章正文、语言、图片 alt/src、链接 text/href。
- 抓取结果带 `untrusted_browser_content`、SHA-256、字符总数、返回字符数和 limitations。
- 当前传输上限为 200 万字符；超过后明确返回 `truncated=true`，不会静默截断。
- 通过 WebSocket 主动连接 LazyMind，使用设备 ID/token 完成 hello 认证，支持断线重连和命令 deadline。
- 使用 `chrome.debugger`/CDP 创建并控制扩展自己的 managed window/tab。
- managed window 默认以最大化状态打开，保留 Chrome 标签栏、地址栏和用户接管能力。
- 已实现动作：
  - `open`
  - `navigate`
  - `snapshot`
  - `click`
  - `click_at`
  - `click_intersection`
  - `type`
  - `type_focused`
  - `select`
  - `press`
  - `scroll`
  - `wait`
  - `screenshot`
  - `tabs`
  - `close`
- snapshot 使用 Accessibility Tree 生成短期元素 `ref` 和 revision；旧 ref 会被拒绝。
- 测试阶段使用完全自动化模式，允许敏感字段输入、提交/发送等按钮、Enter 和任意按键；原安全判断以注释保留。
- 只允许 `http/https`，默认阻止 localhost、私网和云元数据地址；需要工具参数明确允许内网。

### 1.2 Core 内置 Browser Gateway

目录：`backend/core/browser/`

MVP 阶段把 Gateway 作为 Core 内置模块实现，没有新增独立进程，原因是 Docker 和 Desktop 已经共同运行 Core，能先复用现有构建、健康检查和生命周期。

已实现：

- 5 分钟有效、一次性使用的配对码。
- 32 字节随机设备 token，仅在服务端保存 SHA-256。
- 用户与设备隔离；跨用户不能枚举、撤销或调用设备。
- 单设备连接替换、离线检测、命令超时、pending command 路由。
- WebSocket 首帧认证，token 不进入 URL/query。
- 4MB 消息上限、协议版本检查和浏览器扩展 Origin 检查。
- 设备管理 API：
  - `POST /api/core/browser/manage/pairings`
  - `GET /api/core/browser/manage/devices`
  - `DELETE /api/core/browser/manage/devices/{device_id}`
- 扩展公开 API：
  - `POST /api/browser/v1/pair`
  - `GET /api/browser/v1/connect`（WebSocket）
- Streamable HTTP MCP：`POST /mcp/browser/v1`。
- MCP token 由 Core 内部签名并绑定 LazyMind user ID，不把用户 Web JWT 交给扩展。
- 发布 16 个 `browser.*` Tool；包含受边界校验的坐标点击、行列交点点击和焦点输入，不提供任意 JavaScript 或任意 CDP passthrough。

### 1.3 LazyMind Chat 接入

已实现：

- Core 在 `LAZYMIND_BROWSER_ENABLED=true` 且配置 `LAZYMIND_BROWSER_MCP_URL` 时注入第一方 `system_mcp_config`。
- 第一方 Browser MCP 与用户自己配置的 MCP 分开传输。
- Python Chat 加载第一方 Browser Tool；普通用户 MCP 原有行为不变。
- Docker 默认启用并使用 `http://core:8000/mcp/browser/v1`。
- Desktop/Local Runtime 默认启用并使用动态解析出的本机 Core 地址。

当前 Browser Tool 只进入普通 Chat。绑定 Workflow 的回合仍遵守现有工具隔离规则，不会自动获得浏览器控制。

### 1.4 Docker 与 Local 网络入口

Docker 已实现：

- Kong 新增仅指向 Core `/browser/extension/*` 的公开扩展路由。
- 该路由不接受/使用前端 JWT，只信任一次性配对码或设备 token。
- Nginx 为 `/api/browser/v1/connect` 单独开启 WebSocket Upgrade，普通 `/api/` 行为不变。
- Core Compose 环境启用 Browser MCP。

Local Runtime 已实现：

- local-proxy 新增 `/api/browser/v1` 路由并支持 WebSocket 反向代理。
- 只有该精确前缀允许扩展免 Web JWT 访问；代理会删除调用方伪造的 `X-User-*` 身份头。
- CORS 只在浏览器扩展路由接受 `chrome-extension://`/`edge-extension://` origin。
- local-runtime-manager 为 Core 注入 Browser MCP 动态本机地址。
- 设置页“依赖安装”新增“浏览器控制扩展”卡片，可一键把扩展安装到 `runtime/deps/browser-extension`。
- Core 新增依赖 API：`GET /api/core/system-dependencies/browser-extension`、`POST ...:check`、`POST ...:install`。
- 安装源支持 Desktop 内置 `browser-extension/` 目录、本地 ZIP，或远程 URL + SHA256。
- 远程包复用 editable-ppt 的安全 ZIP 解压规则，并增加 Manifest V3、service worker、popup 校验及 staging/原子替换。
- Desktop 仍提供“打开安装位置”，供需要读取/控制用户外部 Chrome 时选择安装目录。

普通 `make local-up` 和 Desktop 都使用 Chrome/Edge 扩展与独立有头窗口；两者复用同一套 Gateway/MCP、配对和工具协议。

这里复用的是 editable-ppt 的下载、校验、安全解压和安装模式，不复用其 Playwright Chromium：后者只能控制隔离浏览器，不能读取用户当前 Chrome 标签页或复用当前扩展授权。

### 1.5 已保留、默认关闭的 Desktop Electron 内嵌原型

目录：`desktop/electron/src/embedded-browser.js`、`frontend/src/modules/chat/components/DesktopEmbeddedBrowser/`

以下代码已经实现且没有删除，但不再是产品默认链路：

- 使用 Electron `WebContentsView` 把受控网页嵌入聊天页右侧，不使用会被 `X-Frame-Options`/CSP 拦截的 iframe。
- 内嵌页面使用独立的持久化 partition，并启用 `sandbox`、`contextIsolation`、关闭 Node integration，不向第三方网页注入 LazyMind preload。
- 第三方页面的相机、麦克风、定位、通知等 Electron 权限和直接下载默认拒绝；文件处理继续走 LazyMind 已授权流程。
- 实验开关开启后，Desktop 前端在用户已登录后创建一次性配对码并作为 `Electron WebContentsView` 设备连接 Browser Gateway；未登录时配对失败，不会执行页面动作。
- 默认构建不挂载聊天右侧面板，Desktop profile 不注入 Electron 设备偏好；只有显式设置 `VITE_DESKTOP_EMBEDDED_BROWSER=true` 才启用原型。
- 复用相同 16 个 MCP Tool 和 WebSocket 命令协议，除原有动作外支持 `click_at/type_focused` 视觉兜底和 `click_intersection` 网格定位链路。
- Electron 内使用 Accessibility Tree + 固定 CDP 命令完成元素观察和真实输入；不开放任意 JavaScript/CDP passthrough。
- 聊天页右侧提供地址栏、前进、后退、刷新、关闭和连接状态；用户可直接点击/登录并随时人工接管。
- 面板左边界可拖拽调整宽度并记住本机宽度。拖拽期间隐藏原生 WebContents 层，避免网页截获鼠标事件。
- 打开内嵌页面时暂时让位于任务/Workflow 右栏；关闭页面后恢复原面板状态。
- Desktop 与扩展一致启用完全自动化，可直接执行敏感字段输入、高风险按钮和 Enter 提交。
- 只允许 `http/https`，自动化默认阻止私网；地址栏由用户手工输入时视为明确允许访问该地址。

网页采用 React、Vue、Angular、Svelte 或服务端模板时，不需要分别适配框架。主驱动基于 DOM/Accessibility/CDP；后续只需针对 Canvas、复杂富文本、跨域 iframe 等特殊控件增加能力适配器。

## 2. 当前使用方式

### 2.1 Docker

1. 构建并启动 LazyMind：

   ```bash
   docker compose up --build
   ```

2. Chrome 打开 `chrome://extensions`，Edge 打开 `edge://extensions`，启用开发者模式并加载 `LazyMind/browser-extension/`。
3. 在 LazyMind“设置 → 系统工具 → 依赖安装 → 浏览器控制扩展”中生成 5 分钟有效的配对码。
4. 在扩展弹窗中填写 `http://127.0.0.1:8090` 和配对码。
5. 抓取当前页前点击“授权当前站点”。
6. 在 LazyMind 普通对话中使用，例如：
   - “抓取并总结我当前打开的页面。”
   - “打开 `https://example.com`，告诉我页面上有哪些链接。”
   - “打开这个表单，填写名称并提交。”

### 2.2 Desktop 开发版（外部 Chrome/Edge）

1. 正常启动 LazyMind Desktop 并登录；打开“设置 → 系统工具 → 依赖安装 → 浏览器控制扩展”，安装并打开扩展目录。
2. 在 Chrome 的 `chrome://extensions` 或 Edge 的 `edge://extensions` 开启开发者模式并“加载已解压的扩展程序”；浏览器确认和授权不能由 Desktop 静默代替。
3. 回到同一个设置弹窗生成 5 分钟有效的配对码；在扩展弹窗填写 Desktop 地址与配对码，等待显示连接成功。
4. 在普通对话中说“打开 `https://example.com`，告诉我页面上有哪些链接”。扩展会创建独立有头窗口，Agent 和用户都可以在该窗口继续操作。

Desktop 默认不再嵌入网页。已有内嵌原型仅供实验，必须在构建前显式设置 `VITE_DESKTOP_EMBEDDED_BROWSER=true`，不属于当前 PRD 验收路径。

### 2.3 `make local-up`

`make local-up` 已包含 Browser Gateway、MCP 注入、公开配对/WebSocket 路由和扩展依赖源。普通 Chrome 中访问 Local 前端和 Desktop Electron 都使用同一个扩展，并由扩展打开独立有头窗口。

需要改用远程依赖源时，在启动 Desktop 前同时设置：

```bash
LAZYMIND_BROWSER_EXTENSION_BUNDLE_URL=https://example.com/lazymind-browser-extension-0.1.0.zip
LAZYMIND_BROWSER_EXTENSION_BUNDLE_SHA256=<64位SHA256>
```

离线测试也可设置 `LAZYMIND_BROWSER_EXTENSION_BUNDLE_PATH` 指向本地 ZIP。URL 模式不会接受缺少 SHA256 的包。

如果扩展连接的 Desktop 前端端口发生变化，需要手工修改扩展地址。Native Messaging 完成后可自动发现动态端口。

`make local-up` 的必要前提：

1. 执行“设置 → 系统工具 → 依赖安装 → 浏览器控制扩展”，或直接在 Chrome 的 `chrome://extensions` / Edge 的 `edge://extensions` 开发者模式中加载仓库根目录的 `browser-extension/`。
2. 在“设置 → 系统工具 → 依赖安装 → 浏览器控制扩展”生成当前登录用户的一次性配对码，在扩展弹窗填写 `http://127.0.0.1:8090` 和配对码，等待状态显示在线。
3. 只有扩展在线后，“打开某 URL”才会新建扩展管理的独立有头 Chrome 窗口。仅运行 `make local-up`、未加载扩展时，后端没有实际浏览器设备可控制。

## 3. 已有测试

- Browser Hub：配对码一次性、过期、token 校验、用户隔离、命令/响应路由。
- Browser MCP：Bearer token、16 个 Tool schema 发布，且 Hub 白名单与发布清单保持一致。
- WebSocket：扩展 hello 认证、命令往返、拒绝普通 Web Origin。
- local-proxy：公开浏览器路由跳过 Web JWT、清除伪造身份头、扩展 Origin 仅限浏览器路由。
- Core：`go test ./...` 全量通过，包括 Browser Hub、WebSocket、MCP、Chat 注入和错误目录审计。
- Core Chat：新增浏览器开关、Streamable HTTP transport 和用户签名 token 注入测试。
- local-proxy：`go test ./...` 全量通过。
- local-runtime-manager：`go test ./...` 全量通过。
- Browser Extension 依赖安装：覆盖 Desktop 内置目录安装、远程 SHA256 包下载、checksum 错误拒绝和 ZIP 路径穿越拒绝。
- Frontend：相关文件通过 ESLint、项目 `pnpm typecheck` 和 `pnpm build` 生产构建；`typecheck:all` 仍有项目既有 generated API/旧组件错误，本次文件没有新增错误。
- Electron：`main.js`、`preload.js` 通过 `node --check`。
- 默认外部浏览器形态：Frontend feature gate 覆盖 Desktop 默认关闭、显式实验开启和非 Desktop 禁止开启；local-runtime-manager 覆盖 Desktop profile 不注入内嵌设备偏好。
- 保留的 Desktop 内嵌原型：URL scheme/私网限制、未知动作拒绝和 preload IPC 共 6 个 Node 测试通过；Frontend bridge 的 command/state/bounds/event 转发测试仍保留。
- 扩展 JavaScript：所有模块通过 `node --check`。
- Python Chat 改动：通过 AST 语法检查。
- VLM 浏览器定位与按请求注入：7 条 Python 单测通过，覆盖有/无 VLM 时的工具集合、截图解析、临时文件删除、坐标缩放、未找到与越界拒绝。
- Chrome 扩展坐标辅助测试 4 条、Electron 控制器测试 9 条通过；Core `browser/chat` Go 测试通过。
- Local MCP 依赖兼容性：`mcp 1.29.1` 下 Streamable HTTP 已进入正常 HTTP 鉴权流程，不再发生返回值解包错误；`pip check` 无依赖冲突。
- 模型 HTTP 429 映射：内置断言覆盖泛化 `invalid_request/provider_rejected` 修正为 `rate_limited`，并确认保留 `quota_exhausted` 等具体分类。当前轻量 Local venv 未安装 `pytest`，因此没有在该 venv 运行完整 pytest 文件。
- `docker compose config --quiet` 配置校验通过（未设置 `ACL_DB_DSN` 时仅有项目原有警告）。
- `git diff --check` 通过。

真实 Chrome 扩展已完成 `browser_open`、`browser_type` 和 `browser_snapshot` 联调；尚未完成真实打包 Desktop 中的扩展安装/配对，以及完整 click/submit/screenshot E2E，因此还不等同于最终产品验收。

## 4. 还没有完成

以下内容不能按“已完成”验收：

1. **设备持久化**：配对和设备当前在 Core 内存中，Core 重启后需要重新配对；尚未进入数据库和撤销审计表。
2. **设备管理 UI**：设置弹窗已能生成和复制一次性配对码，但尚无在线设备列表、单设备撤销和撤销审计页面。
3. **超长正文对象存储**：当前 200 万字符硬上限并显式标记；尚未实现分 chunk 上传、hash 汇总和 `browser.read_capture`。
4. **正式正文算法**：当前使用 DOM/正文候选启发式提取，尚未引入完整 Mozilla Readability 和正文质量对照集。
5. **可选审批模式**：当前产品决策为完全自动化；尚未实现可切换的 action/turn/thread 审批模式。
6. **Workflow/SubAgent**：绑定 Workflow 仍隔离 Browser Tool，尚未增加步骤级 capability policy。
7. **录制转 Skill**：语义事件录制、截图关键帧、轨迹去噪、SkillV2 draft/review/commit 均未实现。
8. **Desktop Native Messaging**：扩展目前仍使用 loopback WebSocket 和手工地址，尚未实现 Native Host 注册及动态端口发现。
9. **浏览器发布**：尚未制作 Chrome Web Store/Edge Add-ons 正式包、图标、隐私说明和商店审核材料。
10. **复杂页面完整覆盖**：已增加“截图 → VLM 定位 → 坐标点击 → 焦点输入”通用兜底，但跨域 iframe、页面新开的 popup/tab、Canvas、文件上传和各类富文本编辑器的真实站点 E2E 尚未完整覆盖。
11. **截图对象存储**：直接调用 `browser_screenshot` 仍以内联 JPEG base64 返回；`browser_visual_locate` 已在工具内部临时落盘并只向主模型返回坐标，但尚未提供可复用的短期对象 URL。
12. **生产级审计/限流**：尚未实现持久化动作审计、每用户并发限制、设备速率限制和告警。
13. **独立 Gateway 进程**：MVP 内置在 Core；需要独立扩缩容时再拆为 `backend/browser-gateway`，协议无需改变。
14. **扩展后台恢复**：受控 session 当前保存在 MV3 Service Worker 内存中；扩展后台重启或 debugger 脱离后，需要重新 `open`。
15. **浏览器自动启用**：Desktop 可以下载、校验并打开扩展目录，但普通 Chrome/Edge 扩展不能被应用静默启用；正式体验需发布 Chrome Web Store/Edge Add-ons，或在受管设备使用企业策略。
16. **默认远程制品**：代码已支持 URL + SHA256 下载，但当前仓库尚未发布默认远程扩展 ZIP；Desktop 安装包目前复用随包携带的扩展源。
17. **扩展升级/卸载 UI**：当前安装后按钮置为已安装，尚未实现版本比较、覆盖升级和清理安装目录。
18. **Desktop 真实 E2E**：尚未在打包后的 macOS/Windows 应用中覆盖扩展安装目录打开、配对、独立窗口创建、登录态持久化、导航和模型控制的自动化验收。

## 5. 本次代码量

按当前工作区行数统计（包含空行和声明行，未提交状态）：

- 生产代码/配置：新增约 **5112 行**，删除 30 行。
- 自动化测试：新增约 **970 行**，删除 2 行。
- 方案、实施状态和扩展 README：新增约 **636 行**，删除 83 行。
- 合计：新增约 **6718 行**，删除 115 行。

这里的“生产代码”包括 Chrome 扩展的 HTML/CSS/JS、Core Gateway/MCP、Chat 接入、Docker/Kong/Nginx、Desktop 扩展安装/配对入口、默认关闭的 WebContentsView 原型以及 local-proxy/runtime-manager 配置。

## 6. 建议下一步顺序

1. 用真实打包 Desktop 跑通扩展安装、配对、独立 Chrome/Edge 窗口和完全自动化操作。
2. 增加设备列表、撤销 UI 和设备持久化，完成 PRD 0.3 登录/授权产品体验。
3. 实现超长正文分块对象和 Readability，对照验收“完整、无乱码、无静默截断”。
4. 增加 Docker、Local、Desktop 共用的扩展 E2E fixture。
5. 如后续产品需要，再实现可切换的高风险审批和 Workflow capability policy。
6. 最后实现外部 Chrome Native Messaging 与录制转 Skill。
