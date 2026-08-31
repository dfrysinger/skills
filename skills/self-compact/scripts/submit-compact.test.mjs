import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { appendFileSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  LOCK_STATES,
  classifyAuthorization,
  classifyRequestOutcome,
  decodeRootEvents,
  lockPaths,
  pidIsLive,
  readEventTail,
  readTextOrNull,
  readTrimmedOrNull,
  runPaths,
} from "./resume-after-compact.mjs";
import { inspectLockForReclaim, runTokenFrom, scanCandidate } from "./submit-compact.mjs";

const scriptsDirectory = dirname(fileURLToPath(import.meta.url));
const submitter = join(scriptsDirectory, "submit-compact.mjs");
const verifierScript = join(scriptsDirectory, "resume-after-compact.mjs");
const submitWrapper = join(scriptsDirectory, "submit-compact.sh");
const resumeWrapper = join(scriptsDirectory, "resume-after-compact.sh");

const brief =
  "Keep: active baton\n\nDrop: resolved detail\n\nAfter compaction: continue the task; do not compact again.";
const continuationText = "Compaction done; resume, do not compact.";
const runToken = "0123abcd";

const fakeRequestSource = `import {
  appendFileSync,
  copyFileSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";

const mode = process.env.FAKE_REQUEST_MODE ?? "success";
const argv = process.argv.slice(2);
if (argv[0] !== "compact") process.exit(64);
const options = {};
for (let index = 1; index < argv.length; index += 2) {
  options[argv[index]] = argv[index + 1];
}
const target = options["--target-session"];
const instructionsPath = options["--instructions-file"];
const continuationPath = options["--continuation-file"];

let count = 0;
try {
  count = Number(readFileSync(process.env.FAKE_REQUEST_COUNT, "utf8").trim() || "0");
} catch {}
writeFileSync(process.env.FAKE_REQUEST_COUNT, String(count + 1));
copyFileSync(instructionsPath, process.env.FAKE_CAPTURED_INSTRUCTIONS);
copyFileSync(continuationPath, process.env.FAKE_CAPTURED_CONTINUATION);
writeFileSync(process.env.FAKE_CAPTURED_ARGUMENTS, JSON.stringify(options));

const workspacePath = process.env.FAKE_WORKSPACE;
const eventsPath = process.env.FAKE_EVENTS;
const appendEvent = (event) => {
  appendFileSync(eventsPath, JSON.stringify({ agentId: null, ...event }) + "\\n");
};

if (mode === "hang") {
  writeFileSync(process.env.FAKE_REQUEST_PID, String(process.pid));
  console.log("request: fake");
  setInterval(() => {}, 1000);
} else if (mode === "failed") {
  console.log("request: fake");
  console.log(JSON.stringify({ id: "fake", status: "failed", sessionId: target, error: "forced failure" }));
  process.exit(1);
} else if (mode === "timeout") {
  console.error("request: fake");
  process.exit(2);
} else if (mode === "preflight") {
  console.error("session-inbox-request: no fresh session-inbox instance");
  process.exit(64);
} else if (mode === "ambiguous-side-effect") {
  console.log("request: fake");
  console.log(
    JSON.stringify({
      id: "fake",
      status: "failed",
      sessionId: target,
      ambiguousSideEffect: true,
      error: "extension exited while executing",
    }),
  );
  process.exit(1);
} else {
  const instructions = readFileSync(instructionsPath, "utf8");
  const eventInstructions =
    mode === "wrong-token" ? instructions.slice(0, -8) + "deadbeef" : instructions;
  if (mode !== "no-event") {
    appendEvent({
      type: "session.compaction_complete",
      data: { success: true, customInstructions: eventInstructions, checkpointNumber: 2 },
    });
  }
  const workspace = readFileSync(workspacePath, "utf8").replace(
    /^summary_count: .*$/m,
    "summary_count: 2",
  );
  writeFileSync(workspacePath, workspace);
  const checkpoints = join(dirname(workspacePath), "checkpoints");
  if (mode !== "missing-checkpoint") {
    mkdirSync(checkpoints, { recursive: true });
    writeFileSync(join(checkpoints, "002-test.md"), "checkpoint\\n");
    if (mode === "duplicate-checkpoint") {
      writeFileSync(join(checkpoints, "002-other.md"), "checkpoint\\n");
    }
  }
  const continuation =
    mode === "wrong-continuation"
      ? "different continuation"
      : readFileSync(continuationPath, "utf8");
  const delivery =
    mode === "steering-continuation"
      ? "steering"
      : mode === "queued-continuation"
        ? "queued"
        : "idle";
  if (mode !== "continuation-failed" && mode !== "no-event") {
    appendEvent({ type: "user.message", data: { content: continuation, delivery } });
    if (mode === "duplicate-continuation") {
      appendEvent({ type: "user.message", data: { content: continuation, delivery } });
    }
  }
  const continuationAccepted = mode !== "continuation-failed";
  const failedReceipt = mode === "post-compact-receipt-failed";
  console.log("request: fake");
  console.log("receipt: fake");
  console.log(
    JSON.stringify({
      id: "fake",
      status: failedReceipt ? "failed" : "completed",
      sessionId: target,
      ...(failedReceipt ? { sideEffectCompleted: true } : {}),
      result: {
        compacted: true,
        tokensRemoved: 10,
        messagesRemoved: 2,
        continuationAccepted,
      },
    }),
  );
  process.exit(failedReceipt ? 1 : 0);
}
`;

