import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmod,
  cp,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const sourceExtension = join(dirname(fileURLToPath(import.meta.url)), "extension.mjs");
const sourceDiagnostics = join(
  dirname(fileURLToPath(import.meta.url)),
  "diagnostics.mjs",
);
const sourceIdentity = join(
  dirname(fileURLToPath(import.meta.url)),
  "session-identity.mjs",
);

async function waitFor(read, label, attempts = 300) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const value = await read();
      if (value !== undefined) return value;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(`timed out waiting for ${label}`, { cause: lastError });
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function writeState(path, value) {
  const temporary = `${path}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value)}\n`);
  await rename(temporary, path);
}

function fingerprint(request) {
  return createHash("sha256")
    .update(
      JSON.stringify({
        kind: request.kind,
        prompt: request.prompt,
        mode: request.mode,
        agentMode: request.agentMode,
        customInstructions: request.customInstructions,
        continuationPrompt: request.continuationPrompt,
      }),
    )
    .digest("hex");
}

async function createHarness(initialState = {}) {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-extension-"));
  const inbox = join(root, "inbox");
  const statePath = join(root, "state.json");
  const callsPath = join(root, "calls.jsonl");
  const extensionPath = join(root, "extension.mjs");
  const diagnosticsPath = join(root, "diagnostics.mjs");
  const identityPath = join(root, "session-identity.mjs");
  const sdkDir = join(root, "node_modules", "@github", "copilot-sdk");
  await mkdir(sdkDir, { recursive: true });
  await cp(sourceExtension, extensionPath);
  await cp(sourceDiagnostics, diagnosticsPath);
  await cp(sourceIdentity, identityPath);
  await writeState(statePath, {
    processing: false,
    active: false,
    pending: 0,
    delivery: "idle",
    idleCounter: 0,
    sessionName: "hotel",
    ...initialState,
  });
  await writeFile(callsPath, "");
  await writeFile(
    join(sdkDir, "package.json"),
    `${JSON.stringify({
      name: "@github/copilot-sdk",
      type: "module",
      exports: { "./extension": "./extension.mjs" },
    })}\n`,
  );
  await writeFile(
    join(sdkDir, "extension.mjs"),
    `
import { appendFileSync, chmodSync, readFileSync } from "node:fs";

const listeners = new Map();
const state = () => JSON.parse(readFileSync(process.env.MOCK_STATE, "utf8"));
const record = (kind, value) =>
  appendFileSync(process.env.MOCK_CALLS, JSON.stringify({kind, value}) + "\\n");
const emit = (name, event = {}) => {
  for (const listener of listeners.get(name) ?? []) listener(event);
};
let idleCounter = state().idleCounter;
setInterval(() => {
  const current = state().idleCounter;
  if (current !== idleCounter) {
    idleCounter = current;
    emit("session.idle", {type: "session.idle", data: {}});
  }
}, 20);

export async function joinSession() {
  if (state().rejectJoin) {
    throw new Error("mock SDK join failed");
  }
  return {
    sessionId: "test-session",
    on(name, listener) {
      const group = listeners.get(name) ?? new Set();
      group.add(listener);
      listeners.set(name, group);
      return () => group.delete(listener);
    },
    async send(options) {
      record("send", options);
      const current = state();
      if (current.rejectSendAfterRecord) {
        throw new Error("mock transport lost the accepted send response");
      }
      if (!current.suppressDelivery) {
        queueMicrotask(() => emit("user.message", {
          type: "user.message",
          data: {content: options.prompt, delivery: current.delivery},
        }));
      }
      return "message-" + Date.now();
    },
    rpc: {
      metadata: {
        async snapshot() {
          return {workspace: {id: "test-session", name: state().sessionName}};
        },
        async isProcessing() {
          return {processing: state().processing};
        },
        async activity() {
          return {hasActiveWork: state().active};
        },
      },
      queue: {
        async pendingItems() {
          return {items: Array.from({length: state().pending}, (_, index) => ({index}))};
        },
      },
      history: {
        async compact(options) {
          record("compact", options);
          const current = state();
          if (current.breakDedupeWrite) {
            chmodSync(process.env.MOCK_DEDUPE_DIR, 0o500);
          }
          return {success: true, tokensRemoved: 11, messagesRemoved: 3};
        },
      },
      commands: {
        async enqueue(options) {
          record("command", options);
          if (state().rejectCommandAfterRecord) {
            throw new Error("mock transport lost the accepted command response");
          }
          if (state().exitOnEnqueue) process.exit(0);
          return {queued: true};
        },
      },
    },
  };
}
`,
  );
  const child = spawn(process.execPath, [extensionPath], {
    env: {
      ...process.env,
      COPILOT_SESSION_INBOX_DIR: inbox,
      MOCK_STATE: statePath,
      MOCK_CALLS: callsPath,
      MOCK_DEDUPE_DIR: join(inbox, "dedupe"),
      COPILOT_SESSION_INBOX_CONFIRM_TIMEOUT_MS: "100",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const exit = new Promise((resolve) => {
    child.on("exit", (code, signal) => resolve({ code, signal, stderr }));
  });

  const heartbeat = initialState.rejectJoin
    ? undefined
    : await waitFor(async () => {
        const instances = join(inbox, "instances");
        const names = await readdir(instances);
        const name = names.find((entry) => entry.endsWith(".json"));
        return name ? readJson(join(instances, name)) : undefined;
      }, "extension heartbeat");

  async function setState(patch) {
    await writeState(statePath, { ...(await readJson(statePath)), ...patch });
  }

  async function request(id, value) {
    const pending = join(inbox, "pending");
    await mkdir(pending, { recursive: true });
    await writeFile(
      join(pending, `${id}.json`),
      `${JSON.stringify({
        id,
        createdAt: new Date().toISOString(),
        target: {
          sessionId: heartbeat.sessionId,
          generation: heartbeat.generation,
        },
        ...value,
      })}\n`,
    );
  }

  async function receipt(directory, id) {
    return waitFor(
      async () => {
        try {
          return await readJson(join(inbox, directory, `${id}.json`));
        } catch (error) {
          if (error?.code === "ENOENT") return undefined;
          throw error;
        }
      },
      `${directory} receipt for ${id}`,
    );
  }

  async function calls() {
    return (await readFile(callsPath, "utf8"))
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  }

  async function diagnosticEntries() {
    const directory = join(inbox, "logs");
    const names = await readdir(directory);
    const entries = [];
    for (const name of names) {
      const content = await readFile(join(directory, name), "utf8");
      entries.push(
        ...content
          .trim()
          .split("\n")
          .filter(Boolean)
          .map((line) => JSON.parse(line)),
      );
    }
    return entries;
  }

  async function stop() {
    if (child.exitCode === null) child.kill("SIGTERM");
    await exit;
    await chmod(join(inbox, "dedupe"), 0o700).catch(() => {});
    await rm(root, { recursive: true, force: true });
  }

  return {
    root,
    inbox,
    child,
    exit,
    heartbeat,
    request,
    receipt,
    calls,
    diagnosticEntries,
    setState,
    stop,
  };
}

test("extension startup failures are persisted before session join", async () => {
  const harness = await createHarness({ rejectJoin: true });
  try {
    const result = await harness.exit;
    assert.notEqual(result.code, 0);
    const diagnostics = await harness.diagnosticEntries();
    const failure = diagnostics.find(
      (entry) => entry.event === "extension.start_failed",
    );
    assert.equal(failure.phase, "joinSession");
    assert.equal(failure.error.message, "mock SDK join failed");
  } finally {
    await harness.stop();
  }
});

test("recipient extension gates delivery, deduplicates, and preserves compact phase state", async () => {
  const harness = await createHarness();
  try {
    assert.equal(harness.heartbeat.sessionName, "hotel");
    await new Promise((resolve) => setTimeout(resolve, 2_200));

    await harness.request("idle-send", {
      kind: "send",
      prompt: "idle prompt",
      mode: "immediate",
    });
    const idleReceipt = await harness.receipt("completed", "idle-send");
    assert.equal(idleReceipt.result.delivery, "idle");

    await harness.setState({ idleCounter: 1 });
    await new Promise((resolve) => setTimeout(resolve, 350));
    await harness.setState({ pending: 1 });
    await harness.request("gate-deferred", {
      kind: "send",
      prompt: "gate-deferred prompt",
      mode: "immediate",
    });
    await new Promise((resolve) => setTimeout(resolve, 700));
    await harness.setState({ pending: 0, idleCounter: 2 });
    await harness.receipt("completed", "gate-deferred");

    await harness.setState({ processing: true });
    await harness.request("busy-send", {
      kind: "send",
      prompt: "deferred prompt",
      mode: "immediate",
    });
    await new Promise((resolve) => setTimeout(resolve, 300));
    await assert.rejects(readFile(join(harness.inbox, "completed", "busy-send.json")), {
      code: "ENOENT",
    });
    await harness.setState({ processing: false, idleCounter: 3 });
    assert.equal((await harness.receipt("completed", "busy-send")).result.delivery, "idle");

    await harness.request("dedupe-first", {
      kind: "send",
      prompt: "one-shot prompt",
      mode: "immediate",
      dedupeKey: "one-shot",
    });
    await harness.receipt("completed", "dedupe-first");
    await harness.setState({ idleCounter: 4 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("dedupe-second", {
      kind: "send",
      prompt: "one-shot prompt",
      mode: "immediate",
      dedupeKey: "one-shot",
    });
    const duplicate = await harness.receipt("completed", "dedupe-second");
    assert.equal(duplicate.deduplicated, true);
    assert.equal(
      (await harness.calls()).filter(
        (call) => call.kind === "send" && call.value.prompt === "one-shot prompt",
      ).length,
      1,
    );
    await harness.setState({ delivery: "steering", idleCounter: 5 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("non-idle-send", {
      kind: "send",
      prompt: "non-idle one-shot",
      mode: "immediate",
      dedupeKey: "non-idle-one-shot",
    });
    const nonIdle = await harness.receipt("completed", "non-idle-send");
    assert.equal(nonIdle.result.delivery, "steering");
    assert.equal(nonIdle.result.idleDelivery, false);
    await harness.setState({ delivery: "idle", idleCounter: 6 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("non-idle-retry", {
      kind: "send",
      prompt: "non-idle one-shot",
      mode: "immediate",
      dedupeKey: "non-idle-one-shot",
    });
    const nonIdleRetry = await harness.receipt("completed", "non-idle-retry");
    assert.equal(nonIdleRetry.deduplicated, true);
    assert.equal(nonIdleRetry.result.delivery, "steering");
    assert.equal(
      (await harness.calls()).filter(
        (call) => call.kind === "send" && call.value.prompt === "non-idle one-shot",
      ).length,
      1,
    );
    await harness.setState({ idleCounter: 7 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("dedupe-conflict", {
      kind: "send",
      prompt: "different payload",
      mode: "immediate",
      dedupeKey: "non-idle-one-shot",
    });
    const conflict = await harness.receipt("failed", "dedupe-conflict");
    assert.match(conflict.error, /dedupe key was reused/);
    assert.equal(
      (await harness.calls()).filter(
        (call) => call.kind === "send" && call.value.prompt === "different payload",
      ).length,
      0,
    );

    await harness.setState({ suppressDelivery: true, idleCounter: 8 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("unconfirmed-send", {
      kind: "send",
      prompt: "accepted without event",
      mode: "immediate",
      dedupeKey: "unconfirmed-one-shot",
    });
    const unconfirmed = await harness.receipt("completed", "unconfirmed-send");
    assert.equal(unconfirmed.result.delivery, "unconfirmed");
    assert.equal(unconfirmed.result.idleDelivery, false);
    await harness.setState({ suppressDelivery: false, idleCounter: 9 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("unconfirmed-retry", {
      kind: "send",
      prompt: "accepted without event",
      mode: "immediate",
      dedupeKey: "unconfirmed-one-shot",
    });
    const unconfirmedRetry = await harness.receipt(
      "completed",
      "unconfirmed-retry",
    );
    assert.equal(unconfirmedRetry.deduplicated, true);
    assert.equal(unconfirmedRetry.result.delivery, "unconfirmed");
    assert.equal(
      (await harness.calls()).filter(
        (call) => call.kind === "send" && call.value.prompt === "accepted without event",
      ).length,
      1,
    );

    await harness.setState({ rejectSendAfterRecord: true, idleCounter: 10 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("ambiguous-send", {
      kind: "send",
      prompt: "accepted then rejected",
      mode: "immediate",
      dedupeKey: "ambiguous-one-shot",
    });
    const ambiguousSend = await harness.receipt("failed", "ambiguous-send");
    assert.equal(ambiguousSend.ambiguousSideEffect, true);
    await harness.setState({ rejectSendAfterRecord: false, idleCounter: 11 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("ambiguous-send-retry", {
      kind: "send",
      prompt: "accepted then rejected",
      mode: "immediate",
      dedupeKey: "ambiguous-one-shot",
    });
    assert.equal(
      (await harness.receipt("failed", "ambiguous-send-retry")).ambiguousSideEffect,
      true,
    );
    assert.equal(
      (await harness.calls()).filter(
        (call) => call.kind === "send" && call.value.prompt === "accepted then rejected",
      ).length,
      1,
    );

    await harness.setState({ delivery: "steering", idleCounter: 12 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("compact-partial", {
      kind: "compact",
      customInstructions: "compact proof",
      continuationPrompt: "resume proof",
    });
    const compactPartial = await harness.receipt("completed", "compact-partial");
    assert.equal(compactPartial.result.compacted, true);
    assert.equal(compactPartial.result.continuationDelivered, false);
    assert.equal(compactPartial.result.continuationDelivery, "steering");
    assert.match(compactPartial.result.continuationError, /instead of idle/);

    await harness.setState({
      delivery: "idle",
      breakDedupeWrite: true,
      idleCounter: 13,
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("compact-receipt-failure", {
      kind: "compact",
      customInstructions: "receipt failure proof",
      dedupeKey: "break-dedupe",
    });
    const failedReceipt = await harness.receipt("failed", "compact-receipt-failure");
    assert.equal(failedReceipt.sideEffectCompleted, true);
    assert.equal(failedReceipt.result.compacted, true);
    await harness.setState({ idleCounter: 14 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("compact-receipt-blocked-retry", {
      kind: "compact",
      customInstructions: "receipt failure proof",
      dedupeKey: "break-dedupe",
    });
    assert.match(
      (await harness.receipt("failed", "compact-receipt-blocked-retry")).error,
      /unfinished prior request/,
    );
    assert.equal(
      (await harness.calls()).filter(
        (call) =>
          call.kind === "compact" &&
          call.value.customInstructions === "receipt failure proof",
      ).length,
      1,
    );
    await chmod(join(harness.inbox, "dedupe"), 0o700);
    await harness.setState({ breakDedupeWrite: false });
    const recoveredReceipt = await harness.receipt(
      "completed",
      "compact-receipt-failure",
    );
    assert.equal(recoveredReceipt.recovered, true);
    await harness.setState({ idleCounter: 15 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("compact-receipt-retry", {
      kind: "compact",
      customInstructions: "receipt failure proof",
      dedupeKey: "break-dedupe",
    });
    assert.equal(
      (await harness.receipt("completed", "compact-receipt-retry")).deduplicated,
      true,
    );
    assert.equal(
      (await harness.calls()).filter(
        (call) =>
          call.kind === "compact" &&
          call.value.customInstructions === "receipt failure proof",
      ).length,
      1,
    );
    const diagnostics = await harness.diagnosticEntries();
    assert.ok(diagnostics.some((entry) => entry.event === "extension.started"));
    assert.ok(diagnostics.some((entry) => entry.event === "request.completed"));
    assert.ok(diagnostics.some((entry) => entry.event === "request.failed"));
    assert.ok(diagnostics.some((entry) => entry.event === "sdk.send.unconfirmed"));
    assert.ok(
      diagnostics.some(
        (entry) =>
          entry.event === "request.deferred" &&
          entry.requestId === "gate-deferred" &&
          entry.idleReady === true &&
          entry.pendingQueueItems === 1,
      ),
    );
    const serializedDiagnostics = JSON.stringify(diagnostics);
    assert.doesNotMatch(serializedDiagnostics, /idle prompt/);
    assert.doesNotMatch(serializedDiagnostics, /receipt failure proof/);
  } finally {
    await harness.stop();
  }
});

test("new-session marker survives extension teardown before its receipt", async () => {
  const harness = await createHarness({ exitOnEnqueue: true });
  try {
    await new Promise((resolve) => setTimeout(resolve, 2_200));
    await harness.request("rotate-without-receipt", {
      kind: "new-session",
      prompt: "seed prompt",
    });

    const result = await harness.exit;
    assert.equal(result.code, 0, result.stderr);
    const marker = await readJson(
      join(harness.inbox, "commands", "rotate-without-receipt.json"),
    );
    assert.equal(marker.requestId, "rotate-without-receipt");
    assert.equal(marker.sessionId, "test-session");
    assert.match(marker.promptSha256, /^[0-9a-f]{64}$/);
    await assert.rejects(
      readFile(join(harness.inbox, "completed", "rotate-without-receipt.json")),
      { code: "ENOENT" },
    );
  } finally {
    await harness.stop();
  }
});

test("new-session marker survives an ambiguous enqueue rejection", async () => {
  const harness = await createHarness({ rejectCommandAfterRecord: true });
  try {
    await new Promise((resolve) => setTimeout(resolve, 2_200));
    await harness.request("rotate-ambiguous", {
      kind: "new-session",
      prompt: "ambiguous seed",
    });

    const receipt = await harness.receipt("failed", "rotate-ambiguous");
    assert.equal(receipt.ambiguousSideEffect, true);
    const marker = await readJson(
      join(harness.inbox, "commands", "rotate-ambiguous.json"),
    );
    assert.equal(marker.requestId, "rotate-ambiguous");
    assert.equal(marker.sessionId, "test-session");
    assert.match(marker.promptSha256, /^[0-9a-f]{64}$/);
  } finally {
    await harness.stop();
  }
});

test("a replacement extension recovers staged claims without duplicating ambiguous work", async () => {
  const harness = await createHarness();
  try {
    const processing = join(harness.inbox, "processing");
    const pending = join(harness.inbox, "pending");
    await mkdir(processing, { recursive: true });
    const pendingRequest = {
      id: "pending-rebind",
      target: { sessionId: "test-session", generation: "dead-generation" },
      kind: "send",
      prompt: "recover pending",
      mode: "immediate",
    };
    const safeRequest = {
      id: "safe-requeue",
      target: { sessionId: "test-session", generation: "dead-generation" },
      kind: "send",
      prompt: "recover safely",
      mode: "immediate",
    };
    const executedRequest = {
      id: "executed-recovery",
      target: { sessionId: "retired-session", generation: "dead-generation" },
      kind: "send",
      prompt: "already delivered",
      mode: "immediate",
      dedupeKey: "executed-key",
    };
    const ambiguousRequest = {
      id: "ambiguous-recovery",
      target: { sessionId: "retired-session", generation: "dead-generation" },
      kind: "compact",
      customInstructions: "ambiguous compact",
    };
    const foreignClaimedRequest = {
      id: "foreign-claimed",
      target: { sessionId: "other-session", generation: "dead-generation" },
      kind: "send",
      prompt: "belongs elsewhere",
      mode: "immediate",
    };
    await writeFile(
      join(pending, "pending-rebind.json"),
      `${JSON.stringify(pendingRequest)}\n`,
    );
    for (const request of [
      safeRequest,
      executedRequest,
      ambiguousRequest,
      foreignClaimedRequest,
    ]) {
      await writeFile(
        join(processing, `${request.id}.json`),
        `${JSON.stringify(request)}\n`,
      );
    }
    await writeFile(
      join(processing, "safe-requeue.json.stage"),
      `${JSON.stringify({
        ownerGeneration: "dead-generation",
        stage: "claimed",
        fingerprint: fingerprint(safeRequest),
      })}\n`,
    );
    await writeFile(
      join(processing, "executed-recovery.json.stage"),
      `${JSON.stringify({
        ownerGeneration: "dead-generation",
        stage: "executed",
        fingerprint: fingerprint(executedRequest),
        result: { messageId: "already-sent", delivery: "idle", idleDelivery: true },
      })}\n`,
    );
    await writeFile(
      join(processing, "executed-recovery.json.recovery"),
      `${JSON.stringify({
        sessionId: "retired-session",
        generation: "dead-recovery-generation",
      })}\n`,
    );
    await writeFile(
      join(processing, "ambiguous-recovery.json.stage"),
      `${JSON.stringify({
        ownerGeneration: "dead-generation",
        stage: "executing",
        fingerprint: fingerprint(ambiguousRequest),
      })}\n`,
    );
    await writeFile(
      join(processing, "foreign-claimed.json.stage"),
      `${JSON.stringify({
        ownerGeneration: "dead-generation",
        stage: "claimed",
        fingerprint: fingerprint(foreignClaimedRequest),
      })}\n`,
    );

    const pendingRecovered = await harness.receipt("completed", "pending-rebind");
    assert.equal(pendingRecovered.result.delivery, "idle");
    const safe = await harness.receipt("completed", "safe-requeue");
    assert.equal(safe.result.delivery, "idle");
    const executed = await harness.receipt("completed", "executed-recovery");
    assert.equal(executed.recovered, true);
    assert.equal(executed.result.messageId, "already-sent");
    const ambiguous = await harness.receipt("failed", "ambiguous-recovery");
    assert.equal(ambiguous.ambiguousSideEffect, true);
    assert.equal(
      JSON.parse(await readFile(join(processing, "foreign-claimed.json"), "utf8"))
        .target.sessionId,
      "other-session",
    );
    await assert.rejects(
      readFile(join(harness.inbox, "failed", "foreign-claimed.json")),
      { code: "ENOENT" },
    );
    assert.equal(
      (await harness.calls()).filter(
        (call) => call.kind === "send" && call.value.prompt === "already delivered",
      ).length,
      0,
    );
  } finally {
    await harness.stop();
  }
});
