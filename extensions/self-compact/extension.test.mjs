import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const sourceExtension = join(
  dirname(fileURLToPath(import.meta.url)),
  "extension.mjs",
);

const goodBrief =
  "Keep: active baton\n\nDrop: resolved detail\n\nAfter compaction: continue; do not compact again.";

async function stageExtension() {
  const root = await mkdtemp(join(tmpdir(), "self compact extension "));
  const extensionDirectory = join(root, "extensions", "self-compact");
  const sdkDirectory = join(root, "node_modules", "@github", "copilot-sdk");
  await mkdir(extensionDirectory, { recursive: true });
  await mkdir(sdkDirectory, { recursive: true });
  await cp(sourceExtension, join(extensionDirectory, "extension.mjs"));
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
  return { root, extensionPath: join(extensionDirectory, "extension.mjs") };
}

async function runExtension(brief, { withSubmitter = true } = {}) {
  const { root, extensionPath } = await stageExtension();
  const submitter = join(root, "mock-submitter.mjs");
  const capture = join(root, "capture.json");
  const input = join(root, "input.txt");
  await writeFile(input, brief);
  await writeFile(
    submitter,
    `import {writeFileSync} from "node:fs";
writeFileSync(process.env.MOCK_CAPTURE, JSON.stringify({
  args: process.argv.slice(2),
  script: process.argv[1],
  runtime: process.execPath,
  session: process.env.COPILOT_AGENT_SESSION_ID,
}));
process.stdout.write("self-compact handoff receipt: proof-token\\nwatcher log: run.log\\n");
`,
  );

  const child = spawn(process.execPath, [extensionPath], {
    env: {
      ...process.env,
      MOCK_INPUT: input,
      MOCK_CAPTURE: capture,
      ...(withSubmitter ? { SELF_COMPACT_SUBMITTER: submitter } : {}),
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
  const invocation = await readFile(capture, "utf8").then(
    JSON.parse,
    () => null,
  );
  await rm(root, { recursive: true, force: true });
  return { ...exit, stdout, stderr, invocation, submitter };
}

test("arms the portable submitter through the current Node runtime", async () => {
  const outcome = await runExtension(goodBrief);
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(
    registered.result,
    "self-compact handoff receipt: proof-token\nwatcher log: run.log",
  );
  assert.equal(registered.defer, "never");
  assert.deepEqual(registered.schema.required, ["brief"]);
  assert.equal(registered.schema.additionalProperties, false);
  assert.deepEqual(Object.keys(registered.schema.properties), ["brief"]);
  assert.notEqual(outcome.invocation, null, "submitter was never launched");
  assert.deepEqual(outcome.invocation.args, ["--tool-call-id", "call-456"]);
  assert.equal(outcome.invocation.session, "session-123");
  assert.equal(outcome.invocation.runtime, process.execPath);
  assert.equal(outcome.invocation.script, outcome.submitter);
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

test("defaults to the Node submitter rather than a shell script", async () => {
  const outcome = await runExtension(goodBrief, { withSubmitter: false });
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result.resultType, "failure");
  const detail = registered.result.textResultForLlm;
  assert.match(detail, /submit-compact\.mjs/);
  assert.doesNotMatch(detail, /submit-compact\.sh/);
  assert.doesNotMatch(detail, /EFTYPE/);
});

test("does not treat the embedded extension host as the Node child runtime", async () => {
  const source = await readFile(sourceExtension, "utf8");
  assert.match(
    source,
    /const nodeBin = process\.env\.SELF_COMPACT_NODE_BIN \?\? "node";/,
  );
  assert.doesNotMatch(source, /execFileAsync\(\s*process\.execPath,/);
});