function killPid(pid) {
  if (!Number.isInteger(pid) || pid <= 1) return;
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    // Already gone.
  }
}

async function deadPid() {
  const child = spawn(process.execPath, ["-e", "process.exit(0)"], { stdio: "ignore" });
  await new Promise((done) => child.on("exit", done));
  return child.pid;
}

async function livePid(t) {
  const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], {
    stdio: "ignore",
  });
  t.after(() => killPid(child.pid));
  return child.pid;
}

async function waitFor(probe, { timeout = 20000, interval = 20, label = "condition" } = {}) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    last = await probe();
    if (last) return last;
    await new Promise((done) => setTimeout(done, interval));
  }
  throw new Error(`timed out waiting for ${label}`);
}

async function waitForLog(log, pattern, options = {}) {
  return await waitFor(
    async () => {
      const text = (await readTextOrNull(log)) ?? "";
      return pattern.test(text) ? text : null;
    },
    { ...options, label: `${pattern} in ${log}` },
  );
}

async function createCase(t, name) {
  const root = await mkdtemp(join(tmpdir(), "self compact port "));
  const sessionDir = join(root, "session");
  const filesDir = join(sessionDir, "files");
  await mkdir(filesDir, { recursive: true });
  const workspace = join(sessionDir, "workspace.yaml");
  const events = join(sessionDir, "events.jsonl");
  await writeFile(workspace, `id: workspace-${name}\ncwd: ${process.cwd()}\nsummary_count: 1\n`);
  await writeFile(events, "");
  const draft = join(root, "draft");
  await writeFile(draft, "unsubmitted user draft\n");
  const requestCli = join(root, "fake-request.mjs");
  await writeFile(requestCli, fakeRequestSource);
  const context = {
    name,
    root,
    sessionDir,
    filesDir,
    workspace,
    events,
    draft,
    requestCli,
    lockDir: join(filesDir, "self-compact.lock"),
    requestCount: join(root, "request-count"),
    capturedInstructions: join(root, "captured-instructions"),
    capturedContinuation: join(root, "captured-continuation"),
    capturedArguments: join(root, "captured-arguments.json"),
    requestPid: join(root, "request-pid"),
    toolCallId: `call-self-compact-${name}`,
  };
  await writeFile(context.requestCount, "");
  t.after(async () => {
    for (const path of [
      join(context.lockDir, "watcher.pid"),
      join(context.lockDir, "submitter.pid"),
      context.requestPid,
    ]) {
      const text = await readTrimmedOrNull(path);
      if (text && /^\d+$/.test(text)) killPid(Number(text));
    }
    await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 50 });
  });
  return context;
}

function caseEnvironment(context, overrides = {}) {
  return {
    ...process.env,
    COPILOT_AGENT_SESSION_ID: "target-session",
    SELF_COMPACT_WORKSPACE: context.workspace,
    SELF_COMPACT_REQUEST_CLI: context.requestCli,
    SELF_COMPACT_NODE_BIN: process.execPath,
    SELF_COMPACT_RUN_TOKEN: runToken,
    SELF_COMPACT_SUBMIT_POLLS: "1",
    SELF_COMPACT_SUBMIT_POLL_SECONDS: "0.01",
    SELF_COMPACT_AUTH_WAIT_SECONDS: "10",
    SELF_COMPACT_POLL_SECONDS: "0.01",
    SELF_COMPACT_MAX_POLLS: "2000",
    SELF_COMPACT_REQUEST_TIMEOUT_SECONDS: "3",
    SELF_COMPACT_READY_POLL_SECONDS: "0.02",
    SELF_COMPACT_HANDOFF_POLL_SECONDS: "0.02",
    FAKE_EVENTS: context.events,
    FAKE_WORKSPACE: context.workspace,
    FAKE_REQUEST_COUNT: context.requestCount,
    FAKE_CAPTURED_INSTRUCTIONS: context.capturedInstructions,
    FAKE_CAPTURED_CONTINUATION: context.capturedContinuation,
    FAKE_CAPTURED_ARGUMENTS: context.capturedArguments,
    FAKE_REQUEST_PID: context.requestPid,
    ...overrides,
  };
}

function appendEvents(context, events) {
  appendFileSync(
    context.events,
    `${events.map((event) => JSON.stringify({ agentId: null, ...event })).join("\n")}\n`,
  );
}

function authorizingEvents(context, { mode = "canonical", callId = context.toolCallId, body = brief } = {}) {
  const requests = [
    {
      toolCallId: callId,
      name: mode === "wrong-tool" ? "bash" : "self_compact",
      arguments: { brief: body },
    },
  ];
  if (mode === "batched") {
    requests.push({ toolCallId: "other-call", name: "bash", arguments: { command: "true" } });
  }
  const events = [
    { type: "assistant.turn_start" },
    {
      type: "assistant.message",
      data: { content: mode === "visible-brief" ? body : "", toolRequests: requests },
    },
  ];
  if (mode === "interleaved") {
    events.splice(1, 0, { type: "user.message", data: { content: "interrupting draft" } });
  }
  events.push({
    type: "tool.execution_start",
    data: { toolCallId: callId, toolName: mode === "wrong-tool" ? "bash" : "self_compact" },
  });
  if (mode === "already-complete") {
    events.push({
      type: "tool.execution_complete",
      data: { toolCallId: callId, result: { content: "stale receipt" } },
    });
  }
  appendEvents(context, events);
}

