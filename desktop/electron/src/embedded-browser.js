const { randomUUID } = require("node:crypto");

const CDP_VERSION = "1.3";
const MAX_SNAPSHOT_ELEMENTS = 500;
const HIDDEN_BOUNDS = { x: 0, y: 0, width: 1, height: 1 };
const INTERACTIVE_ROLES = new Set([
  "button", "checkbox", "combobox", "link", "listbox", "menuitem", "option",
  "radio", "searchbox", "slider", "spinbutton", "switch", "tab", "textbox",
  "treeitem", "heading", "StaticText",
]);
// Full-automation mode temporarily disables the local action safety policy.
// Keep the original rules here so they can be restored when an approval flow is available.
// const HIGH_RISK_NAME = /(提交|发送|发布|删除|移除|购买|付款|支付|转账|确认订单|授权|同意|submit|send|publish|delete|remove|buy|purchase|pay|transfer|authorize|approve)/i;
// const SENSITIVE_NAME = /(密码|口令|验证码|动态码|支付|银行卡|信用卡|身份证|password|passcode|otp|verification|credit card|card number|cvv|ssn)/i;
// const ALLOWED_KEYS = new Set([
//   "Escape", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
//   "Backspace", "Delete",
// ]);

class EmbeddedBrowserController {
  constructor({ WebContentsView, getHostWindow, onState, log = () => {} }) {
    this.WebContentsView = WebContentsView;
    this.getHostWindow = getHostWindow;
    this.onState = onState;
    this.log = log;
    this.view = null;
    this.session = null;
    this.bounds = null;
    this.visible = false;
    this.lastError = "";
    this.permissionSession = null;
    this.downloadListener = null;
  }

  async dispatch(action, payload = {}) {
    switch (String(action || "")) {
      case "open": return this.open(payload);
      case "navigate": return this.navigate(payload);
      case "capture_current_page":
      case "snapshot": return this.snapshot(this.requireSession(payload.session_id));
      case "click": return this.click(payload);
      case "click_at": return this.clickAt(payload);
      case "click_intersection": return this.clickIntersection(payload);
      case "type": return this.type(payload);
      case "type_focused": return this.typeFocused(payload);
      case "select": return this.select(payload);
      case "press": return this.press(payload);
      case "scroll": return this.scroll(payload);
      case "wait": return this.wait(payload);
      case "screenshot": return this.screenshot(payload);
      case "tabs": return this.tabs(payload);
      case "close": return this.close(payload);
      case "reload": return this.reload(payload);
      case "back": return this.goBack(payload);
      case "forward": return this.goForward(payload);
      default: throw browserError("UNSUPPORTED_ACTION", `不支持浏览器动作 ${action}`);
    }
  }

  state() {
    const contents = this.contents();
    return {
      open: Boolean(this.session && contents && !contents.isDestroyed()),
      visible: this.visible,
      loading: Boolean(contents?.isLoading()),
      session_id: this.session?.id || "",
      url: contents?.getURL() || this.session?.url || "",
      title: contents?.getTitle() || "",
      can_go_back: navigationCanGoBack(contents),
      can_go_forward: navigationCanGoForward(contents),
      error: this.lastError,
    };
  }

  setBounds(payload = {}) {
    const view = this.view;
    const host = this.getHostWindow();
    if (!view || !host || host.isDestroyed()) {
      this.visible = false;
      return this.state();
    }
    if (payload.visible === false) {
      this.visible = false;
      view.setVisible(false);
      this.emitState();
      return this.state();
    }
    const contentBounds = host.getContentBounds();
    const raw = payload.bounds || payload;
    const x = clampInteger(raw.x, 0, Math.max(0, contentBounds.width - 1));
    const y = clampInteger(raw.y, 0, Math.max(0, contentBounds.height - 1));
    const width = clampInteger(raw.width, 1, Math.max(1, contentBounds.width - x));
    const height = clampInteger(raw.height, 1, Math.max(1, contentBounds.height - y));
    this.bounds = { x, y, width, height };
    view.setBounds(this.bounds);
    view.setVisible(true);
    this.visible = true;
    this.emitState();
    return this.state();
  }

