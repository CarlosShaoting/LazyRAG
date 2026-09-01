const assert = require("node:assert/strict");
const test = require("node:test");

const {
  EmbeddedBrowserController,
  isPrivateHost,
  validateTargetURL,
} = require("./embedded-browser");

test("validateTargetURL accepts public HTTP(S) URLs and removes credentials", () => {
  assert.equal(
    validateTargetURL("https://user:secret@example.com/path?q=1", false),
    "https://example.com/path?q=1",
  );
});

test("validateTargetURL rejects unsupported schemes", () => {
  assert.throws(
    () => validateTargetURL("file:///etc/passwd", true),
    (error) => error.code === "URL_NOT_ALLOWED",
  );
});

test("validateTargetURL requires an explicit opt-in for private targets", () => {
  assert.throws(
    () => validateTargetURL("http://127.0.0.1:8080", false),
    (error) => error.code === "PRIVATE_NETWORK_BLOCKED",
  );
  assert.equal(
    validateTargetURL("http://127.0.0.1:8080", true),
    "http://127.0.0.1:8080/",
  );
});

test("isPrivateHost covers loopback, RFC1918, link-local, and IPv6 local ranges", () => {
  for (const host of ["localhost", "10.0.0.1", "172.20.1.1", "192.168.1.2", "169.254.1.1", "::1", "fd00::1"]) {
    assert.equal(isPrivateHost(host), true, host);
  }
  assert.equal(isPrivateHost("example.com"), false);
});

test("controller rejects unknown actions before creating a view", async () => {
  const controller = new EmbeddedBrowserController({
    WebContentsView: class {},
    getHostWindow: () => null,
    onState: () => {},
  });
  await assert.rejects(
    controller.dispatch("evaluate", {}),
    (error) => error.code === "UNSUPPORTED_ACTION",
  );
});

function automationController() {
  const controller = new EmbeddedBrowserController({
    WebContentsView: class {},
    getHostWindow: () => null,
    onState: () => {},
  });
  controller.view = { webContents: { isDestroyed: () => false } };
  controller.session = {
    id: "bs_test",
    revision: 1,
    refs: new Map([
      ["send", { backendNodeId: 1, role: "button", name: "发送", sensitive: false }],
      ["password", { backendNodeId: 2, role: "textbox", name: "密码", sensitive: true }],
    ]),
  };
  controller.snapshot = async () => ({ session_id: controller.session.id });
  return controller;
}

test("full-automation mode clicks consequential controls", async () => {
  const controller = automationController();
  const commands = [];
  controller.elementRect = async () => ({ x: 0, y: 0, width: 100, height: 40 });
  controller.send = async (method, params) => commands.push({ method, params });

  await controller.click({ session_id: "bs_test", ref: "send", expected_revision: 1 });

  assert.equal(commands.filter(({ method }) => method === "Input.dispatchMouseEvent").length, 3);
});

test("full-automation mode types into sensitive fields", async () => {
  const controller = automationController();
  const commands = [];
  controller.send = async (method, params) => commands.push({ method, params });

  await controller.type({
    session_id: "bs_test",
    ref: "password",
    expected_revision: 1,
    text: "secret",
  });

  assert.ok(commands.some(({ method, params }) => method === "Input.insertText" && params.text === "secret"));
});

test("full-automation mode presses Enter", async () => {
  const controller = automationController();
  const commands = [];
  controller.send = async (method, params) => commands.push({ method, params });

  await controller.press({ session_id: "bs_test", key: "Enter" });

  assert.deepEqual(
    commands.map(({ method, params }) => [method, params.type, params.key]),
    [
      ["Input.dispatchKeyEvent", "keyDown", "Enter"],
      ["Input.dispatchKeyEvent", "keyUp", "Enter"],
    ],
  );
});