function completeAuthorizingTurn(context, receiptContent, { callId = context.toolCallId, trailingActivity = false } = {}) {
  const events = [
    {
      type: "tool.execution_complete",
      data: { toolCallId: callId, result: { content: receiptContent } },
    },
    { type: "assistant.turn_end" },
  ];
  if (trailingActivity) {
    events.push({ type: "user.message", data: { content: "intervening activity" } });
  } else {
    events.push(
      { type: "assistant.turn_start" },
      { type: "assistant.message", data: { content: "", toolRequests: [] } },
      { type: "assistant.turn_end" },
    );
  }
  appendEvents(context, events);
}

function runSubmit(context, { callId = context.toolCallId, env = {} } = {}) {
  return new Promise((done, failed) => {
    const child = spawn(process.execPath, [submitter, "--tool-call-id", callId], {
      env: caseEnvironment(context, env),
      stdio: ["ignore", "pipe", "pipe"],
      cwd: context.root,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", failed);
    child.on("close", (code) => done({ code, stdout, stderr, pid: child.pid }));
  });
}

function receiptOf(stdout) {
  const match = /^self-compact handoff receipt: (.+)$/m.exec(stdout);
  return match ? match[1] : null;
}

function logOf(stdout) {
  const match = /^watcher log: (.+)$/m.exec(stdout);
  return match ? match[1] : null;
}

async function arm(context, options = {}) {
  const outcome = await runSubmit(context, options);
  assert.equal(outcome.code, 0, `${outcome.stdout}${outcome.stderr}`);
  const lockToken = receiptOf(outcome.stdout);
  const log = logOf(outcome.stdout);
  assert.ok(lockToken, "missing handoff receipt");
  assert.ok(log, "missing watcher log path");
  return { ...outcome, lockToken, log };
}

async function requestCount(context) {
  const text = (await readTextOrNull(context.requestCount)) ?? "";
  return text.trim() === "" ? 0 : Number(text.trim());
}

async function lockExists(context) {
  try {
    await stat(context.lockDir);
    return true;
  } catch {
    return false;
  }
}

async function lockState(context) {
  return await readTrimmedOrNull(join(context.lockDir, "state"));
}

test("verified compaction preserves the exact brief, token, checkpoint, and one continuation", async (t) => {
  const context = await createCase(t, "success");
  authorizingEvents(context);
  const armed = await arm(context);
  const submitterPid = Number(await readTrimmedOrNull(join(context.lockDir, "submitter.pid")));

  // The foreground helper is already gone; the detached verifier owns the run.
  await waitFor(async () => !pidIsLive(submitterPid), { label: "foreground exit" });
  assert.equal(await lockState(context), "verifier-owned");

  completeAuthorizingTurn(context, armed.stdout);
  const log = await waitForLog(
    armed.log,
    /verified token-bound compaction checkpoint 2 and one SDK continuation/,
  );

  assert.equal(
    await readFile(context.capturedInstructions, "utf8"),
    `${brief}\n\nSELF_COMPACT_RUN_TOKEN: ${runToken}`,
  );
  assert.equal(await readFile(context.capturedContinuation, "utf8"), continuationText);
  const args = JSON.parse(await readFile(context.capturedArguments, "utf8"));
  assert.equal(args["--target-session"], "target-session");
  assert.equal(args["--timeout"], "3");
  assert.equal(args["--dedupe-key"], `self-compact:target-session:${armed.lockToken}`);
  assert.equal(await requestCount(context), 1);
  assert.equal(await readFile(context.draft, "utf8"), "unsubmitted user draft\n");
  assert.match(log, /"status":"completed"/);
  assert.doesNotMatch(log, /active baton/);

  const trace = [...log.matchAll(/^self-compact state: (.+)$/gm)].map(([, name]) => name);
  assert.deepEqual(trace, LOCK_STATES);
  await waitFor(async () => !(await lockExists(context)), { label: "lock release" });
});

test("immediate steering delivery is a verified continuation", async (t) => {
  const context = await createCase(t, "steering");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "steering-continuation" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
  assert.equal(await requestCount(context), 1);
  await waitFor(async () => !(await lockExists(context)), { label: "lock release" });
});

test("queued continuation delivery retains the lock", async (t) => {
  const context = await createCase(t, "queued");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "queued-continuation" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /other root activity won the continuation race/);
  assert.equal(await lockExists(context), true);
  assert.equal(await lockState(context), "checkpoint-observed");
});

test("a duplicated continuation is a failure", async (t) => {
  const context = await createCase(t, "duplicate-continuation");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "duplicate-continuation" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /delivered the continuation more than once/);
  assert.equal(await lockExists(context), true);
});

test("a failed SDK continuation receipt retains the lock", async (t) => {
  const context = await createCase(t, "continuation-failed");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "continuation-failed" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /compact succeeded but the SDK continuation was not delivered/);
  assert.equal(await lockExists(context), true);
  assert.equal(await requestCount(context), 1);
});

