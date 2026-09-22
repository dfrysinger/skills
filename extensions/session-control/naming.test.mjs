import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, extname, join } from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
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

async function collectUnexpectedReferences() {
  const { stdout } = await execFileAsync("git", ["ls-files", "-z"], {
    cwd: repositoryRoot,
    encoding: "buffer",
  });
  const matches = [];
  for (const repositoryPath of stdout.toString("utf8").split("\0")) {
    if (!repositoryPath) continue;
    const extension = extname(repositoryPath);
    if (!textExtensions.has(extension)) continue;
    if (compatibilityAndHistoricalFiles.has(repositoryPath)) continue;
    const content = await readFile(join(repositoryRoot, repositoryPath), "utf8");
    if (content.toLowerCase().includes(deprecatedName)) {
      matches.push(repositoryPath);
    }
  }
  return matches;
}

test("current product surfaces use session-control naming", async () => {
  assert.deepEqual(await collectUnexpectedReferences(), []);
});
