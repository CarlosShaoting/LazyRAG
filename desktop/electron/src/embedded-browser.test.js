const assert = require("node:assert/strict");
const test = require("node:test");

const {
  EmbeddedBrowserController,
  intersectionPoint,
  isPrivateHost,
  normalizeViewportPoint,
  rectFromQuads,
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

test("normalizeViewportPoint validates VLM coordinates", () => {
  assert.deepEqual(
    normalizeViewportPoint(200.5, 100, { width: 800, height: 600 }),
    { x: 200.5, y: 100 },
  );
  assert.throws(
    () => normalizeViewportPoint(-1, 100, { width: 800, height: 600 }),
    (error) => error.code === "COORDINATE_OUT_OF_BOUNDS",
  );
});

test("rectFromQuads derives a clickable rectangle for accessibility text nodes", () => {
  assert.deepEqual(
    rectFromQuads([[100, 40, 260, 40, 260, 64, 100, 64]]),
    { x: 100, y: 40, width: 160, height: 24 },
  );
  assert.equal(rectFromQuads([[0, 0, 0, 0, 0, 0, 0, 0]]), null);
});

test("intersectionPoint combines the column x coordinate with the row y coordinate", () => {
  assert.deepEqual(
    intersectionPoint(
      { x: 100, y: 520, width: 90, height: 30 },
      { x: 700, y: 60, width: 80, height: 30 },
      { width: 1200, height: 800 },
    ),
    { x: 740, y: 535 },
  );
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
      ["person", { backendNodeId: 3, role: "StaticText", name: "崔绍庭", sensitive: false }],
      ["date", { backendNodeId: 4, role: "StaticText", name: "9/7", sensitive: false }],
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

test("intersection click resolves row and column refs before dispatching", async () => {
  const controller = automationController();
  const points = [];
  controller.elementRect = async (target) => target.backendNodeId === 3
    ? { x: 100, y: 520, width: 90, height: 30 }
    : { x: 700, y: 60, width: 80, height: 30 };
  controller.viewportSize = async () => ({ width: 1200, height: 800 });
  controller.inspectPoint = async () => ({ hit_target: { tag: "div" } });
  controller.dispatchClick = async (x, y) => points.push({ x, y });

  const result = await controller.clickIntersection({
    session_id: "bs_test",
    row_ref: "person",
    column_ref: "date",
    expected_revision: 1,
  });

  assert.deepEqual(points, [{ x: 740, y: 535 }]);
  assert.equal(result.interaction.row.name, "崔绍庭");
  assert.equal(result.interaction.column.name, "9/7");
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
