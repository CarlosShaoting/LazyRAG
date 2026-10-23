#!/usr/bin/env node
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const runtimeRoot = process.argv[2];
if (!runtimeRoot || !path.isAbsolute(runtimeRoot) || !existsSync(runtimeRoot)) {
  console.error("usage: stage-skill-fallback.mjs <existing absolute runtime directory>");
  process.exit(2);
}

function writeCatalog(directory, filename, catalog) {
  const root = path.join(runtimeRoot, directory);
  rmSync(root, { recursive: true, force: true });
  mkdirSync(root, { recursive: true });
  writeFileSync(path.join(root, filename), JSON.stringify(catalog) + "\n");
  return root;
}

writeCatalog("builtin-skills", "catalog.json", { schema_version: 1, skills: [] });
const featuredRoot = writeCatalog("featured-skills", "catalog.json", { schema_version: 2, cases: [] });
mkdirSync(path.join(featuredRoot, "assets"));
writeFileSync(
  path.join(featuredRoot, "downloads.json"),
  JSON.stringify({ schemaVersion: 1, bundles: {}, local: {} }) + "\n",
);
