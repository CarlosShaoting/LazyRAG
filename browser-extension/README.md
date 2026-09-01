# LazyMind Browser Extension

当前目录是无需构建即可加载的 Chrome/Edge Manifest V3 开发版扩展。

## 本地加载

1. 启动 LazyMind Docker，默认入口为 `http://127.0.0.1:8090`。
2. 打开 `chrome://extensions`，启用开发者模式。
3. 选择“加载已解压的扩展程序”，目录指向本目录 `browser-extension/`。
4. 在已登录的 LazyMind 中调用 `POST /api/core/browser/manage/pairings` 生成配对码。
5. 打开扩展，填写 LazyMind 地址与配对码。
6. 如需抓取当前页，点击“授权当前站点”。如需控制页面，直接在 LazyMind 对话中要求打开 URL；扩展只控制它为任务创建的窗口。

## Desktop 依赖安装

Desktop 用户可以在“设置 → 依赖安装 → 浏览器控制扩展”中安装扩展包。安装目录为 Desktop Runtime 下的 `deps/browser-extension`，安装完成后可点击“打开安装位置”。

Chrome 安全策略不允许 Desktop 静默启用普通扩展；仍需打开 `chrome://extensions`、启用开发者模式并选择“加载已解压的扩展程序”。正式商店版本发布后可改为 Chrome Web Store 安装。

## 当前自动化边界

- 当前标签页仅支持读取，不能被 Agent 静默控制。
- 控制只针对扩展创建的 managed window/tab。
- 测试阶段启用完全自动化：允许密码、OTP、支付与身份字段输入，也允许提交、发送、发布、删除、购买、付款、授权和 Enter 提交。
- 原高风险、敏感字段和按键白名单判断保留为代码注释，后续需要审批模式时可恢复。
- 仅允许 `http/https` URL；本地和内网 URL 需要工具调用明确设置 `allow_private_network`。
- 页面文本和 Accessibility 快照一律作为不可信内容返回。

## 尚未包含

- Chrome Web Store/Edge Add-ons 正式签名包。
- Desktop Native Messaging；Desktop MVP 暂时通过本地 HTTP/WebSocket 代理。
- 设备凭证数据库持久化和产品设置页。
- 长正文分块对象存储；当前最多返回 200 万字符，并明确标记 `truncated`。
- 可切换的高风险操作审批 UI；当前产品决策为完全自动化。
- 录制操作转 Skill。
