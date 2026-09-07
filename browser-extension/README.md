# LazyMind Browser Extension

当前目录是无需构建即可加载的 Chrome/Edge Manifest V3 开发版扩展。Chrome 与 Edge 共用同一个 Manifest、Gateway 协议和控制器；扩展会在配对时自动识别当前浏览器，并把 `Google Chrome` 或 `Microsoft Edge` 及浏览器版本上报给 LazyMind。

## 本地加载

1. 启动 LazyMind Docker，默认入口为 `http://127.0.0.1:8090`。
2. Chrome 在地址栏打开 `chrome://extensions`；Edge 打开 `edge://extensions`，然后启用“开发人员模式”。
3. 选择“加载已解压的扩展程序”，目录指向本目录 `browser-extension/`。
4. 在已登录的 LazyMind 中调用 `POST /api/core/browser/manage/pairings` 生成配对码。
5. 打开扩展，填写 LazyMind 地址与配对码。
6. 如需抓取当前页，点击“授权当前站点”。如需控制页面，直接在 LazyMind 对话中要求打开 URL；扩展只控制它为任务创建的窗口。

## Desktop 依赖安装

Desktop 用户可以在“设置 → 依赖安装 → 浏览器控制扩展”中安装扩展包。安装目录为 Desktop Runtime 下的 `deps/browser-extension`，安装完成后可点击“打开安装位置”。

Chrome/Edge 安全策略不允许 Desktop 在普通个人浏览器中静默启用扩展；仍需打开对应浏览器的扩展管理页、启用开发者模式并选择“加载解压缩的扩展”。正式商店版本发布后可分别改为 Chrome Web Store 或 Microsoft Edge Add-ons 安装；企业受管 Edge 可再使用 `ExtensionInstallForcelist` 部署。

## Edge 本地加载

1. 在 Edge 地址栏打开 `edge://extensions`。
2. 打开左侧“开发人员模式”。
3. 点击“加载解压缩的扩展”，选择本目录或 Desktop 安装出的 `deps/browser-extension` 目录。
4. 打开扩展弹窗，确认标题下方显示 `Microsoft Edge <版本>`。
5. 在 LazyMind“设置 → 依赖安装 → 浏览器控制扩展”中选择 Microsoft Edge，生成配对码并连接。
6. 抓取用户当前 Edge 标签页前，仍需点击“授权当前站点”；控制新页面时，扩展会创建最大化的独立 Edge 窗口。

Edge 开发版不需要单独复制一套源码。用于 Edge Add-ons 提交的 ZIP 也从本目录生成，避免 Chrome/Edge 两套控制器产生行为差异。

## 当前自动化边界

- 当前标签页仅支持读取，不能被 Agent 静默控制。
- 控制只针对扩展创建的 managed window/tab。
- Agent 打开 URL 时创建独立窗口，并默认以最大化状态显示。
- 测试阶段启用完全自动化：允许密码、OTP、支付与身份字段输入，也允许提交、发送、发布、删除、购买、付款、授权和 Enter 提交。
- 原高风险、敏感字段和按键白名单判断保留为代码注释，后续需要审批模式时可恢复。
- 仅允许 `http/https` URL；本地和内网 URL 需要工具调用明确设置 `allow_private_network`。
- 页面文本和 Accessibility 快照一律作为不可信内容返回。

## 尚未包含

- Chrome Web Store/Edge Add-ons 正式上架与签名包。
- Desktop Native Messaging；Desktop MVP 暂时通过本地 HTTP/WebSocket 代理。
- 设备凭证数据库持久化和产品设置页。
- 长正文分块对象存储；当前最多返回 200 万字符，并明确标记 `truncated`。
- 可切换的高风险操作审批 UI；当前产品决策为完全自动化。
- 录制操作转 Skill。