  async open(payload) {
    const url = validateTargetURL(payload.url, payload.allow_private_network);
    await this.disposeCurrent();
    const host = this.getHostWindow();
    if (!host || host.isDestroyed()) {
      throw browserError("OPEN_FAILED", "LazyMind Desktop 主窗口不可用");
    }

    const view = new this.WebContentsView({
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        backgroundThrottling: false,
        partition: "persist:lazymind-embedded-browser",
      },
    });
    this.view = view;
    this.session = {
      id: `bs_${randomUUID().replaceAll("-", "")}`,
      revision: 0,
      refs: new Map(),
      allowPrivateNetwork: Boolean(payload.allow_private_network),
      url,
    };
    this.lastError = "";
    host.contentView.addChildView(view);
    view.setBounds(HIDDEN_BOUNDS);
    view.setVisible(false);
    this.installNavigationGuards(view);
    this.installPermissionGuards(view);
    this.installStateEvents(view);
    this.emitState();

    try {
      view.webContents.debugger.attach(CDP_VERSION);
      await Promise.all([
        this.send("Page.enable"),
        this.send("DOM.enable"),
        this.send("Runtime.enable"),
        this.send("Accessibility.enable"),
      ]);
      await loadURLWithTimeout(view.webContents, url, 15000);
      return this.snapshot(this.session);
    } catch (error) {
      const normalized = normalizeError(error, "OPEN_FAILED");
      this.lastError = normalized.message;
      this.emitState();
      await this.disposeCurrent();
      throw normalized;
    }
  }

  async navigate(payload) {
    const session = this.requireSession(payload.session_id);
    const url = validateTargetURL(payload.url, payload.allow_private_network);
    session.allowPrivateNetwork = Boolean(payload.allow_private_network);
    session.url = url;
    this.lastError = "";
    this.emitState();
    await loadURLWithTimeout(this.contents(), url, 15000);
    return this.snapshot(session);
  }

  async snapshot(session) {
    const contents = this.requireContents();
    const tree = await this.send("Accessibility.getFullAXTree");
    session.revision += 1;
    session.refs = new Map();
    const elements = [];
    for (const node of tree.nodes || []) {
      const role = String(node.role?.value || "");
      const backendNodeId = node.backendDOMNodeId;
      if (node.ignored || !backendNodeId || !INTERACTIVE_ROLES.has(role)) continue;
      const name = normalizeText(node.name?.value || "");
      const value = normalizeText(node.value?.value || "");
      if (!name && !value && role !== "textbox") continue;
      const ref = `e_${backendNodeId}`;
      const properties = Object.fromEntries((node.properties || []).map((property) => [
        property.name,
        property.value?.value,
      ]));
      // Full-automation mode returns and accepts every field value.
      // const sensitive = Boolean(properties.protected) || SENSITIVE_NAME.test(name);
      const sensitive = false;
      session.refs.set(ref, { backendNodeId, role, name, sensitive });
      elements.push({
        ref,
        role,
        name,
        value: sensitive ? "" : value,
        state: Object.entries(properties)
          .filter(([, propertyValue]) => typeof propertyValue === "boolean" && propertyValue)
          .map(([propertyName]) => propertyName),
        sensitive,
      });
      if (elements.length >= MAX_SNAPSHOT_ELEMENTS) break;
    }
    this.emitState();
    return {
      untrusted_browser_content: true,
      session_id: session.id,
      revision: session.revision,
      url: contents.getURL() || "",
      title: contents.getTitle() || "",
      elements,
      limitations: elements.length >= MAX_SNAPSHOT_ELEMENTS
        ? ["snapshot_element_limit_reached"]
        : [],
    };
  }

  async click(payload) {
    const session = this.requireSession(payload.session_id);
    const target = this.resolveRef(session, payload.ref, payload.expected_revision);
    // Full-automation mode: allow consequential controls such as send and submit.
    // if (HIGH_RISK_NAME.test(target.name)) {
    //   throw browserError(
    //     "HUMAN_TAKEOVER_REQUIRED",
    //     `“${target.name || target.role}”可能产生外部或不可逆影响，请用户在内嵌页面中手工完成。`,
    //   );
    // }
    const rect = await this.elementRect(target);
    const x = rect.x + rect.width / 2;
    const y = rect.y + rect.height / 2;
    await this.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await this.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
    await this.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
    await delay(300);
    return this.snapshot(session);
  }

  async clickAt(payload) {
    const session = this.requireSession(payload.session_id);
    const viewport = await this.viewportSize();
    const point = normalizeViewportPoint(payload.x, payload.y, viewport);
    await this.dispatchClick(point.x, point.y);
    await delay(300);
    return this.snapshot(session);
  }

  async clickIntersection(payload) {
    const session = this.requireSession(payload.session_id);
    const rowTarget = this.resolveRef(session, payload.row_ref, payload.expected_revision);
    const columnTarget = this.resolveRef(session, payload.column_ref, payload.expected_revision);
    if (rowTarget.backendNodeId === columnTarget.backendNodeId) {
      throw browserError("INVALID_INTERSECTION", "行标签和列标题必须是两个不同的元素引用");
    }

    await this.elementRect(columnTarget);
    await this.elementRect(rowTarget);
    const rowRect = await this.elementRect(rowTarget, { scroll: false });
    const columnRect = await this.elementRect(columnTarget, { scroll: false });
    const viewport = await this.viewportSize();
    const point = intersectionPoint(rowRect, columnRect, viewport);
    const before = await this.inspectPoint(point);
    await this.dispatchClick(point.x, point.y);
    await delay(300);
    const after = await this.inspectPoint(point);
    const snapshot = await this.snapshot(session);
    return {
      ...snapshot,
      interaction: {
        kind: "intersection_click",
        row: { ref: payload.row_ref, name: rowTarget.name, rect: rowRect },
        column: { ref: payload.column_ref, name: columnTarget.name, rect: columnRect },
        point,
        before,
        after,
      },
    };
  }

  async type(payload) {
    const session = this.requireSession(payload.session_id);
    const target = this.resolveRef(session, payload.ref, payload.expected_revision);
    // Full-automation mode: allow sensitive-field input.
    // if (target.sensitive) {
    //   throw browserError("HUMAN_TAKEOVER_REQUIRED", "密码、验证码、支付或身份字段必须由用户在内嵌页面中手工输入。");
    // }
    await this.send("DOM.focus", { backendNodeId: target.backendNodeId });
    if (payload.replace) {
      const objectId = await this.resolveObject(target.backendNodeId);
      await this.send("Runtime.callFunctionOn", {
        objectId,
        functionDeclaration: `function () {
          if (!("value" in this)) return;
          const prototype = Object.getPrototypeOf(this);
          const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
          if (setter) setter.call(this, ""); else this.value = "";
          this.dispatchEvent(new Event("input", {bubbles: true}));
          this.dispatchEvent(new Event("change", {bubbles: true}));
        }`,
        returnByValue: true,
      });
    }
    await this.send("Input.insertText", { text: String(payload.text || "") });
    await delay(150);
    await this.verifyVisibleText(payload.verify_text);
    return this.snapshot(session);
  }

  async typeFocused(payload) {
    const session = this.requireSession(payload.session_id);
    if (payload.replace) {
      await this.clearFocusedElement();
    }
    await this.send("Input.insertText", { text: String(payload.text || "") });
    await delay(150);
    await this.verifyVisibleText(payload.verify_text);
    return this.snapshot(session);
  }

  async select(payload) {
    const session = this.requireSession(payload.session_id);
    const target = this.resolveRef(session, payload.ref, payload.expected_revision);
    const objectId = await this.resolveObject(target.backendNodeId);
    const response = await this.send("Runtime.callFunctionOn", {
      objectId,
      functionDeclaration: `function (value) {
        if (!(this instanceof HTMLSelectElement)) return {ok: false};
        this.value = value;
        this.dispatchEvent(new Event("input", {bubbles: true}));
        this.dispatchEvent(new Event("change", {bubbles: true}));
        return {ok: this.value === value, value: this.value};
      }`,
      arguments: [{ value: String(payload.value || "") }],
      returnByValue: true,
    });
    if (!response.result?.value?.ok) {
      throw browserError("SELECT_FAILED", "目标不是原生下拉框或选项值不存在");
    }
    return this.snapshot(session);
  }

  async press(payload) {
    const session = this.requireSession(payload.session_id);
    const key = String(payload.key || "");
    // Full-automation mode: allow Enter and keys outside the former allowlist.
    // if (key === "Enter") {
    //   throw browserError("HUMAN_TAKEOVER_REQUIRED", "Enter 可能提交表单或触发外部操作，请用户手工完成。");
    // }
    // if (!ALLOWED_KEYS.has(key)) {
    //   throw browserError("KEY_NOT_ALLOWED", `按键 ${key} 不在允许列表中`);
    // }
    await this.send("Input.dispatchKeyEvent", { type: "keyDown", key });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", key });
    await delay(150);
    return this.snapshot(session);
  }

  async scroll(payload) {
    const session = this.requireSession(payload.session_id);
    const objectId = await this.documentObject();
    await this.send("Runtime.callFunctionOn", {
      objectId,
      functionDeclaration: "function (x, y) { window.scrollBy({left: x, top: y, behavior: 'instant'}); }",
      arguments: [{ value: finiteNumber(payload.x) }, { value: finiteNumber(payload.y) }],
      returnByValue: true,
    });
    await delay(150);
    return this.snapshot(session);
  }

  async wait(payload) {
    const session = this.requireSession(payload.session_id);
    const timeout = Math.min(Math.max(Number(payload.timeout_ms) || 5000, 100), 30000);
    const text = String(payload.text || "");
    const url = String(payload.url || "");
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const objectId = await this.documentObject();
      const response = await this.send("Runtime.callFunctionOn", {
        objectId,
        functionDeclaration: `function (text, url) {
          const textOK = !text || (document.body?.innerText || "").includes(text);
          const urlOK = !url || location.href.includes(url);
          return {ok: textOK && urlOK, url: location.href};
        }`,
        arguments: [{ value: text }, { value: url }],
        returnByValue: true,
      });
      if (response.result?.value?.ok) return this.snapshot(session);
      await delay(250);
    }
    throw browserError("ACTION_TIMEOUT", "等待页面条件超时");
  }

  async screenshot(payload) {
    const session = this.requireSession(payload.session_id);
    const image = await this.requireContents().capturePage();
    const imageSize = image.getSize();
    return {
      session_id: session.id,
      url: this.contents().getURL() || "",
      title: this.contents().getTitle() || "",
      mime_type: "image/jpeg",
      data_base64: image.toJPEG(75).toString("base64"),
      viewport: await this.viewportSize(),
      image: { width: imageSize.width, height: imageSize.height },
    };
  }

  async tabs(payload) {
    const session = this.requireSession(payload.session_id);
    const contents = this.requireContents();
    return {
      session_id: session.id,
      tabs: [{ tab_id: contents.id, url: contents.getURL() || "", title: contents.getTitle() || "", active: true }],
    };
  }

  async close(payload) {
    const session = this.requireSession(payload.session_id);
    const sessionID = session.id;
    await this.disposeCurrent();
    return { session_id: sessionID, closed: true };
  }

  async reload(payload) {
    const session = this.requireSession(payload.session_id);
    const contents = this.requireContents();
    const loaded = waitForNextNavigation(contents, 15000);
    contents.reload();
    await loaded;
    return this.snapshot(session);
  }

  async goBack(payload) {
    const session = this.requireSession(payload.session_id);
    const contents = this.requireContents();
    if (!navigationCanGoBack(contents)) return this.snapshot(session);
    const loaded = waitForNextNavigation(contents, 15000);
    if (contents.navigationHistory) contents.navigationHistory.goBack();
    else contents.goBack();
    await loaded;
    return this.snapshot(session);
  }

  async goForward(payload) {
    const session = this.requireSession(payload.session_id);
    const contents = this.requireContents();
    if (!navigationCanGoForward(contents)) return this.snapshot(session);
    const loaded = waitForNextNavigation(contents, 15000);
    if (contents.navigationHistory) contents.navigationHistory.goForward();
    else contents.goForward();
    await loaded;
    return this.snapshot(session);
  }

  async dispose() {
    await this.disposeCurrent();
  }

  requireSession(sessionID) {
    if (!this.session || this.session.id !== String(sessionID || "")) {
      throw browserError("SESSION_NOT_FOUND", "Desktop 内嵌浏览器会话不存在或已经关闭");
    }
    this.requireContents();
    return this.session;
  }

  requireContents() {
    const contents = this.contents();
    if (!contents || contents.isDestroyed()) {
      throw browserError("BROWSER_DETACHED", "Desktop 内嵌浏览器已经关闭");
    }
    return contents;
  }

  contents() {
    return this.view?.webContents || null;
  }

  resolveRef(session, ref, expectedRevision) {
    if (expectedRevision && Number(expectedRevision) !== session.revision) {
      throw browserError("STALE_SNAPSHOT", "页面快照已经变化，请重新获取 snapshot");
    }
    const target = session.refs.get(String(ref || ""));
    if (!target) throw browserError("STALE_SNAPSHOT", "元素引用不存在，请重新获取 snapshot");
    return target;
  }

  async elementRect(target, options = {}) {
    if (options.scroll !== false) {
      try {
        await this.send("DOM.scrollIntoViewIfNeeded", { backendNodeId: target.backendNodeId });
      } catch {}
    }

    try {
      const response = await this.send("DOM.getContentQuads", { backendNodeId: target.backendNodeId });
      const rect = rectFromQuads(response.quads);
      if (rect) return rect;
    } catch {}

    const objectId = await this.resolveObject(target.backendNodeId);
    const response = await this.send("Runtime.callFunctionOn", {
      objectId,
      functionDeclaration: `function (shouldScroll) {
        const visibleRect = (rect) => rect && rect.width > 0 && rect.height > 0
          ? {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
          : null;
        const scrollTarget = this && this.nodeType === 1 ? this : this?.parentElement;
        if (shouldScroll) {
          scrollTarget?.scrollIntoView({block: "center", inline: "center", behavior: "instant"});
        }

        if (this && this.nodeType === 3) {
          const range = document.createRange();
          range.selectNodeContents(this);
          const textRect = visibleRect(range.getBoundingClientRect());
          range.detach?.();
          if (textRect) return textRect;
        }

        let candidate = this && this.nodeType === 1 ? this : this?.parentElement;
        for (let depth = 0; candidate && depth < 5; depth += 1, candidate = candidate.parentElement) {
          const rect = visibleRect(candidate.getBoundingClientRect?.());
          if (rect) return rect;
        }
        return null;
      }`,
      arguments: [{ value: options.scroll !== false }],
      returnByValue: true,
    });
    const rect = response.result?.value;
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      throw browserError("ELEMENT_NOT_VISIBLE", "目标元素不可见或没有可点击区域");
    }
    return rect;
  }

  async viewportSize() {
    const metrics = await this.send("Page.getLayoutMetrics");
    const viewport = metrics.cssVisualViewport || metrics.cssLayoutViewport ||
      metrics.visualViewport || metrics.layoutViewport || {};
    const width = Number(viewport.clientWidth || viewport.width);
    const height = Number(viewport.clientHeight || viewport.height);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw browserError("VIEWPORT_UNAVAILABLE", "无法获取浏览器视口尺寸");
    }
    return { width, height };
  }

  async dispatchClick(x, y) {
    await this.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await this.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
    await this.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
  }

  async inspectPoint(point) {
    const response = await this.send("Runtime.evaluate", {
      expression: `(() => {
        const describe = (element) => {
          if (!element) return null;
          return {
            tag: String(element.tagName || "").toLowerCase(),
            role: element.getAttribute?.("role") || "",
            aria_label: element.getAttribute?.("aria-label") || "",
            contenteditable: element.getAttribute?.("contenteditable") || "",
            editable: Boolean(element.isContentEditable),
            readonly: Boolean(element.readOnly),
          };
        };
        return {
          hit_target: describe(document.elementFromPoint(${JSON.stringify(point.x)}, ${JSON.stringify(point.y)})),
          focused: describe(document.activeElement),
        };
      })()`,
      returnByValue: true,
      silent: true,
    });
    return response.result?.value || {};
  }

  async clearFocusedElement() {
    await this.send("Runtime.evaluate", {
      expression: `(() => {
        const element = document.activeElement;
        if (!element) return false;
        if ("value" in element) {
          const prototype = Object.getPrototypeOf(element);
          const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
          if (setter) setter.call(element, ""); else element.value = "";
          element.dispatchEvent(new Event("input", {bubbles: true}));
          element.dispatchEvent(new Event("change", {bubbles: true}));
          return true;
        }
        if (element.isContentEditable) {
          document.execCommand("selectAll", false, null);
          document.execCommand("delete", false, null);
          return true;
        }
        return false;
      })()`,
      returnByValue: true,
      silent: true,
    });
  }

  async verifyVisibleText(rawText) {
    const text = String(rawText || "");
    if (!text) return;
    const deadline = Date.now() + 3000;
    while (Date.now() < deadline) {
      const response = await this.send("Runtime.evaluate", {
        expression: `(() => (document.body?.innerText || "").includes(${JSON.stringify(text)}))()`,
        returnByValue: true,
        silent: true,
      });
      if (response.result?.value) return;
      await delay(100);
    }
    throw browserError("TYPE_NOT_APPLIED", `输入完成后页面未出现校验文本“${text.slice(0, 80)}”`);
  }

  async resolveObject(backendNodeId) {
    const response = await this.send("DOM.resolveNode", { backendNodeId });
    const objectId = response.object?.objectId;
    if (!objectId) throw browserError("STALE_SNAPSHOT", "页面节点已失效，请重新获取 snapshot");
    return objectId;
  }

  async documentObject() {
    const response = await this.send("Runtime.evaluate", {
      expression: "document", returnByValue: false, silent: true,
    });
    const objectId = response.result?.objectId;
    if (!objectId) throw browserError("PAGE_UNAVAILABLE", "无法访问当前文档");
    return objectId;
  }

  send(method, params = {}) {
    return this.requireContents().debugger.sendCommand(method, params);
  }

  installNavigationGuards(view) {
    const navigateFromPage = (url) => {
      try {
        const target = validateTargetURL(url, this.session?.allowPrivateNetwork);
        void view.webContents.loadURL(target).catch((error) => {
          this.lastError = String(error?.message || error);
          this.emitState();
        });
      } catch (error) {
        this.lastError = String(error?.message || error);
        this.emitState();
      }
    };
    view.webContents.setWindowOpenHandler(({ url }) => {
      navigateFromPage(url);
      return { action: "deny" };
    });
    const guardMainFrameNavigation = (event, url) => {
      try {
        validateTargetURL(url, this.session?.allowPrivateNetwork);
      } catch (error) {
        event.preventDefault();
        this.lastError = String(error?.message || error);
        this.emitState();
      }
    };
    view.webContents.on("will-navigate", guardMainFrameNavigation);
    view.webContents.on("will-redirect", guardMainFrameNavigation);
  }

  installStateEvents(view) {
    for (const eventName of ["did-start-loading", "did-stop-loading", "did-navigate", "did-navigate-in-page", "page-title-updated"]) {
      view.webContents.on(eventName, () => this.emitState());
    }
    view.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (!isMainFrame || errorCode === -3) return;
      this.lastError = `${errorDescription} (${validatedURL})`;
      this.emitState();
    });
    view.webContents.on("render-process-gone", (_event, details) => {
      this.lastError = `页面渲染进程已退出：${details.reason}`;
      this.emitState();
    });
  }

  installPermissionGuards(view) {
    const browserSession = view.webContents.session;
    browserSession.setPermissionCheckHandler(() => false);
    browserSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
    const downloadListener = (event) => {
      event.preventDefault();
      this.lastError = "自动下载已阻止；请在 LazyMind 中使用经过授权的文件流程。";
      this.emitState();
    };
    browserSession.on("will-download", downloadListener);
    this.permissionSession = browserSession;
    this.downloadListener = downloadListener;
  }

  async disposeCurrent() {
    const view = this.view;
    this.view = null;
    this.session = null;
    this.bounds = null;
    this.visible = false;
    if (this.permissionSession) {
      if (this.downloadListener) {
        this.permissionSession.removeListener("will-download", this.downloadListener);
      }
      this.permissionSession.setPermissionCheckHandler(null);
      this.permissionSession.setPermissionRequestHandler(null);
    }
    this.permissionSession = null;
    this.downloadListener = null;
    if (view) {
      const host = this.getHostWindow();
      try { view.webContents.debugger.detach(); } catch {}
      try {
        if (host && !host.isDestroyed()) host.contentView.removeChildView(view);
      } catch {}
      try {
        if (!view.webContents.isDestroyed()) view.webContents.close();
      } catch (error) {
        this.log(`could not close embedded browser: ${error.message}`);
      }
    }
    this.emitState();
  }

  emitState() {
    try { this.onState(this.state()); } catch {}
  }
}