test("earlier assistant prose does not block the current empty-content request", async (t) => {
  const context = await createCase(t, "prior-prose");
  appendEvents(context, [
    { type: "assistant.turn_start" },
    { type: "assistant.message", data: { content: "ordinary prior response", toolRequests: [] } },
    { type: "assistant.turn_end" },
  ]);
  authorizingEvents(context);
  const armed = await arm(context);
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
  assert.equal(await requestCount(context), 1);
});

for (const [name, mode] of [
  ["a malformed brief", "malformed"],
  ["a non-self_compact tool", "wrong-tool"],
  ["a brief duplicated into assistant prose", "visible-brief"],
  ["a batched helper request", "batched"],
  ["conflicting root activity inside the turn", "interleaved"],
  ["a tool call that already completed", "already-complete"],
]) {
  test(`${name} never creates a compact request`, async (t) => {
    const context = await createCase(t, `refuse-${mode}`);
    authorizingEvents(context, {
      mode,
      body: mode === "malformed" ? "Keep:\nDrop: x\nAfter compaction: do not compact again." : brief,
    });
    const outcome = await runSubmit(context);
    assert.notEqual(outcome.code, 0, outcome.stdout);
    assert.match(outcome.stderr, /current-turn authorization failed/);
    assert.equal(await requestCount(context), 0);
    assert.equal(await lockExists(context), false);
  });
}

test("a different tool-call identity is never bound", async (t) => {
  const context = await createCase(t, "wrong-call-id");
  authorizingEvents(context);
  const outcome = await runSubmit(context, { callId: "other-call-id" });
  assert.notEqual(outcome.code, 0);
  assert.equal(await requestCount(context), 0);
  assert.equal(await lockExists(context), false);
});

test("root activity after the authorizing turn cancels before publication", async (t) => {
  const context = await createCase(t, "post-turn-activity");
  authorizingEvents(context);
  const armed = await arm(context);
  completeAuthorizingTurn(context, armed.stdout, { trailingActivity: true });
  await waitForLog(armed.log, /new root activity followed helper completion/);
  assert.equal(await requestCount(context), 0);
  await waitFor(async () => !(await lockExists(context)), { label: "lock release" });
});

test("a live owner excludes a second run", async (t) => {
  const context = await createCase(t, "run-exclusion");
  await mkdir(context.lockDir, { recursive: true });
  const lock = lockPaths(context.lockDir);
  const owner = await livePid(t);
  await writeFile(lock.state, "verifier-owned\n");
  await writeFile(lock.token, "existing-token\n");
  await writeFile(lock.runId, "existing-run\n");
  await writeFile(lock.submitterPid, `${owner}\n`);
  await writeFile(lock.watcherPid, `${owner}\n`);
  authorizingEvents(context);
  const outcome = await runSubmit(context);
  assert.notEqual(outcome.code, 0);
  assert.match(outcome.stderr, /another or ambiguous self-compact run owns/);
  assert.equal(await requestCount(context), 0);
  assert.equal(await readTrimmedOrNull(lock.token), "existing-token");
});

test("a dead pre-attempt owner is reclaimed and the run proceeds", async (t) => {
  const context = await createCase(t, "reclaim-dead");
  await mkdir(context.lockDir, { recursive: true });
  const lock = lockPaths(context.lockDir);
  const gone = await deadPid();
  await writeFile(lock.state, "verifier-owned\n");
  await writeFile(lock.token, "stale-token\n");
  await writeFile(lock.runId, "stale-run\n");
  await writeFile(lock.submitterPid, `${gone}\n`);
  await writeFile(lock.watcherPid, `${gone}\n`);
  authorizingEvents(context);
  const armed = await arm(context);
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
  assert.equal(await requestCount(context), 1);
});

test("a publishing owner is never reclaimed even when its processes are dead", async (t) => {
  const context = await createCase(t, "no-reclaim-publishing");
  await mkdir(context.lockDir, { recursive: true });
  const lock = lockPaths(context.lockDir);
  const gone = await deadPid();
  await writeFile(lock.state, "publishing\n");
  await writeFile(lock.token, "stale-token\n");
  await writeFile(lock.runId, "stale-run\n");
  await writeFile(lock.submitterPid, `${gone}\n`);
  await writeFile(lock.watcherPid, `${gone}\n`);
  await writeFile(lock.publishing, JSON.stringify({ eventOffset: 0 }));
  authorizingEvents(context);
  const outcome = await runSubmit(context);
  assert.notEqual(outcome.code, 0);
  assert.match(outcome.stderr, /another or ambiguous self-compact run owns/);
  assert.equal(await requestCount(context), 0);
  assert.equal(await readTrimmedOrNull(lock.token), "stale-token");
});

test("recorded request metadata blocks reclaim of an otherwise dead lock", async (t) => {
  const context = await createCase(t, "no-reclaim-request");
  await mkdir(context.lockDir, { recursive: true });
  const lock = lockPaths(context.lockDir);
  const gone = await deadPid();
  await writeFile(lock.state, "authorized\n");
  await writeFile(lock.token, "stale-token\n");
  await writeFile(lock.runId, "stale-run\n");
  await writeFile(lock.submitterPid, `${gone}\n`);
  await writeFile(lock.watcherPid, `${gone}\n`);
  await writeFile(lock.request, JSON.stringify({ id: "fake" }));
  const inspection = await inspectLockForReclaim(context.lockDir);
  assert.equal(inspection.reclaimable, false);
  assert.match(inspection.reason, /request metadata/);
});

