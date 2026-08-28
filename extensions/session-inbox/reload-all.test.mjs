import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const script = join(dirname(fileURLToPath(import.meta.url)), "reload-all.mjs");

test("reports requested sessions with stale heartbeats as restart required", async () => {
  const root = await mkdtemp(join(tmpdir(), "extension-reload-all-"));
  try {
    const instanceDirectory = join(root, "instances");
    await mkdir(instanceDirectory, { recursive: true });
    await writeFile(
      join(instanceDirectory, "session-1-generation-1.json"),
      `${JSON.stringify({
        sessionId: "session-1",
        generation: "generation-1",
        tmuxSession: "hotel",
        updatedAt: new Date(Date.now() - 60_000).toISOString(),
      })}\n`,
    );
    const child = spawn(process.execPath, [script, "hotel"], {
      env: { ...process.env, COPILOT_SESSION_INBOX_DIR: root },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    const exit = await new Promise((resolve) => {
      child.on("exit", (code, signal) => resolve({ code, signal }));
    });
    assert.deepEqual(exit, { code: 2, signal: null });
    assert.match(stderr, /hotel: restart required: session-inbox heartbeat is stale/);
    assert.match(stdout, /Restart required: hotel/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