function validateTargetURL(raw, allowPrivateNetwork) {
  let parsed;
  try { parsed = new URL(String(raw || "")); } catch {
    throw browserError("INVALID_URL", "URL 格式无效");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw browserError("URL_NOT_ALLOWED", "只允许打开 http/https URL");
  }
  if (!allowPrivateNetwork && isPrivateHost(parsed.hostname)) {
    throw browserError("PRIVATE_NETWORK_BLOCKED", "本地或内网地址需要用户明确允许");
  }
  parsed.username = "";
  parsed.password = "";
  return parsed.toString();
}

function isPrivateHost(host) {
  const normalized = String(host || "").toLowerCase().replace(/^\[|\]$/g, "").replace(/\.$/, "");
  if (!normalized || normalized === "localhost" || normalized.endsWith(".localhost")
      || normalized.endsWith(".local") || normalized === "metadata.google.internal") return true;
  const octets = normalized.split(".").map(Number);
  if (octets.length === 4 && octets.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)) {
    const [first, second] = octets;
    if (first === 0 || first === 10 || first === 127 || first >= 224) return true;
    if (first === 100 && second >= 64 && second <= 127) return true;
    if (first === 169 && second === 254) return true;
    if (first === 172 && second >= 16 && second <= 31) return true;
    if (first === 192 && second === 168) return true;
  }
  if (normalized === "::" || normalized === "::1") return true;
  if (/^f[cd][0-9a-f]{2}:/.test(normalized) || /^fe[89ab][0-9a-f]:/.test(normalized)) return true;
  if (normalized.startsWith("::ffff:")) return isPrivateHost(normalized.slice("::ffff:".length));
  return false;
}

