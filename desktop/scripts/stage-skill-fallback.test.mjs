import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const script = fileURLToPath(new URL("./stage-skill-fallback.mjs", import.meta.url));

test("fallback replaces partial Skill output with empty valid catalogs", () => {
  const runtime = mkdtempSync(path.join(os.tmpdir(), "lazymind-skill-fallback-"));
  try {
    const packageDir = path.join(runtime, "builtin-skills", "packages");
    const assetDir = path.join(runtime, "featured-skills", "assets");
    mkdirSync(packageDir, { recursive: true });
    mkdirSync(assetDir, { recursive: true });
    writeFileSync(path.join(packageDir, "partial.zip"), "partial");
    writeFileSync(path.join(assetDir, "partial.jpg"), "partial");

    const result = spawnSync(process.execPath, [script, runtime], { encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(
      JSON.parse(readFileSync(path.join(runtime, "builtin-skills", "catalog.json"), "utf8")),
      { schema_version: 1, skills: [] },
    );
    assert.deepEqual(
      JSON.parse(readFileSync(path.join(runtime, "featured-skills", "catalog.json"), "utf8")),
      { schema_version: 2, cases: [] },
    );
    assert.deepEqual(
      JSON.parse(readFileSync(path.join(runtime, "featured-skills", "downloads.json"), "utf8")),
      { schemaVersion: 1, bundles: {}, local: {} },
    );
    assert.equal(existsSync(path.join(packageDir, "partial.zip")), false);
    assert.equal(existsSync(path.join(assetDir, "partial.jpg")), false);
    assert.equal(existsSync(assetDir), true);
  } finally {
    rmSync(runtime, { recursive: true, force: true });
  }
});