test("a verifier that never becomes ready retains a reclaimable lock", async (t) => {
  const context = await createCase(t, "verifier-startup-failure");
  const stub = join(context.root, "verifier-stub.mjs");
  await writeFile(stub, 'process.stderr.write("verifier failed to start\\n");\nprocess.exit(1);\n');
  authorizingEvents(context);
  const outcome = await runSubmit(context, { env: { SELF_COMPACT_VERIFIER: stub } });
  assert.notEqual(outcome.code, 0);
  assert.match(outcome.stderr, /detached SDK verifier did not become ready; lock retained at/);
  assert.equal(await lockExists(context), true);
  assert.equal(await lockState(context), "verifier-starting");
  assert.equal(await requestCount(context), 0);

  // The abandoned pre-attempt lock is safely reclaimed by the next run.
  const secondCall = `${context.toolCallId}-second`;
  authorizingEvents(context, { callId: secondCall });
  const armed = await arm(context, { callId: secondCall });
  completeAuthorizingTurn(context, armed.stdout, { callId: secondCall });
  await waitForLog(armed.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
  assert.equal(await requestCount(context), 1);
});

test("a readiness artifact with the wrong token never earns the handoff", async (t) => {
  const context = await createCase(t, "wrong-ready-token");
  const stub = join(context.root, "verifier-stub.mjs");
  await writeFile(
    stub,
    `import { readFileSync, writeFileSync } from "node:fs";
const run = JSON.parse(readFileSync(process.argv[2], "utf8"));
writeFileSync(process.env.FAKE_REQUEST_PID, String(process.pid));
writeFileSync(run.ready, "not-the-lock-token\\n");
setTimeout(() => {}, 30000);
`,
  );
  authorizingEvents(context);
  const outcome = await runSubmit(context, {
    env: { SELF_COMPACT_VERIFIER: stub, SELF_COMPACT_READY_POLLS: "5" },
  });
  assert.notEqual(outcome.code, 0);
  assert.match(outcome.stderr, /did not become ready/);
  const runId = await readTrimmedOrNull(join(context.lockDir, "run-id"));
  const artifacts = runPaths(context.filesDir, runId);
  assert.equal(await readTextOrNull(artifacts.handoff), null);
  assert.equal(await requestCount(context), 0);
  const cancelled = await readTextOrNull(join(context.lockDir, "cancelled"));
  assert.notEqual(cancelled, null);
});

test("the verifier refuses a run whose lock token does not own the lock", async (t) => {
  const context = await createCase(t, "token-mismatch");
  await mkdir(context.lockDir, { recursive: true });
  const lock = lockPaths(context.lockDir);
  await writeFile(lock.token, "owner-token\n");
  await writeFile(lock.state, "verifier-starting\n");
  const artifacts = runPaths(context.filesDir, "mismatch-run");
  await writeFile(artifacts.instructions, `${brief}\n\nSELF_COMPACT_RUN_TOKEN: ${runToken}`);
  await writeFile(artifacts.continuation, continuationText);
  const runFile = artifacts.runFile;
  await writeFile(
    runFile,
    JSON.stringify({
      version: 1,
      runId: "mismatch-run",
      runToken,
      lockToken: "intruder-token",
      toolCallId: context.toolCallId,
      targetSession: "target-session",
      workspace: context.workspace,
      events: context.events,
      checkpointsDir: join(context.sessionDir, "checkpoints"),
      filesDir: context.filesDir,
      lockDir: context.lockDir,
      baselineSummaryCount: 1,
      ready: artifacts.ready,
      handoff: artifacts.handoff,
      instructions: artifacts.instructions,
      continuation: artifacts.continuation,
      candidate: artifacts.candidate,
      runFile,
      log: artifacts.log,
      nodeBin: process.execPath,
      requestCli: context.requestCli,
      inboxRoot: context.root,
      requestTimeoutSeconds: 3,
      pollSeconds: 0.01,
      maxPolls: 10,
      authWaitSeconds: 1,
      authScanBytes: 65536,
      handoffPolls: 2,
      handoffPollSeconds: 0.01,
    }),
  );
  const outcome = await new Promise((done) => {
    const child = spawn(process.execPath, [verifierScript, runFile], {
      env: caseEnvironment(context),
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
    child.on("close", (code) => done({ code, stdout, stderr }));
  });
  assert.notEqual(outcome.code, 0);
  assert.match(outcome.stderr, /watcher lock token mismatch/);
  assert.equal(await readTrimmedOrNull(lock.token), "owner-token");
  assert.equal(await requestCount(context), 0);
});

test("the verifier refuses to run without a positive handoff", async (t) => {
  const context = await createCase(t, "no-handoff");
  await mkdir(context.lockDir, { recursive: true });
  const lock = lockPaths(context.lockDir);
  const artifacts = runPaths(context.filesDir, "no-handoff-run");
  await writeFile(lock.token, "handoff-token\n");
  await writeFile(lock.state, "verifier-starting\n");
  await writeFile(artifacts.instructions, `${brief}\n\nSELF_COMPACT_RUN_TOKEN: ${runToken}`);
  await writeFile(artifacts.continuation, continuationText);
  await writeFile(
    artifacts.runFile,
    JSON.stringify({
      version: 1,
      runId: "no-handoff-run",
      runToken,
      lockToken: "handoff-token",
      toolCallId: context.toolCallId,
      targetSession: "target-session",
      workspace: context.workspace,
      events: context.events,
      checkpointsDir: join(context.sessionDir, "checkpoints"),
      filesDir: context.filesDir,
      lockDir: context.lockDir,
      baselineSummaryCount: 1,
      ready: artifacts.ready,
      handoff: artifacts.handoff,
      instructions: artifacts.instructions,
      continuation: artifacts.continuation,
      candidate: artifacts.candidate,
      runFile: artifacts.runFile,
      log: artifacts.log,
      nodeBin: process.execPath,
      requestCli: context.requestCli,
      inboxRoot: context.root,
      requestTimeoutSeconds: 3,
      pollSeconds: 0.01,
      maxPolls: 10,
      authWaitSeconds: 1,
      authScanBytes: 65536,
      handoffPolls: 2,
      handoffPollSeconds: 0.01,
    }),
  );
  const outcome = await new Promise((done) => {
    const child = spawn(process.execPath, [verifierScript, artifacts.runFile], {
      env: caseEnvironment(context),
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stderr = "";
    let stdout = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("close", (code) => done({ code, stdout, stderr }));
  });
  assert.notEqual(outcome.code, 0);
  assert.match(outcome.stderr, /positive handoff was not established/);
  assert.match(outcome.stdout, /self-compact state: verifier-owned/);
  assert.equal(await requestCount(context), 0);
  assert.equal(await lockExists(context), false);
});

test("verifier death after handoff but before publishing is safely reclaimed", async (t) => {
  const context = await createCase(t, "verifier-death");
  authorizingEvents(context);
  const armed = await arm(context);
  const watcherPid = Number(
    await waitFor(async () => await readTrimmedOrNull(join(context.lockDir, "watcher.pid")), {
      label: "watcher pid",
    }),
  );
  killPid(watcherPid);
  await waitFor(async () => !pidIsLive(watcherPid), { label: "verifier death" });
  assert.equal(await lockState(context), "verifier-owned");
  assert.equal(await readTextOrNull(join(context.lockDir, "publish.json")), null);
  assert.equal(await requestCount(context), 0);

  completeAuthorizingTurn(context, armed.stdout);
  const secondCall = `${context.toolCallId}-second`;
  authorizingEvents(context, { callId: secondCall });
  const second = await arm(context, { callId: secondCall });
  completeAuthorizingTurn(context, second.stdout, { callId: secondCall });
  await waitForLog(second.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
  assert.equal(await requestCount(context), 1);
});

test("a crash at the publishing marker retains an unreclaimable lock", async (t) => {
  const context = await createCase(t, "publishing-crash");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "hang" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitFor(async () => (await lockState(context)) === "publishing", {
    label: "publishing state",
  });
  const watcherPid = Number(await readTrimmedOrNull(join(context.lockDir, "watcher.pid")));
  const requestPid = Number(
    await waitFor(async () => await readTrimmedOrNull(context.requestPid), {
      label: "request publisher pid",
    }),
  );
  killPid(watcherPid);
  killPid(requestPid);
  await waitFor(async () => !pidIsLive(watcherPid), { label: "verifier death" });

  const publish = JSON.parse(await readFile(join(context.lockDir, "publish.json"), "utf8"));
  assert.equal(publish.targetSession, "target-session");
  assert.equal(publish.lockToken, armed.lockToken);
  assert.equal(publish.dedupeKey, `self-compact:target-session:${armed.lockToken}`);
  assert.equal(typeof publish.eventOffset, "number");

  const inspection = await inspectLockForReclaim(context.lockDir);
  assert.equal(inspection.reclaimable, false);

  const secondCall = `${context.toolCallId}-second`;
  authorizingEvents(context, { callId: secondCall });
  const outcome = await runSubmit(context, { callId: secondCall });
  assert.notEqual(outcome.code, 0);
  assert.match(outcome.stderr, /another or ambiguous self-compact run owns/);
  assert.equal(await requestCount(context), 1);
});

test("a definitively failed request releases the lock", async (t) => {
  const context = await createCase(t, "failed-request");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "failed" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /session-inbox reported a failed compact request/);
  await waitFor(async () => !(await lockExists(context)), { label: "lock release" });
  assert.equal(await requestCount(context), 1);
});

test("an ambiguous request timeout retains the lock", async (t) => {
  const context = await createCase(t, "timeout");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "timeout" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /outcome is ambiguous \(status 2\); lock retained/);
  assert.equal(await lockExists(context), true);
  assert.equal(await requestCount(context), 1);
  const outcome = JSON.parse(await readFile(join(context.lockDir, "outcome.json"), "utf8"));
  assert.equal(outcome.outcome, "retained");
  assert.equal(outcome.state, "request-published");
  const request = JSON.parse(await readFile(join(context.lockDir, "request.json"), "utf8"));
  assert.equal(request.id, "fake");
  assert.equal(request.dedupeKey, `self-compact:target-session:${armed.lockToken}`);
  assert.match(request.completed, /completed[\\/]fake\.json$/);
});

test("a pre-publication rejection releases the lock", async (t) => {
  const context = await createCase(t, "preflight");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "preflight" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /rejected the compact request before publication/);
  await waitFor(async () => !(await lockExists(context)), { label: "lock release" });
  assert.equal(await requestCount(context), 1);
});

test("an ambiguous side effect retains the lock", async (t) => {
  const context = await createCase(t, "ambiguous-side-effect");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "ambiguous-side-effect" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /extension exited during compact execution/);
  assert.equal(await lockExists(context), true);
  assert.equal(await requestCount(context), 1);
});

test("a failed receipt whose side effect completed still verifies", async (t) => {
  const context = await createCase(t, "post-compact-receipt-failed");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "post-compact-receipt-failed" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
  await waitFor(async () => !(await lockExists(context)), { label: "lock release" });
  assert.equal(await requestCount(context), 1);
});

test("a completion bound to another token is not this run's compact", async (t) => {
  const context = await createCase(t, "wrong-token");
  authorizingEvents(context);
  const armed = await arm(context, {
    env: { FAKE_REQUEST_MODE: "wrong-token", SELF_COMPACT_MAX_POLLS: "20" },
  });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /matching token-bound compaction completion was not observed/);
  assert.equal(await lockExists(context), true);
});

test("a stale matching completion before the publish boundary is ignored", async (t) => {
  const context = await createCase(t, "stale-completion");
  appendEvents(context, [
    {
      type: "session.compaction_complete",
      data: {
        success: true,
        customInstructions: `${brief}\n\nSELF_COMPACT_RUN_TOKEN: ${runToken}`,
        checkpointNumber: 2,
      },
    },
  ]);
  authorizingEvents(context);
  const armed = await arm(context, {
    env: { FAKE_REQUEST_MODE: "no-event", SELF_COMPACT_MAX_POLLS: "20" },
  });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /matching token-bound compaction completion was not observed/);
  assert.equal(await lockExists(context), true);
});

