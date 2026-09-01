const assert = require("node:assert/strict");
const test = require("node:test");

const { createDesktopBridge } = require("./preload");

test("desktop preload exposes embedded browser IPC without exposing ipcRenderer", async () => {
  const calls = [];
  const listeners = new Map();
  const ipcRenderer = {
    invoke: async (...args) => {
      calls.push(args);
      return { ok: true };
    },
    send: () => {},
    on: (channel, listener) => listeners.set(channel, listener),
    removeListener: (channel, listener) => {
      if (listeners.get(channel) === listener) listeners.delete(channel);
    },
  };
  const bridge = createDesktopBridge(ipcRenderer);

  await bridge.embeddedBrowserState();
  await bridge.embeddedBrowserBounds({ x: 1, y: 2, width: 3, height: 4 });
  await bridge.embeddedBrowserCommand("snapshot", { session_id: "bs_1" });

  assert.deepEqual(calls, [
    ["lazymind:embeddedBrowserState"],
    ["lazymind:embeddedBrowserBounds", { x: 1, y: 2, width: 3, height: 4 }],
    ["lazymind:embeddedBrowserCommand", "snapshot", { session_id: "bs_1" }],
  ]);

  let received;
  const unsubscribe = bridge.onEmbeddedBrowserState((state) => { received = state; });
  listeners.get("lazymind:embeddedBrowserState")({}, { open: true, session_id: "bs_1" });
  assert.deepEqual(received, { open: true, session_id: "bs_1" });
  unsubscribe();
  assert.equal(listeners.has("lazymind:embeddedBrowserState"), false);
});
