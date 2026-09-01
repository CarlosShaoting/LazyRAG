import { describe, expect, it } from "vitest";

import { resolveRuntimeFeatures } from "./features";

describe("resolveRuntimeFeatures", () => {
  it("keeps the embedded browser disabled by default in Desktop", () => {
    expect(
      resolveRuntimeFeatures({ VITE_LAZYMIND_MODE: "desktop" })
        .desktopEmbeddedBrowser,
    ).toBe(false);
  });

  it("allows the retained Desktop prototype to be enabled explicitly", () => {
    expect(
      resolveRuntimeFeatures({
        VITE_LAZYMIND_MODE: "desktop",
        VITE_DESKTOP_EMBEDDED_BROWSER: "true",
      }).desktopEmbeddedBrowser,
    ).toBe(true);
  });

  it("never enables the embedded browser outside Desktop", () => {
    expect(
      resolveRuntimeFeatures({
        VITE_LAZYMIND_MODE: "local",
        VITE_DESKTOP_EMBEDDED_BROWSER: "true",
      }).desktopEmbeddedBrowser,
    ).toBe(false);
  });
});
