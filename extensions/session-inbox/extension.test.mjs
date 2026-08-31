import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
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
import { appendFileSync, readFileSync, rmSync, writeFileSync } from "node:fs";

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
      if (current.queuePromptOnSend) {
        writeFileSync(
          process.env.MOCK_STATE,
          JSON.stringify({
            ...current,
            queuedPrompt: options.prompt,
            extraQueuedPrompt: current.additionalQueuePromptOnSend
              ? options.prompt
              : current.extraQueuedPrompt,
          }) + "\\n",
        );
      }
      if (
        !current.suppressDelivery &&
        !(options.agentMode === "autopilot" && current.suppressAutopilotDelivery)
      ) {
        queueMicrotask(() => emit("user.message", {
          type: "user.message",
          data: {
            content: options.prompt,
            delivery: current.delivery,
            agentMode: options.agentMode,
            source: options.agentMode === "autopilot" ? "sdk" : undefined,
          },
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
          const current = state();
          if (current.pendingItemsNeverResolves) {
            return new Promise(() => {});
          }
          return {
            items: [
              ...(current.preexistingQueuedPrompt
                ? [{
                    id: "preexisting-message",
                    kind: "message",
                    displayText: current.preexistingQueuedPrompt,
                    agentMode: "interactive",
                  }]
                : []),
              ...(current.queuedPrompt
                ? [{
                  id: "queued-message",
                  kind: "message",
                  displayText: current.queuedPrompt,
                  agentMode: "interactive",
                }]
                : []),
              ...(current.extraQueuedPrompt
                ? [{
                    id: "extra-queued-message",
                    kind: "message",
                    displayText: current.extraQueuedPrompt,
                    agentMode: "interactive",
                  }]
                : []),
              ...Array.from({length: current.pending}, (_, index) => ({
                  id: "pending-" + index,
                  kind: "message",
                  displayText: "pending " + index,
                  agentMode: "interactive",
                })),
            ],
            steeringMessages: current.steeringPrompt
              ? [current.steeringPrompt]
              : [],
          };
        },
        async sendNow(options) {
          record("queue.sendNow", options);
          const current = state();
          if (current.sendNowDelayMs) {
            await new Promise((resolve) =>
              setTimeout(resolve, current.sendNowDelayMs),
            );
          }
          if (!current.promoteQueued) {
            if (current.drainQueuedAfterSendNowMs !== undefined) {
              setTimeout(() => {
                const latest = state();
                writeFileSync(
                  process.env.MOCK_STATE,
                  JSON.stringify({
                    ...latest,
                    ...(latest.retainQueuedOnDrain
                      ? {}
                      : {queuedPrompt: undefined}),
                  }) + "\\n",
                );
                if (!latest.suppressDrainDelivery) {
                  emit("user.message", {
                    type: "user.message",
                    data: {
                      content: current.queuedPrompt,
                      delivery: "idle",
                    },
                  });
                }
              }, current.drainQueuedAfterSendNowMs);
            }
            return {steered: false};
          }
          writeFileSync(
            process.env.MOCK_STATE,
            JSON.stringify({...current, queuedPrompt: undefined}) + "\\n",
          );
          queueMicrotask(() => emit("user.message", {
            type: "user.message",
            data: {
              content: current.queuedPrompt,
              delivery: "steering",
            },
          }));
          return {steered: true};
        },
        async removeAt(options) {
          record("queue.removeAt", options);
          const current = state();
          if (current.removeQueuedError) {
            throw new Error("mock queue removal failed");
          }
          if (!current.removeQueued) return {removed: false};
          writeFileSync(
            process.env.MOCK_STATE,
            JSON.stringify({...current, queuedPrompt: undefined}) + "\\n",
          );
          if (current.lateDeliveryAfterRemoveMs !== undefined) {
            setTimeout(
              () =>
                emit("user.message", {
                  type: "user.message",
                  data: {
                    content: current.queuedPrompt,
                    delivery: "idle",
                  },
                }),
              current.lateDeliveryAfterRemoveMs,
            );
          }
          return {removed: true};
        },
      },
      extensions: {
        async reload() {
          record("extensions.reload", {});
          if (state().exitOnReload) process.exit(0);
        },
      },
      history: {
        async compact(options) {
          record("compact", options);
          const current = state();
          if (current.breakDedupeWrite) {
            rmSync(process.env.MOCK_DEDUPE_DIR, {recursive: true, force: true});
            writeFileSync(process.env.MOCK_DEDUPE_DIR, "block dedupe directory");
          }
          if (current.idleBeforeCompactCompletion) {
            queueMicrotask(() =>
              emit("session.idle", {type: "session.idle", data: {}}),
            );
          }
          setTimeout(
            () =>
              emit("session.compaction_complete", {
                type: "session.compaction_complete",
                data: {
                  success: current.compactEventSuccess ?? true,
                  customInstructions: options.customInstructions,
                },
              }),
            current.compactCompletionDelayMs ?? 10,
          );
          if (!current.suppressCompactIdle) {
            setTimeout(() => {
              const latest = state();
              writeFileSync(
                process.env.MOCK_STATE,
                JSON.stringify({
                  ...latest,
                  idleCounter: latest.idleCounter + 1,
                  ...(latest.deliveryAfterCompactIdle
                    ? {delivery: latest.deliveryAfterCompactIdle}
                    : {}),
                }) + "\\n",
              );
            }, current.compactIdleDelayMs ?? 20);
          }
          return {success: true, tokensRemoved: 11, messagesRemoved: 3};
        },
      },
      workspaces: {
        async readAutopilotObjective() {
          record("autopilot-objective.read", {});
          return {content: state().autopilotObjective ?? null};
        },
      },
      commands: {
        async invoke(options) {
          record("command.invoke", options);
          const current = state();
          if (current.rejectCommandAfterRecord) {
            throw new Error("mock transport lost the accepted command response");
          }
          if (
            options.name === "autopilot" &&
            !current.suppressAutopilotObjective
          ) {
            const objective = options.input;
            writeFileSync(
              process.env.MOCK_STATE,
              JSON.stringify({
                ...current,
                autopilotObjective: JSON.stringify({
                  version: 1,
                  nextId: 2,
                  current: {
                    id: 1,
                    objective,
                    status: "active",
                    autopilotOrigin: "objective",
                    turnCount: 0,
                  },
                }),
              }) + "\\n",
            );
          }
          if (current.activeAutopilot) {
            return {kind: "text", text: "Autopilot objective updated."};
          }
          return {
            kind: "agent-prompt",
            prompt: \`The user set this explicit autopilot objective with /autopilot:\\n\\n\${options.input}\\n\\nWork autonomously.\`,
            displayPrompt: \`Autopilot objective: \${options.input}\`,
            mode: "autopilot",
          };
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
      COPILOT_SESSION_STATE_ROOT: join(root, "session-state"),
      COPILOT_SESSION_INBOX_CONFIRM_TIMEOUT_MS: "500",
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

test("recipient extension submits SDK work and preserves phase state", async () => {
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
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("autopilot-objective", {
      kind: "autopilot",
      prompt: "finish the durable objective\nand verify its result",
      dedupeKey: "autopilot-objective",
    });
    const autopilotReceipt = await Promise.race([
      harness.receipt("completed", "autopilot-objective"),
      harness
        .receipt("failed", "autopilot-objective")
        .then((receipt) => assert.fail(JSON.stringify(receipt))),
    ]);
    assert.equal(autopilotReceipt.result.objectiveSet, true);
    assert.equal(autopilotReceipt.result.objectiveStatus, "active");
    assert.equal(autopilotReceipt.result.activation, "idle");
    assert.equal(autopilotReceipt.result.idleDelivery, true);
    const autopilotCalls = (await harness.calls()).filter((call) =>
      ["command.invoke", "autopilot-objective.read"].includes(call.kind),
    );
    assert.deepEqual(autopilotCalls.slice(-2), [
      {
        kind: "command.invoke",
        value: {
          name: "autopilot",
          input: "finish the durable objective\nand verify its result",
        },
      },
      { kind: "autopilot-objective.read", value: {} },
    ]);

    await harness.setState({ idleCounter: 2 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.setState({ suppressAutopilotObjective: true });
    await harness.request("autopilot-unconfirmed", {
      kind: "autopilot",
      prompt: "a different objective that never persists",
      dedupeKey: "autopilot-unconfirmed",
    });
    const unconfirmedObjective = await harness.receipt(
      "failed",
      "autopilot-unconfirmed",
    );
    assert.equal(unconfirmedObjective.ambiguousSideEffect, true);
    assert.match(
      unconfirmedObjective.error,
      /did not establish the requested objective/,
    );
    await harness.setState({
      suppressAutopilotObjective: false,
      idleCounter: 3,
    });

    await new Promise((resolve) => setTimeout(resolve, 350));
    await harness.setState({ processing: true, active: true, pending: 2 });
    await harness.request("busy-compact", {
      kind: "compact",
      customInstructions: "compact during active autopilot",
    });
    assert.equal(
      (await harness.receipt("completed", "busy-compact")).result.compacted,
      true,
    );
    assert.ok(
      (await harness.calls()).some(
        (call) =>
          call.kind === "compact" &&
          call.value.customInstructions ===
            "compact during active autopilot",
      ),
    );

    await harness.request("busy-send", {
      kind: "send",
      prompt: "steer during active work",
      mode: "immediate",
    });
    assert.equal(
      (await harness.receipt("completed", "busy-send")).result.delivery,
      "idle",
    );
    assert.deepEqual(
      (await harness.calls()).find(
        (call) =>
          call.kind === "send" &&
          call.value.prompt === "steer during active work",
      ),
      {
        kind: "send",
        value: {
          prompt: "steer during active work",
          mode: "immediate",
        },
      },
    );

    await harness.setState({
      delivery: "steering",
      activeAutopilot: true,
    });
    await harness.request("busy-autopilot", {
      kind: "autopilot",
      prompt: "execute the objective during active work",
      dedupeKey: "busy-autopilot",
    });
    const busyAutopilot = await harness.receipt("completed", "busy-autopilot");
    assert.equal(busyAutopilot.result.objectiveSet, true);
    assert.equal(busyAutopilot.result.delivery, "steering");
    assert.equal(busyAutopilot.result.queuedDelivery, false);
    assert.equal(busyAutopilot.result.commandInvoked, true);
    assert.equal(busyAutopilot.result.objectiveUpdatedInPlace, true);
    assert.ok(
      (await harness.calls()).some(
        (call) =>
          call.kind === "command.invoke" &&
          call.value.name === "autopilot" &&
          call.value.input === "execute the objective during active work",
      ),
    );
    assert.equal(
      (await harness.calls()).some(
        (call) =>
          call.kind === "send" &&
          call.value.prompt.includes("execute the objective during active work"),
      ),
      false,
    );
    await harness.request("busy-autopilot-duplicate", {
      kind: "autopilot",
      prompt: "execute the objective during active work",
      dedupeKey: "busy-autopilot",
    });
    assert.equal(
      (await harness.receipt("completed", "busy-autopilot-duplicate")).deduplicated,
      true,
    );
    assert.equal(
      (await harness.calls()).filter(
        (call) =>
          call.kind === "command.invoke" &&
          call.value.name === "autopilot" &&
          call.value.input === "execute the objective during active work",
      ).length,
      1,
    );
    await harness.setState({
      activeAutopilot: false,
      delivery: "idle",
      autopilotObjective: JSON.stringify({
        version: 1,
        nextId: 2,
        current: {
          id: 1,
          objective: "execute the objective during active work",
          status: "paused",
          pauseReason: "resumed_session",
        },
      }),
    });
    await harness.request("busy-autopilot-resumed", {
      kind: "autopilot",
      prompt: "execute the objective during active work",
      dedupeKey: "busy-autopilot",
    });
    const resumedAutopilot = await harness.receipt(
      "completed",
      "busy-autopilot-resumed",
    );
    assert.equal(resumedAutopilot.deduplicated, false);
    assert.equal(resumedAutopilot.result.objectiveStatus, "active");
    assert.equal(
      (await harness.calls()).filter(
        (call) =>
          call.kind === "command.invoke" &&
          call.value.name === "autopilot" &&
          call.value.input === "execute the objective during active work",
      ).length,
      2,
    );
    await harness.setState({
      activeAutopilot: false,
      delivery: "queued",
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("queued-autopilot", {
      kind: "autopilot",
      prompt: "reject a queued objective activation",
      dedupeKey: "queued-autopilot",
    });
    const queuedAutopilot = await harness.receipt("failed", "queued-autopilot");
    assert.equal(queuedAutopilot.ambiguousSideEffect, true);
    assert.match(queuedAutopilot.error, /started with queued delivery/);
    await harness.setState({
      processing: false,
      active: false,
      pending: 0,
      delivery: "idle",
      idleCounter: 4,
    });

    await harness.request("dedupe-first", {
      kind: "send",
      prompt: "one-shot prompt",
      mode: "immediate",
      dedupeKey: "one-shot",
    });
    await harness.receipt("completed", "dedupe-first");
    await harness.setState({ idleCounter: 6 });
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
    await harness.setState({ delivery: "steering", idleCounter: 7 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("non-idle-send", {
      kind: "send",
      prompt: "non-idle one-shot",
      mode: "immediate",
      dedupeKey: "non-idle-one-shot",
    });
    const nonIdle = await harness.receipt("completed", "non-idle-send");
    assert.equal(nonIdle.result.messageAccepted, true);
    assert.equal(nonIdle.result.delivery, "steering");
    assert.equal(nonIdle.result.idleDelivery, false);
    await harness.setState({ delivery: "idle", idleCounter: 8 });
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
    await harness.setState({ idleCounter: 9 });
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

    await harness.setState({ suppressDelivery: true, idleCounter: 10 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("unconfirmed-send", {
      kind: "send",
      prompt: "accepted without event",
      mode: "immediate",
      dedupeKey: "unconfirmed-one-shot",
    });
    const unconfirmed = await harness.receipt("failed", "unconfirmed-send");
    assert.equal(unconfirmed.ambiguousSideEffect, true);
    assert.equal(unconfirmed.result.messageAccepted, true);
    assert.equal(unconfirmed.result.delivery, "unconfirmed");
    await harness.setState({ suppressDelivery: false, idleCounter: 11 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("unconfirmed-retry", {
      kind: "send",
      prompt: "accepted without event",
      mode: "immediate",
      dedupeKey: "unconfirmed-one-shot",
    });
    const unconfirmedRetry = await harness.receipt("failed", "unconfirmed-retry");
    assert.equal(unconfirmedRetry.ambiguousSideEffect, true);
    assert.match(unconfirmedRetry.error, /prior request side effect is ambiguous/);
    assert.equal(
      (await harness.calls()).filter(
        (call) => call.kind === "send" && call.value.prompt === "accepted without event",
      ).length,
      1,
    );

    await harness.setState({ rejectSendAfterRecord: true, idleCounter: 12 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("ambiguous-send", {
      kind: "send",
      prompt: "accepted then rejected",
      mode: "immediate",
      dedupeKey: "ambiguous-one-shot",
    });
    const ambiguousSend = await harness.receipt("failed", "ambiguous-send");
    assert.equal(ambiguousSend.ambiguousSideEffect, true);
    await harness.setState({ rejectSendAfterRecord: false, idleCounter: 13 });
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

    await harness.setState({
      suppressDelivery: true,
      processing: true,
      active: true,
      pending: 1,
      idleCounter: 14,
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("compact-unconfirmed-continuation", {
      kind: "compact",
      customInstructions: "long-running active turn proof",
      continuationPrompt: "queue without waiting for its later event",
    });
    const compactUnconfirmed = await harness.receipt(
      "failed",
      "compact-unconfirmed-continuation",
    );
    assert.equal(compactUnconfirmed.ambiguousSideEffect, true);
    assert.equal(compactUnconfirmed.result.compacted, true);
    assert.equal(compactUnconfirmed.result.continuationAccepted, true);
    assert.equal(typeof compactUnconfirmed.result.continuationMessageId, "string");
    assert.equal(compactUnconfirmed.result.continuationDelivery, "unconfirmed");

    await harness.setState({
      suppressDelivery: false,
      delivery: "steering",
      processing: true,
      active: true,
      pending: 1,
      idleCounter: 15,
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("compact-steering-continuation", {
      kind: "compact",
      customInstructions: "steering continuation proof",
      continuationPrompt: "resume through immediate delivery",
    });
    const compactSteering = await harness.receipt(
      "completed",
      "compact-steering-continuation",
    );
    assert.equal(compactSteering.result.compacted, true);
    assert.equal(compactSteering.result.continuationAccepted, true);
    assert.equal(typeof compactSteering.result.continuationMessageId, "string");
    assert.equal(compactSteering.result.continuationDelivery, "steering");
    assert.equal(compactSteering.result.continuationError, undefined);

    await harness.setState({
      suppressDelivery: false,
      delivery: "idle",
      deliveryAfterCompactIdle: undefined,
      compactIdleDelayMs: undefined,
      idleBeforeCompactCompletion: true,
      processing: true,
      active: true,
      pending: 1,
      idleCounter: 16,
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await harness.request("compact-waits-for-idle", {
      kind: "compact",
      customInstructions: "post-compact idle proof",
      continuationPrompt: "resume immediately after compact completion",
    });
    const compactAfterIdle = await harness.receipt(
      "completed",
      "compact-waits-for-idle",
    );
    assert.equal(compactAfterIdle.result.compacted, true);
    assert.equal(compactAfterIdle.result.continuationAccepted, true);
    assert.equal(compactAfterIdle.result.continuationDelivery, "idle");

    await harness.setState({
      delivery: "idle",
      breakDedupeWrite: true,
      deliveryAfterCompactIdle: undefined,
      compactIdleDelayMs: undefined,
      idleBeforeCompactCompletion: undefined,
      idleCounter: 17,
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
    await rm(join(harness.inbox, "dedupe"), { force: true });
    await mkdir(join(harness.inbox, "dedupe"));
    await harness.setState({ breakDedupeWrite: false, idleCounter: 17 });
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
    await rm(join(harness.inbox, "dedupe"), { recursive: true, force: true });
    await mkdir(join(harness.inbox, "dedupe"), { recursive: true });
    await harness.setState({ breakDedupeWrite: false });
    const recoveredReceipt = await harness.receipt(
      "completed",
      "compact-receipt-failure",
    );
    assert.equal(recoveredReceipt.recovered, true);
    await harness.setState({ idleCounter: 18 });
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
        (entry) => entry.event === "sdk.autopilot_objective.sent",
      ),
    );
    assert.equal(
      diagnostics.some(
        (entry) => entry.event === "request.deferred",
      ),
      false,
    );
    const serializedDiagnostics = JSON.stringify(diagnostics);
    assert.doesNotMatch(serializedDiagnostics, /idle prompt/);
    assert.doesNotMatch(serializedDiagnostics, /receipt failure proof/);
  } finally {
    await harness.stop();
  }
});

test("non-immediate sends fail definitively and leave their dedupe key retryable", async () => {
  const harness = await createHarness();
  try {
    await harness.request("legacy-queued-send", {
      kind: "send",
      prompt: "legacy queued prompt",
      mode: "enqueue",
      dedupeKey: "legacy-send",
    });

    const rejected = await harness.receipt("failed", "legacy-queued-send");
    assert.equal(rejected.ambiguousSideEffect, undefined);
    assert.match(rejected.error, /must use immediate delivery/);
    assert.equal(
      (await harness.calls()).some(
        (call) =>
          call.kind === "send" &&
          call.value.prompt === "legacy queued prompt",
      ),
      false,
    );

    await harness.setState({ idleCounter: 1 });
    await harness.request("replacement-immediate-send", {
      kind: "send",
      prompt: "legacy queued prompt",
      mode: "immediate",
      dedupeKey: "legacy-send",
    });
    const replacement = await harness.receipt(
      "completed",
      "replacement-immediate-send",
    );
    assert.equal(replacement.result.delivery, "idle");
    assert.equal(replacement.deduplicated, false);
  } finally {
    await harness.stop();
  }
});

test("a rotation barrier leaves prepublished inbox work pending", async () => {
  const harness = await createHarness();
  try {
    const sessionDir = join(
      harness.root,
      "session-state",
      harness.heartbeat.sessionId,
    );
    await mkdir(sessionDir, { recursive: true });
    await writeFile(join(sessionDir, "rotation.barrier"), "rotating\n");
    await harness.request("rotation-barrier-send", {
      kind: "send",
      mode: "immediate",
      prompt: "must not be sent",
    });
    await new Promise((resolve) => setTimeout(resolve, 300));
    assert.equal(
      JSON.parse(
        await readFile(
          join(harness.inbox, "pending", "rotation-barrier-send.json"),
          "utf8",
        ),
      ).id,
      "rotation-barrier-send",
    );
    assert.equal(
      (await harness.calls()).some((call) => call.kind === "send"),
      false,
    );
  } finally {
    await harness.stop();
  }
});

test("an immediate send observed in the FIFO fails ambiguously", async () => {
  const harness = await createHarness({ delivery: "queued" });
  try {
    await harness.request("queued-immediate-send", {
      kind: "send",
      prompt: "must not enter FIFO",
      mode: "immediate",
      dedupeKey: "queued-immediate",
    });
    const receipt = await harness.receipt("failed", "queued-immediate-send");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /message entered the FIFO queue/);
    assert.equal(receipt.result.delivery, "queued");
    assert.equal(receipt.result.queuedDelivery, true);
  } finally {
    await harness.stop();
  }
});

test("an immediate send placed in FIFO is promoted to steering", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    promoteQueued: true,
  });
  try {
    await harness.request("promote-queued-send", {
      kind: "send",
      prompt: "promote me",
      mode: "immediate",
      dedupeKey: "promote-queued",
    });
    const receipt = await harness.receipt("completed", "promote-queued-send");
    assert.equal(receipt.result.delivery, "steering");
    assert.equal(receipt.result.queuedDelivery, false);
    assert.ok(
      (await harness.calls()).some(
        (call) =>
          call.kind === "queue.sendNow" &&
          call.value.id === "queued-message",
      ),
    );
  } finally {
    await harness.stop();
  }
});

test("an unsteerable queued send is removed definitively", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    removeQueued: true,
  });
  try {
    await harness.request("remove-queued-send", {
      kind: "send",
      prompt: "remove me",
      mode: "immediate",
      dedupeKey: "remove-queued",
    });
    const receipt = await harness.receipt("failed", "remove-queued-send");
    assert.equal(receipt.ambiguousSideEffect, undefined);
    assert.equal(receipt.terminalFallbackEligible, true);
    assert.match(receipt.error, /removed from FIFO/);
    assert.ok(
      (await harness.calls()).some(
        (call) =>
          call.kind === "queue.removeAt" &&
          call.value.id === "queued-message",
      ),
    );
  } finally {
    await harness.stop();
  }
});

test("queue recovery never touches a preexisting identical message", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    preexistingQueuedPrompt: "same prompt",
  });
  try {
    await harness.request("preexisting-identical-send", {
      kind: "send",
      prompt: "same prompt",
      mode: "immediate",
      dedupeKey: "preexisting-identical",
    });
    const receipt = await harness.receipt("failed", "preexisting-identical-send");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /delivery was not confirmed/);
    assert.equal(
      (await harness.calls()).some(
        (call) =>
          call.kind === "queue.sendNow" || call.kind === "queue.removeAt",
      ),
      false,
    );
  } finally {
    await harness.stop();
  }
});

test("queue recovery promotes only the newly appeared identical message", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    preexistingQueuedPrompt: "same prompt",
    queuePromptOnSend: true,
    promoteQueued: true,
  });
  try {
    await harness.request("new-identical-send", {
      kind: "send",
      prompt: "same prompt",
      mode: "immediate",
      dedupeKey: "new-identical",
    });
    const receipt = await harness.receipt("completed", "new-identical-send");
    assert.equal(receipt.result.delivery, "steering");
    const queueCalls = (await harness.calls()).filter(
      (call) =>
        call.kind === "queue.sendNow" || call.kind === "queue.removeAt",
    );
    assert.deepEqual(
      queueCalls.map((call) => [call.kind, call.value.id]),
      [["queue.sendNow", "queued-message"]],
    );
  } finally {
    await harness.stop();
  }
});

test("multiple newly appeared identical messages remain ambiguous", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    additionalQueuePromptOnSend: true,
    promoteQueued: true,
  });
  try {
    await harness.request("multiple-identical-send", {
      kind: "send",
      prompt: "duplicate prompt",
      mode: "immediate",
      dedupeKey: "multiple-identical",
    });
    const receipt = await harness.receipt("failed", "multiple-identical-send");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /delivery was not confirmed/);
    assert.equal(
      (await harness.calls()).some(
        (call) =>
          call.kind === "queue.sendNow" || call.kind === "queue.removeAt",
      ),
      false,
    );
  } finally {
    await harness.stop();
  }
});

test("a stalled queue snapshot cannot outlive the confirmation deadline", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    pendingItemsNeverResolves: true,
  });
  try {
    const startedAt = Date.now();
    await harness.request("stalled-queue-snapshot-send", {
      kind: "send",
      prompt: "bounded queue snapshot",
      mode: "immediate",
      dedupeKey: "stalled-queue-snapshot",
    });
    const receipt = await harness.receipt("failed", "stalled-queue-snapshot-send");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /confirmation deadline/);
    assert.ok(Date.now() - startedAt < 2_000);
    assert.equal(
      (await harness.calls()).filter((call) => call.kind === "send").length,
      1,
    );
  } finally {
    await harness.stop();
  }
});

test("a delayed queue mutation settles before an ambiguous receipt permits retry", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    promoteQueued: true,
    sendNowDelayMs: 750,
  });
  try {
    await harness.request("delayed-promotion-send", {
      kind: "send",
      prompt: "delayed promotion",
      mode: "immediate",
      dedupeKey: "delayed-promotion",
    });
    const receipt = await harness.receipt("failed", "delayed-promotion-send");
    assert.equal(receipt.ambiguousSideEffect, true);

    await harness.request("delayed-promotion-retry", {
      kind: "send",
      prompt: "delayed promotion",
      mode: "immediate",
      dedupeKey: "delayed-promotion",
    });
    const retry = await harness.receipt("failed", "delayed-promotion-retry");
    assert.equal(retry.ambiguousSideEffect, true);
    const calls = await harness.calls();
    assert.equal(calls.filter((call) => call.kind === "send").length, 1);
    assert.equal(
      calls.filter((call) => call.kind === "queue.sendNow").length,
      1,
    );
  } finally {
    await harness.stop();
  }
});

test("a compact continuation observed in the FIFO fails ambiguously", async () => {
  const harness = await createHarness({ delivery: "queued" });
  try {
    await harness.request("queued-compact-continuation", {
      kind: "compact",
      customInstructions: "queued continuation rejection",
      continuationPrompt: "must not enter FIFO",
      dedupeKey: "queued-compact",
    });
    const receipt = await harness.receipt(
      "failed",
      "queued-compact-continuation",
    );
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /compact continuation entered the FIFO queue/);
    assert.equal(receipt.result.compacted, true);
    assert.equal(receipt.result.continuationAccepted, true);
    assert.equal(receipt.result.continuationDelivery, "queued");
  } finally {
    await harness.stop();
  }
});

test("a compact continuation may drain naturally into an idle turn", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    drainQueuedAfterSendNowMs: 20,
  });
  try {
    await harness.request("natural-drain-compact", {
      kind: "compact",
      customInstructions: "natural drain proof",
      continuationPrompt: "nonce-bearing natural drain",
      dedupeKey: "natural-drain-compact",
    });
    const receipt = await harness.receipt("completed", "natural-drain-compact");
    assert.equal(receipt.result.continuationAccepted, true);
    assert.equal(receipt.result.continuationDelivery, "idle");
    const queueCalls = await harness.calls();
    assert.equal(
      queueCalls.some((call) => call.kind === "queue.sendNow"),
      true,
    );
    assert.equal(
      queueCalls.some((call) => call.kind === "queue.removeAt"),
      false,
    );
  } finally {
    await harness.stop();
  }
});

test("natural idle delivery remains valid through the confirmation deadline", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    drainQueuedAfterSendNowMs: 180,
  });
  try {
    await harness.request("late-natural-drain-compact", {
      kind: "compact",
      customInstructions: "late natural drain proof",
      continuationPrompt: "nonce-bearing late natural drain",
      dedupeKey: "late-natural-drain-compact",
    });
    const receipt = await harness.receipt(
      "completed",
      "late-natural-drain-compact",
    );
    assert.equal(receipt.result.continuationAccepted, true);
    assert.equal(receipt.result.continuationDelivery, "idle");
    assert.equal(
      (await harness.calls()).some((call) => call.kind === "queue.removeAt"),
      false,
    );
  } finally {
    await harness.stop();
  }
});

test("a continuation event while its exact queue item remains is ambiguous", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    drainQueuedAfterSendNowMs: 20,
    retainQueuedOnDrain: true,
    removeQueued: true,
  });
  try {
    await harness.request("event-item-remains", {
      kind: "compact",
      customInstructions: "event item remains proof",
      continuationPrompt: "nonce-bearing retained item",
      dedupeKey: "event-item-remains",
    });
    const receipt = await harness.receipt("failed", "event-item-remains");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /removal raced with delivery/);
    assert.equal(receipt.result.continuationDelivery, "idle");
  } finally {
    await harness.stop();
  }
});

test("a still-pending continuation is removed only after the delivery deadline", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    removeQueued: true,
  });
  try {
    await harness.request("remove-still-pending", {
      kind: "compact",
      customInstructions: "remove still pending proof",
      continuationPrompt: "nonce-bearing still pending",
      dedupeKey: "remove-still-pending",
    });
    const receipt = await harness.receipt("completed", "remove-still-pending");
    assert.equal(receipt.result.compacted, true);
    assert.equal(receipt.result.continuationAccepted, false);
    assert.match(receipt.result.continuationError, /did not drain/);
  } finally {
    await harness.stop();
  }
});

test("failed continuation queue removal is ambiguous", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
  });
  try {
    await harness.request("remove-false-compact", {
      kind: "compact",
      customInstructions: "remove false proof",
      continuationPrompt: "nonce-bearing remove false",
      dedupeKey: "remove-false-compact",
    });
    const receipt = await harness.receipt("failed", "remove-false-compact");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /removal raced with delivery/);
  } finally {
    await harness.stop();
  }
});

test("continuation queue removal errors are ambiguous", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    removeQueuedError: true,
  });
  try {
    await harness.request("remove-error-compact", {
      kind: "compact",
      customInstructions: "remove error proof",
      continuationPrompt: "nonce-bearing remove error",
      dedupeKey: "remove-error-compact",
    });
    const receipt = await harness.receipt("failed", "remove-error-compact");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /queue recovery did not complete/);
  } finally {
    await harness.stop();
  }
});

test("a continuation queue item disappearing without an event is ambiguous", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    drainQueuedAfterSendNowMs: 20,
    suppressDrainDelivery: true,
  });
  try {
    await harness.request("disappear-without-event", {
      kind: "compact",
      customInstructions: "disappear without event proof",
      continuationPrompt: "nonce-bearing disappeared item",
      dedupeKey: "disappear-without-event",
    });
    const receipt = await harness.receipt("failed", "disappear-without-event");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /disappeared without a confirmed delivery/);
  } finally {
    await harness.stop();
  }
});

test("a delivery event arriving after queue removal is ambiguous", async () => {
  const harness = await createHarness({
    suppressDelivery: true,
    queuePromptOnSend: true,
    removeQueued: true,
    lateDeliveryAfterRemoveMs: 10,
  });
  try {
    await harness.request("late-after-removal", {
      kind: "compact",
      customInstructions: "late after removal proof",
      continuationPrompt: "nonce-bearing late event",
      dedupeKey: "late-after-removal",
    });
    const receipt = await harness.receipt("failed", "late-after-removal");
    assert.equal(receipt.ambiguousSideEffect, true);
    assert.match(receipt.error, /removal raced with delivery/);
  } finally {
    await harness.stop();
  }
});

test("a failed compaction completion never releases its continuation", async () => {
  const harness = await createHarness({
    compactEventSuccess: false,
    delivery: "idle",
  });
  try {
    await harness.request("failed-compact-completion", {
      kind: "compact",
      customInstructions: "failed completion proof",
      continuationPrompt: "must not be sent",
      dedupeKey: "failed-compact-completion",
    });
    const receipt = await harness.receipt("failed", "failed-compact-completion");
    assert.match(
      receipt.error,
      /session history compaction completion reported failure/,
    );
    assert.equal(
      (await harness.calls()).some(
        (call) =>
          call.kind === "send" && call.value.prompt === "must not be sent",
      ),
      false,
    );
  } finally {
    await harness.stop();
  }
});

test("extension reload receipt is durable before the extension exits", async () => {
  const harness = await createHarness({ exitOnReload: true });
  try {
    await harness.request("reload-extension", {
      kind: "reload-extensions",
    });
    const receipt = await harness.receipt("completed", "reload-extension");
    assert.equal(receipt.result.reloadRequested, true);
    const result = await harness.exit;
    assert.equal(result.code, 0, result.stderr);
    assert.ok(
      (await harness.calls()).some((call) => call.kind === "extensions.reload"),
    );
    await assert.rejects(
      readFile(join(harness.inbox, "processing", "reload-extension.json")),
      { code: "ENOENT" },
    );
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
