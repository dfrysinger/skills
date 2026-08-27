import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  chmod,
  cp,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const sourceExtension = join(
  dirname(fileURLToPath(import.meta.url)),
  "extension.mjs",
);

async function runExtension(brief) {
  const root = await mkdtemp(join(tmpdir(), "self-compact-extension-"));
  const extensionPath = join(root, "extension.mjs");
  const sdkDirectory = join(root, "node_modules", "@github", "copilot-sdk");
  const submitter = join(root, "submitter.sh");
  const capture = join(root, "capture.json");
  const input = join(root, "input.txt");
  await mkdir(sdkDirectory, { recursive: true });
  await cp(sourceExtension, extensionPath);
  await writeFile(input, brief);
  await writeFile(
    join(sdkDirectory, "package.json"),
    `${JSON.stringify({
      name: "@github/copilot-sdk",
      type: "module",
      exports: { "./extension": "./extension.mjs" },
    })}\n`,
  );
  await writeFile(
    join(sdkDirectory, "extension.mjs"),
    `import {readFileSync} from "node:fs";
export async function joinSession({tools}) {
  const tool = tools.find(({name}) => name === "self_compact");
  const result = await tool.handler(
    {brief: readFileSync(process.env.MOCK_INPUT, "utf8")},
    {sessionId: "session-123", toolCallId: "call-456", toolName: "self_compact"},
  );
  process.stdout.write(JSON.stringify({
    result,
    schema: tool.parameters,
    defer: tool.defer,
  }));
}
`,
  );
  await writeFile(
    submitter,
    `#!/usr/bin/env bash
set -euo pipefail
printf '{"args":["%s","%s"],"session":"%s"}\\n' \
  "$1" "$2" "$COPILOT_AGENT_SESSION_ID" > "$MOCK_CAPTURE"
printf 'self-compact handoff receipt: proof-token\\n'
`,
  );
  await chmod(submitter, 0o755);

  const child = spawn(process.execPath, [extensionPath], {
    env: {
      ...process.env,
      MOCK_INPUT: input,
      MOCK_CAPTURE: capture,
      SELF_COMPACT_SUBMITTER: submitter,
    },
    stdio: ["ignore", "pipe", "pipe"],
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
  const invocation = await readFile(capture, "utf8").then(JSON.parse, () => null);
  await rm(root, { recursive: true, force: true });
  return { ...exit, stdout, stderr, invocation };
}

test("registers one private brief parameter and arms by tool-call identity", async () => {
  const brief =
    "Keep: active baton\n\nDrop: resolved detail\n\nAfter compaction: continue; do not compact again.";
  const outcome = await runExtension(brief);
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result, "self-compact handoff receipt: proof-token");
  assert.equal(registered.defer, "never");
  assert.deepEqual(registered.schema.required, ["brief"]);
  assert.equal(registered.schema.additionalProperties, false);
  assert.deepEqual(Object.keys(registered.schema.properties), ["brief"]);
  assert.deepEqual(outcome.invocation.args, ["--tool-call-id", "call-456"]);
  assert.equal(outcome.invocation.session, "session-123");
});

test("rejects malformed briefs before launching the submitter", async () => {
  const outcome = await runExtension(
    "Keep:\n\nDrop: detail\n\nAfter compaction: continue.",
  );
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result.resultType, "failure");
  assert.match(registered.result.textResultForLlm, /brief must be/);
  assert.equal(outcome.invocation, null);
});