test("a missing checkpoint file is not proof of compaction", async (t) => {
  const context = await createCase(t, "missing-checkpoint");
  authorizingEvents(context);
  const armed = await arm(context, {
    env: { FAKE_REQUEST_MODE: "missing-checkpoint", SELF_COMPACT_MAX_POLLS: "20" },
  });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /did not produce exactly one checkpoint file/);
  assert.equal(await lockExists(context), true);
});

test("two checkpoint files for one number are not proof of compaction", async (t) => {
  const context = await createCase(t, "duplicate-checkpoint");
  authorizingEvents(context);
  const armed = await arm(context, {
    env: { FAKE_REQUEST_MODE: "duplicate-checkpoint", SELF_COMPACT_MAX_POLLS: "20" },
  });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /did not produce exactly one checkpoint file/);
  assert.equal(await lockExists(context), true);
});

test("a different continuation message fails the run", async (t) => {
  const context = await createCase(t, "wrong-continuation");
  authorizingEvents(context);
  const armed = await arm(context, { env: { FAKE_REQUEST_MODE: "wrong-continuation" } });
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /other root activity won the continuation race/);
  assert.equal(await lockExists(context), true);
});

test("a replayed tool call after a verified run publishes nothing", async (t) => {
  const context = await createCase(t, "replay");
  authorizingEvents(context);
  const armed = await arm(context);
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
  await waitFor(async () => !(await lockExists(context)), { label: "lock release" });

  const replay = await runSubmit(context);
  assert.notEqual(replay.code, 0);
  assert.match(replay.stderr, /current-turn authorization failed/);
  assert.equal(await requestCount(context), 1);
  assert.equal(await lockExists(context), false);
});