function clampInteger(value, min, max) {
  const number = Math.round(Number(value));
  if (!Number.isFinite(number)) return min;
  return Math.max(min, Math.min(max, number));
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function normalizeViewportPoint(rawX, rawY, viewport) {
  const x = Number(rawX);
  const y = Number(rawY);
  const width = Number(viewport?.width);
  const height = Number(viewport?.height);
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
    throw browserError("INVALID_COORDINATES", "坐标或视口尺寸无效");
  }
  if (x < 0 || y < 0 || x >= width || y >= height) {
    throw browserError(
      "COORDINATE_OUT_OF_BOUNDS",
      `坐标 (${x}, ${y}) 超出视口 ${width}x${height}`,
    );
  }
  return { x, y };
}

function intersectionPoint(rowRect, columnRect, viewport) {
  const rowY = Number(rowRect?.y) + Number(rowRect?.height) / 2;
  const columnX = Number(columnRect?.x) + Number(columnRect?.width) / 2;
  if (![rowY, columnX].every(Number.isFinite)) {
    throw browserError("INVALID_INTERSECTION", "无法从行标签和列标题计算交点");
  }
  return normalizeViewportPoint(columnX, rowY, viewport);
}

function rectFromQuads(quads) {
  for (const quad of quads || []) {
    if (!Array.isArray(quad) || quad.length < 8) continue;
    const xs = [Number(quad[0]), Number(quad[2]), Number(quad[4]), Number(quad[6])];
    const ys = [Number(quad[1]), Number(quad[3]), Number(quad[5]), Number(quad[7])];
    if (![...xs, ...ys].every(Number.isFinite)) continue;
    const x = Math.min(...xs);
    const y = Math.min(...ys);
    const width = Math.max(...xs) - x;
    const height = Math.max(...ys) - y;
    if (width > 0 && height > 0) return { x, y, width, height };
  }
  return null;
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, 500);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function loadURLWithTimeout(contents, url, timeout) {
  let timer;
  try {
    return await Promise.race([
      contents.loadURL(url),
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(browserError("ACTION_TIMEOUT", "页面加载超时")),
          timeout,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

function waitForNextNavigation(contents, timeout) {
  if (!contents || contents.isDestroyed()) return Promise.resolve();
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer);
      contents.removeListener("did-stop-loading", finish);
      contents.removeListener("did-fail-load", finish);
      resolve();
    };
    const timer = setTimeout(finish, timeout);
    contents.once("did-stop-loading", finish);
    contents.once("did-fail-load", finish);
  });
}

function navigationCanGoBack(contents) {
  if (!contents || contents.isDestroyed()) return false;
  if (contents.navigationHistory) return Boolean(contents.navigationHistory.canGoBack());
  return Boolean(contents.canGoBack?.());
}

function navigationCanGoForward(contents) {
  if (!contents || contents.isDestroyed()) return false;
  if (contents.navigationHistory) return Boolean(contents.navigationHistory.canGoForward());
  return Boolean(contents.canGoForward?.());
}

function browserError(code, message, details) {
  const error = new Error(message);
  error.code = code;
  error.details = details;
  return error;
}

function normalizeError(error, fallbackCode) {
  if (error?.code) return error;
  return browserError(fallbackCode, String(error?.message || error));
}

module.exports = {
  EmbeddedBrowserController,
  intersectionPoint,
  isPrivateHost,
  normalizeViewportPoint,
  rectFromQuads,
  validateTargetURL,
};
