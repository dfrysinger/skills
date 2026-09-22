import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = dirname(
  dirname(dirname(fileURLToPath(import.meta.url))),
);
const compatibilityAndHistoricalFiles = new Set([
  "README.md",
  "design/mailbox-ambiguous-wakeup-deduplication.md",
  "design/self-compact-session-control-decisions.json",
  "design/self-compact-structured-tool.md",
  "design/session-control-rename.md",
  "design/windows-agent-session-naming.md",
  "design/windows-cross-computer-mailbox-addressing.md",
  "design/windows-sdk-workflow-reliability.md",
  "extensions/session-control/discovery.test.mjs",
  "extensions/session-control/storage-root.mjs",
  "extensions/session-control/storage-root.test.mjs",
]);
const textExtensions = new Set([
  ".cmd",
  ".json",
  ".md",
  ".mjs",
  ".ps1",
  ".sh",
  ".yml",
]);
const deprecatedName = ["session", "inbox"].join("-");

async function collectUnexpectedReferences(directory, matches = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === ".git") continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await collectUnexpectedReferences(path, matches);
      continue;
    }
    const extension = entry.name.slice(entry.name.lastIndexOf("."));
    if (!textExtensions.has(extension)) continue;
    const repositoryPath = relative(repositoryRoot, path);
    if (compatibilityAndHistoricalFiles.has(repositoryPath)) continue;
    const content = await readFile(path, "utf8");
    if (content.toLowerCase().includes(deprecatedName)) {
      matches.push(repositoryPath);
    }
  }
  return matches;
}

test("current product surfaces use session-control naming", async () => {
  assert.deepEqual(await collectUnexpectedReferences(repositoryRoot), []);
});