test("durable run metadata uses absolute platform paths", async (t) => {
  const context = await createCase(t, "paths");
  authorizingEvents(context);
  const armed = await arm(context);
  const runId = await readTrimmedOrNull(join(context.lockDir, "run-id"));
  const artifacts = runPaths(context.filesDir, runId);
  const run = JSON.parse(await readFile(artifacts.runFile, "utf8"));
  for (const key of ["workspace", "events", "lockDir", "instructions", "continuation", "log"]) {
    assert.equal(run[key], run[key].trim());
    if (process.platform === "win32") {
      assert.match(run[key], /^[A-Za-z]:\\/, `${key} is not an absolute Windows path`);
    } else {
      assert.match(run[key], /^\//, `${key} is not an absolute path`);
    }
  }
  assert.match(run.log, / /, "the fixture path contains a space");
  assert.equal(run.lockToken, armed.lockToken);
  assert.equal(run.runToken, runToken);
  completeAuthorizingTurn(context, armed.stdout);
  await waitForLog(armed.log, /verified token-bound compaction checkpoint 2 and one SDK continuation/);
});

test("authorization classification refuses malformed and unaligned event windows", () => {
  assert.deepEqual(classifyAuthorization({ boundaryExceeded: true }, { toolCallId: "a", receipt: "r" }), {
    state: "cancel",
    reason: "authorization boundary exceeds event tail",
  });
  assert.deepEqual(classifyAuthorization({ partial: true }, { toolCallId: "a", receipt: "r" }), {
    state: "wait",
  });
  assert.deepEqual(
    classifyAuthorization({ text: "{not json}\n" }, { toolCallId: "a", receipt: "r" }),
    { state: "cancel", reason: "malformed authorization event JSON" },
  );
  const duplicated = [
    { type: "tool.execution_start", data: { toolCallId: "a", toolName: "self_compact" } },
    { type: "tool.execution_start", data: { toolCallId: "a", toolName: "self_compact" } },
  ]
    .map((event) => JSON.stringify(event))
    .join("\n");
  assert.deepEqual(classifyAuthorization({ text: `${duplicated}\n` }, { toolCallId: "a", receipt: "r" }), {
    state: "cancel",
    reason: "duplicate helper execution identity",
  });
});

test("request classification separates publication, failure, and ambiguity", () => {
  assert.deepEqual(
    classifyRequestOutcome({ status: 64, output: "no instance\n", targetSession: "s" }),
    {
      outcome: "rejected",
      published: false,
      reason: "session-inbox rejected the compact request before publication",
      release: true,
    },
  );
  const failed = classifyRequestOutcome({
    status: 1,
    output: `request: p\n${JSON.stringify({ status: "failed", sessionId: "s" })}\n`,
    targetSession: "s",
  });
  assert.equal(failed.outcome, "failed");
  assert.equal(failed.release, true);
  const ambiguous = classifyRequestOutcome({
    status: 1,
    output: `request: p\n${JSON.stringify({ status: "failed", sessionId: "s", ambiguousSideEffect: true })}\n`,
    targetSession: "s",
  });
  assert.equal(ambiguous.outcome, "ambiguous");
  assert.equal(ambiguous.release, false);
  const timedOut = classifyRequestOutcome({ status: 2, output: "request: p\n", targetSession: "s" });
  assert.equal(timedOut.outcome, "ambiguous");
  assert.equal(timedOut.release, false);
  const unmatched = classifyRequestOutcome({
    status: 0,
    output: `request: p\n${JSON.stringify({ status: "completed", sessionId: "other" })}\n`,
    targetSession: "s",
  });
  assert.equal(unmatched.outcome, "unmatched");
  const completed = classifyRequestOutcome({
    status: 0,
    output: `request: p\n${JSON.stringify({
      status: "completed",
      sessionId: "s",
      result: { compacted: true, continuationAccepted: false },
    })}\n`,
    targetSession: "s",
  });
  assert.equal(completed.outcome, "completed");
  assert.equal(completed.continuation, "failed");
});

test("the run token is deterministic and always eight lowercase hex characters", () => {
  const first = runTokenFrom({}, 1_700_000_000_000, 4242, "20260831T000000Z");
  const second = runTokenFrom({}, 1_700_000_000_000, 4242, "20260831T000000Z");
  assert.equal(first, second);
  assert.match(first, /^[0-9a-f]{8}$/);
  assert.equal(runTokenFrom({ SELF_COMPACT_RUN_TOKEN: "0123abcd" }), "0123abcd");
  assert.throws(() => runTokenFrom({ SELF_COMPACT_RUN_TOKEN: "NOTHEX" }), /eight lowercase hex/);
});

test("event tails drop partial leading lines and refuse partial trailing lines", async (t) => {
  const context = await createCase(t, "tail");
  await writeFile(context.events, '{"type":"a"}\n{"type":"b"}\n{"type":"c"}');
  const partial = await readEventTail(context.events, 1_048_576);
  assert.equal(partial.partial, true);
  await writeFile(context.events, '{"type":"a"}\n{"type":"b"}\n');
  const whole = await readEventTail(context.events, 1_048_576);
  assert.equal(decodeRootEvents(whole.text).length, 2);
  const windowed = await readEventTail(context.events, 65_536);
  assert.equal(decodeRootEvents(windowed.text).length, 2);
});

test("subagent events never authorize a root compaction", async (t) => {
  const context = await createCase(t, "subagent");
  appendFileSync(
    context.events,
    `${JSON.stringify({
      agentId: "sub-1",
      type: "assistant.message",
      data: {
        content: "",
        toolRequests: [
          { toolCallId: context.toolCallId, name: "self_compact", arguments: { brief } },
        ],
      },
    })}\n`,
  );
  const tail = await readEventTail(context.events, 1_048_576);
  assert.equal(decodeRootEvents(tail.text).length, 0);
  await assert.rejects(
    scanCandidate([context.workspace], context.toolCallId, 1_048_576),
    /could not bind one running canonical self-compact helper/,
  );
});

test("the shell entry points are thin Node delegators", async () => {
  for (const [wrapper, target] of [
    [submitWrapper, "submit-compact.mjs"],
    [resumeWrapper, "resume-after-compact.mjs"],
  ]) {
    const text = await readFile(wrapper, "utf8");
    assert.match(text, new RegExp(`exec [^\\n]*${target.replace(".", "\\.")}[^\\n]*"\\$@"`));
    assert.doesNotMatch(text, /perl|awk|JSON::PP|nohup/);
    assert.ok(
      text.split("\n").filter((line) => line.trim() && !line.trim().startsWith("#")).length <= 12,
      `${wrapper} is not a thin wrapper`,
    );
  }
});
