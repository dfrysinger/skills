import { createHash, randomBytes } from "node:crypto";
import { mkdir, readdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

import { joinSession } from "@github/copilot-sdk/extension";
import { createDiagnosticLogger, errorDetails } from "./diagnostics.mjs";
import { currentSessionName, currentTmuxSession } from "./session-identity.mjs";

const root = process.env.COPILOT_SESSION_INBOX_DIR ?? join(homedir(), ".copilot", "session-inbox");
const pendingDir = join(root, "pending");
const processingDir = join(root, "processing");
const completedDir = join(root, "completed");
const failedDir = join(root, "failed");
const instancesDir = join(root, "instances");
const dedupeDir = join(root, "dedupe");
let pluginVersion;
try {
  pluginVersion = JSON.parse(
    await readFile(new URL("../../plugin.json", import.meta.url), "utf8"),
  ).version;
} catch {
  // Development harnesses and project-local copies may not have a plugin manifest.
}
const configuredConfirmationTimeoutMs = Number.parseInt(
  process.env.COPILOT_SESSION_INBOX_CONFIRM_TIMEOUT_MS ?? "10000",
  10,
);
const confirmationTimeoutMs =
  Number.isFinite(configuredConfirmationTimeoutMs) &&
  configuredConfirmationTimeoutMs > 0
    ? configuredConfirmationTimeoutMs
    : 10_000;
const configuredAutopilotConfirmationTimeoutMs = Number.parseInt(
  process.env.COPILOT_SESSION_INBOX_AUTOPILOT_CONFIRM_TIMEOUT_MS ??
    process.env.COPILOT_SESSION_INBOX_CONFIRM_TIMEOUT_MS ??
    "300000",
  10,
);
const autopilotConfirmationTimeoutMs =
  Number.isFinite(configuredAutopilotConfirmationTimeoutMs) &&
  configuredAutopilotConfirmationTimeoutMs > 0
    ? configuredAutopilotConfirmationTimeoutMs
    : 300_000;

const startupDiagnostics = createDiagnosticLogger(
  root,
  `extension-bootstrap-${process.pid}.jsonl`,
  { component: "extension", hostPid: process.ppid, pid: process.pid },
);
let session;
try {
  session = await joinSession();
} catch (error) {
  startupDiagnostics.log("extension.start_failed", {
    phase: "joinSession",
    error: errorDetails(error),
  });
  throw error;
}
let tmuxSession;
let sessionName;
let heartbeatRefreshing = false;
let initialTmuxSessionError;
let initialSessionNameError;
try {
  tmuxSession = await currentTmuxSession();
} catch (error) {
  initialTmuxSessionError = error;
}
try {
  sessionName = await currentSessionName(session);
} catch (error) {
  initialSessionNameError = error;
}
const generation = randomBytes(16).toString("hex");
const diagnostics = createDiagnosticLogger(
  root,
  `${session.sessionId}-${generation}.jsonl`,
  {
    component: "extension",
    sessionId: session.sessionId,
    generation,
    tmuxSession,
    sessionName,
    hostPid: process.ppid,
    pid: process.pid,
  },
);
let pumping = false;

await Promise.all(
  [
    pendingDir,
    processingDir,
    completedDir,
    failedDir,
    instancesDir,
    dedupeDir,
  ].map((dir) => mkdir(dir, { recursive: true, mode: 0o700 })),
);
diagnostics.log("extension.started", {
  extensionPath: import.meta.url,
  pluginVersion,
  confirmationTimeoutMs,
});
if (initialSessionNameError) {
  diagnostics.log("session.identity_lookup_failed", {
    identitySource: "session-name",
    error: errorDetails(initialSessionNameError),
  });
}
if (initialTmuxSessionError) {
  diagnostics.log("session.identity_lookup_failed", {
    identitySource: "tmux",
    error: errorDetails(initialTmuxSessionError),
  });
}

function matchesTarget(request) {
  const target = request.target ?? {};
  return (
    target.sessionId === session.sessionId &&
    (!target.generation || target.generation === generation)
  );
}

async function writeJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.${process.pid}.${randomBytes(4).toString("hex")}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await rename(temporaryPath, path);
}

async function writeHeartbeat() {
  if (heartbeatRefreshing) return;
  heartbeatRefreshing = true;
  try {
    let refreshedTmuxSession = tmuxSession;
    try {
      refreshedTmuxSession = await currentTmuxSession();
    } catch (error) {
      diagnostics.log("session.identity_lookup_failed", {
        identitySource: "tmux",
        error: errorDetails(error),
      });
    }
    let refreshedSessionName = sessionName;
    try {
      refreshedSessionName = await currentSessionName(session);
    } catch (error) {
      diagnostics.log("session.identity_lookup_failed", {
        identitySource: "session-name",
        error: errorDetails(error),
      });
    }
    if (
      refreshedTmuxSession !== tmuxSession ||
      refreshedSessionName !== sessionName
    ) {
      tmuxSession = refreshedTmuxSession;
      sessionName = refreshedSessionName;
      diagnostics.setContext({ tmuxSession, sessionName });
      diagnostics.log("session.identity_changed", { tmuxSession, sessionName });
    }
    await writeJson(join(instancesDir, `${session.sessionId}-${generation}.json`), {
      sessionId: session.sessionId,
      tmuxSession,
      sessionName,
      generation,
      hostPid: process.ppid,
      pid: process.pid,
      pluginVersion,
      updatedAt: new Date().toISOString(),
    });
  } finally {
    heartbeatRefreshing = false;
  }
}

async function sendAndConfirm({ prompt, agentMode }) {
  const matchingEvents = [];
  let resolveEvent;
  const unsubscribe = session.on("user.message", (event) => {
    if (event.data.content !== prompt) return;
    matchingEvents.push(event);
    resolveEvent?.();
    resolveEvent = undefined;
  });
  const confirmationDeadline = Date.now() + confirmationTimeoutMs;
  const beforeSendSnapshotDeadline = Math.min(
    confirmationDeadline,
    Date.now() + Math.min(2_000, confirmationTimeoutMs / 2),
  );
  const withinDeadline = async (operation, deadline, label) => {
    const remainingMs = deadline - Date.now();
    if (remainingMs <= 0) throw new Error(`${label} timed out`);
    let timer;
    try {
      return await Promise.race([
        operation,
        new Promise((_, reject) => {
          timer = setTimeout(
            () => reject(new Error(`${label} timed out`)),
            remainingMs,
          );
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  };
  const waitForDelivery = async (deliveries, deadline = confirmationDeadline) => {
    while (Date.now() < deadline) {
      const event = matchingEvents.find((candidate) =>
        deliveries.includes(candidate.data.delivery),
      );
      if (event) return event;
      await Promise.race([
        new Promise((resolve) => {
          resolveEvent = resolve;
        }),
        new Promise((resolve) =>
          setTimeout(resolve, Math.max(0, deadline - Date.now())),
        ),
      ]);
      resolveEvent = undefined;
    }
    return undefined;
  };
  try {
    let preexistingQueueIds;
    try {
      const pending = await withinDeadline(
        session.rpc.queue.pendingItems(),
        beforeSendSnapshotDeadline,
        "pre-send queue snapshot",
      );
      preexistingQueueIds = new Set(pending.items.map((item) => item.id));
    } catch (error) {
      diagnostics.log("sdk.send.queue_snapshot_failed", {
        phase: "before-send",
        error: errorDetails(error),
      });
    }
    diagnostics.log("sdk.send.started", { mode: "immediate", agentMode });
    const messageId = await session.send({
      prompt,
      mode: "immediate",
      ...(agentMode ? { agentMode } : {}),
    });
    let event = await waitForDelivery(
      ["idle", "steering", "queued"],
      Math.min(
        confirmationDeadline,
        Date.now() + Math.min(2_000, confirmationTimeoutMs / 2),
      ),
    );
    if (!event || event.data.delivery === "queued") {
      try {
        const pending = await withinDeadline(
          session.rpc.queue.pendingItems(),
          confirmationDeadline,
          "post-send queue inspection",
        );
        const queuedMatches = pending.items.filter(
          (item) =>
            item.kind === "message" &&
            item.displayText === prompt &&
            preexistingQueueIds?.has(item.id) === false,
        );
        if (queuedMatches.length === 1) {
          diagnostics.log("sdk.send.promoting_queued", {
            messageId,
            queuedItemId: queuedMatches[0].id,
          });
          const promoted = await withinDeadline(
            session.rpc.queue.sendNow({
              id: queuedMatches[0].id,
            }),
            confirmationDeadline,
            "queued message promotion",
          );
          if (promoted.steered) {
            event = await waitForDelivery(["steering"]);
          } else {
            const removed = await withinDeadline(
              session.rpc.queue.removeAt({
                id: queuedMatches[0].id,
              }),
              confirmationDeadline,
              "queued message removal",
            );
            if (removed.removed) {
              throw definitiveNoSideEffectError(
                "immediate message could not enter the steering lane and was removed from FIFO",
              );
            }
          }
        }
      } catch (error) {
        if (error.definitiveNoSideEffect || error.ambiguousSideEffect) throw error;
        throw ambiguousSideEffectError(
          "session inbox queue recovery did not complete before confirmation deadline",
          {
            messageId,
            messageAccepted: true,
            delivery: event?.data.delivery ?? "unconfirmed",
            idleDelivery: false,
            queuedDelivery: event?.data.delivery === "queued",
            cause: error.message,
          },
        );
      }
      if (!event || event.data.delivery === "queued") {
        event = (await waitForDelivery(["idle", "steering"])) ?? event;
      }
    }
    diagnostics.log(event ? "sdk.send.confirmed" : "sdk.send.unconfirmed", {
      messageId,
      delivery: event?.data.delivery,
    });
    if (!event) {
      throw ambiguousSideEffectError(
        "session inbox message delivery was not confirmed",
        {
          messageId,
          messageAccepted: true,
          delivery: "unconfirmed",
          idleDelivery: false,
          queuedDelivery: false,
        },
      );
    }
    return {
      messageId,
      messageAccepted: true,
      delivery: event.data.delivery,
      idleDelivery: event.data.delivery === "idle",
      queuedDelivery: event.data.delivery === "queued",
    };
  } finally {
    unsubscribe();
  }
}

async function executeAutopilotObjective(prompt) {
  diagnostics.log("sdk.autopilot_objective.started");
  let activation;
  const stopListening = session.on("user.message", (event) => {
    const messageText = `${event.data.content ?? ""}\n${event.data.transformedContent ?? ""}`;
    if (
      event.data.agentMode === "autopilot" &&
      messageText.includes(prompt)
    ) {
      activation = {
        delivery: event.data.delivery,
        idleDelivery: event.data.delivery === "idle",
        queuedDelivery: event.data.delivery === "queued",
      };
    }
  });
  const deadline = Date.now() + autopilotConfirmationTimeoutMs;
  let objective;
  let invocationKind;
  let messageId;
  try {
    const invocation = await session.rpc.commands.invoke({
      name: "autopilot",
      input: prompt,
    });
    invocationKind = invocation.kind;
    if (
      invocation.kind !== "text" &&
      (invocation.kind !== "agent-prompt" || invocation.mode !== "autopilot")
    ) {
      throw new Error(
        `autopilot command returned unsupported result ${invocation.kind}`,
      );
    }
    diagnostics.log("sdk.autopilot_objective.invoked", {
      resultKind: invocation.kind,
    });
    if (invocation.kind === "agent-prompt") {
      messageId = await session.send({
        prompt: invocation.prompt,
        mode: "immediate",
        agentMode: invocation.mode,
      });
      diagnostics.log("sdk.autopilot_objective.sent", { messageId });
    }
    diagnostics.log("sdk.autopilot_objective.executed");

    while (Date.now() < deadline) {
      if (!objective) {
        const saved = await session.rpc.workspaces.readAutopilotObjective();
        if (saved.content) {
          try {
            const state = JSON.parse(saved.content);
            if (
              state?.current?.objective === prompt &&
              ["active", "completed"].includes(state.current.status)
            ) {
              objective = {
                objectiveId: state.current.id,
                objectiveStatus: state.current.status,
              };
            }
          } catch {
            // The native command may still be replacing an older objective file.
          }
        }
      }
      if (objective && invocationKind === "text") {
        diagnostics.log("sdk.autopilot_objective.confirmed", {
          ...objective,
          activation: "active-objective",
        });
        return {
          ...objective,
          delivery: "steering",
          idleDelivery: false,
          queuedDelivery: false,
          objectiveUpdatedInPlace: true,
        };
      }
      if (objective && activation) {
        if (!activation.idleDelivery && activation.delivery !== "steering") {
          throw Object.assign(
            new Error(
              `autopilot objective started with ${activation.delivery ?? "unknown"} delivery`,
            ),
            {
              result: {
                ...objective,
                ...activation,
                commandInvoked: true,
                objectiveSet: true,
                activation: activation.delivery,
              },
              ambiguousSideEffect: true,
            },
          );
        }
        diagnostics.log("sdk.autopilot_objective.confirmed", {
          ...objective,
          delivery: activation.delivery,
        });
        return { ...objective, ...activation, messageId };
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  } finally {
    stopListening();
  }
  throw new Error(
    objective
      ? "autopilot objective was established but its activation was not confirmed"
      : "autopilot command did not establish the requested objective",
  );
}

async function execute(request) {
  switch (request.kind) {
    case "send": {
      if (request.mode !== "immediate") {
        throw definitiveNoSideEffectError(
          "session inbox sends must use immediate delivery",
        );
      }
      const delivery = await sendAndConfirm({
        prompt: request.prompt,
        agentMode: request.agentMode,
      });
      if (delivery.queuedDelivery) {
        throw ambiguousSideEffectError(
          "session inbox message entered the FIFO queue",
          delivery,
        );
      }
      return delivery;
    }
    case "autopilot": {
      const objective = await executeAutopilotObjective(request.prompt);
      return {
        commandInvoked: true,
        objectiveSet: true,
        objectiveId: objective.objectiveId,
        objectiveStatus: objective.objectiveStatus,
        delivery: objective.delivery,
        idleDelivery: objective.idleDelivery,
        queuedDelivery: objective.queuedDelivery,
        activation: objective.delivery,
        objectiveUpdatedInPlace: objective.objectiveUpdatedInPlace === true,
      };
    }
    case "compact": {
      const result = await session.rpc.history.compact({
        ...(request.customInstructions
          ? { customInstructions: request.customInstructions }
          : {}),
        trigger: "manual",
      });
      if (!result.success) {
        throw new Error("session history compaction did not succeed");
      }
      let continuationAccepted;
      let continuationMessageId;
      let continuationDelivery;
      let continuationError;
      if (request.continuationPrompt) {
        try {
          diagnostics.log("sdk.compact_continuation.started", {
            mode: "immediate",
          });
          const continuation = await sendAndConfirm({
            prompt: request.continuationPrompt,
          });
          continuationAccepted = continuation.messageAccepted;
          continuationMessageId = continuation.messageId;
          continuationDelivery = continuation.delivery;
          if (continuation.queuedDelivery) {
            throw ambiguousSideEffectError(
              "compact continuation entered the FIFO queue",
              {
                compacted: true,
                tokensRemoved: result.tokensRemoved,
                messagesRemoved: result.messagesRemoved,
                continuationAccepted,
                continuationMessageId,
                continuationDelivery,
              },
            );
          }
          diagnostics.log("sdk.compact_continuation.accepted", {
            messageId: continuationMessageId,
            delivery: continuationDelivery,
          });
        } catch (error) {
          if (error?.ambiguousSideEffect === true) {
            if (error.result?.compacted === true) throw error;
            throw ambiguousSideEffectError(error.message, {
              compacted: true,
              tokensRemoved: result.tokensRemoved,
              messagesRemoved: result.messagesRemoved,
              continuationAccepted: error.result?.messageAccepted,
              continuationMessageId: error.result?.messageId,
              continuationDelivery: error.result?.delivery,
            });
          }
          continuationAccepted = false;
          continuationError = error instanceof Error ? error.message : String(error);
        }
      }
      return {
        compacted: true,
        tokensRemoved: result.tokensRemoved,
        messagesRemoved: result.messagesRemoved,
        ...(continuationAccepted === undefined ? {} : { continuationAccepted }),
        ...(continuationMessageId === undefined ? {} : { continuationMessageId }),
        ...(continuationDelivery === undefined ? {} : { continuationDelivery }),
        ...(continuationError ? { continuationError } : {}),
      };
    }
    case "new-session-direct": {
      const available = await session.rpc.commands.list();
      const directNew = available.commands.some(
        (command) => command.name === "new" && command.kind === "builtin",
      );
      if (!directNew) {
        throw definitiveNoSideEffectError(
          "direct session rotation is unavailable: Copilot CLI does not expose /new through a non-FIFO SDK API",
        );
      }
      let invocation;
      try {
        invocation = await session.rpc.commands.invoke({
          name: "new",
          input: request.prompt,
        });
      } catch (error) {
        if (
          error instanceof Error &&
          /Unknown slash command: \/new/.test(error.message)
        ) {
          throw definitiveNoSideEffectError(
            "direct session rotation is unavailable: Copilot CLI rejected /new as a direct command",
          );
        }
        throw error;
      }
      if (invocation.kind !== "completed") {
        throw ambiguousSideEffectError(
          `direct /new returned unsupported result ${invocation.kind}`,
          {
            commandInvoked: true,
            mechanism: "commands.invoke",
            resultKind: invocation.kind,
          },
        );
      }
      return {
        commandInvoked: true,
        mechanism: "commands.invoke",
        resultKind: invocation.kind,
      };
    }
    case "reload-extensions":
      return { reloadRequested: true };
    default:
      throw new Error(`unsupported session inbox request kind: ${request.kind}`);
  }
}

function requestFingerprint(request) {
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

function dedupePath(key, sessionId = session.sessionId) {
  const digest = createHash("sha256").update(`${sessionId}\0${key}`).digest("hex");
  return join(dedupeDir, `${digest}.json`);
}

function ambiguousSideEffectError(message, result) {
  const error = new Error(message);
  error.ambiguousSideEffect = true;
  error.result = result;
  return error;
}

function definitiveNoSideEffectError(message) {
  const error = new Error(message);
  error.definitiveNoSideEffect = true;
  return error;
}

function stagePath(directory, name) {
  return join(directory, `${name}.stage`);
}

function recoveryLockPath(name) {
  return join(processingDir, `${name}.recovery`);
}

async function generationIsFresh(sessionId, ownerGeneration) {
  const names = await readdir(instancesDir);
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    try {
      const instance = JSON.parse(await readFile(join(instancesDir, name), "utf8"));
      const age = Date.now() - Date.parse(instance.updatedAt);
      if (
        instance.sessionId === sessionId &&
        instance.generation === ownerGeneration &&
        Number.isFinite(age) &&
        age >= 0 &&
        age <= 15_000
      ) {
        return true;
      }
    } catch {
      // Concurrent heartbeat replacement cannot prove a generation is live.
    }
  }
  return false;
}

async function acquireRecoveryLock(name) {
  const path = recoveryLockPath(name);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await writeFile(
        path,
        `${JSON.stringify({
          sessionId: session.sessionId,
          generation,
          updatedAt: new Date().toISOString(),
        })}\n`,
        { mode: 0o600, flag: "wx" },
      );
      return true;
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      try {
        const lock = JSON.parse(await readFile(path, "utf8"));
        if (await generationIsFresh(lock.sessionId, lock.generation)) return false;
      } catch (readError) {
        if (readError?.code !== "ENOENT") {
          // A malformed lock cannot prove that another live generation owns recovery.
        }
      }
      const stalePath = `${path}.${generation}.stale`;
      try {
        await rename(path, stalePath);
        await rm(stalePath, { force: true });
      } catch (renameError) {
        if (renameError?.code !== "ENOENT") throw renameError;
      }
    }
  }
  return false;
}

async function recoverStalePendingRequests() {
  const names = (await readdir(pendingDir))
    .filter((name) => name.endsWith(".json"))
    .sort();
  for (const name of names) {
    const pendingPath = join(pendingDir, name);
    let request;
    try {
      request = JSON.parse(await readFile(pendingPath, "utf8"));
    } catch {
      continue;
    }
    const target = request.target ?? {};
    if (
      target.sessionId !== session.sessionId ||
      !target.generation ||
      target.generation === generation ||
      (await generationIsFresh(target.sessionId, target.generation))
    ) {
      continue;
    }

    const processingPath = join(processingDir, name);
    try {
      await rename(pendingPath, processingPath);
    } catch {
      continue;
    }
    diagnostics.log("recovery.pending_claimed", {
      requestId: request.id,
      kind: request.kind,
      ownerGeneration: target.generation,
    });
    await writeJson(stagePath(processingDir, name), {
      ownerGeneration: target.generation,
      stage: "claimed",
      fingerprint: requestFingerprint(request),
      updatedAt: new Date().toISOString(),
    });
  }
}

let recovering = false;
async function recoverStaleClaims() {
  if (recovering || pumping) return;
  recovering = true;
  try {
    await recoverStalePendingRequests();
    const names = (await readdir(processingDir))
      .filter((name) => name.endsWith(".json"))
      .sort();
    for (const name of names) {
      const processingPath = join(processingDir, name);
      let request;
      try {
        request = JSON.parse(await readFile(processingPath, "utf8"));
      } catch {
        continue;
      }
      const processingStagePath = stagePath(processingDir, name);
      let stage = { stage: "claimed", fingerprint: requestFingerprint(request) };
      try {
        stage = JSON.parse(await readFile(processingStagePath, "utf8"));
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
      const ownerGeneration =
        stage.ownerGeneration ?? request.target?.generation;
      if (
        stage.stage === "claimed" &&
        request.target?.sessionId !== session.sessionId
      ) {
        continue;
      }
      if (
        stage.stage !== "executed" &&
        ownerGeneration &&
        (await generationIsFresh(request.target?.sessionId, ownerGeneration))
      ) {
        continue;
      }
      if (!(await acquireRecoveryLock(name))) continue;
      diagnostics.log("recovery.locked", {
        requestId: request.id,
        kind: request.kind,
        stage: stage.stage,
        ownerGeneration,
      });

      const receiptBase = {
        id: request.id,
        dedupeKey: request.dedupeKey,
        sessionId: request.target?.sessionId,
        generation: ownerGeneration,
        recoveredByGeneration: generation,
        handledAt: new Date().toISOString(),
      };
      try {
        if (
          stage.stage === "claimed" &&
          request.target?.sessionId === session.sessionId
        ) {
          request.target.generation = generation;
          await writeJson(processingPath, request);
          await writeJson(processingStagePath, {
            ownerGeneration: generation,
            stage: "claimed",
            fingerprint: requestFingerprint(request),
            updatedAt: new Date().toISOString(),
          });
          await rm(processingStagePath, { force: true });
          await rename(processingPath, join(pendingDir, name));
          diagnostics.log("recovery.requeued", {
            requestId: request.id,
            kind: request.kind,
          });
        } else if (
          stage.stage === "executed" &&
          stage.fingerprint === requestFingerprint(request)
        ) {
          if (request.dedupeKey) {
            await writeJson(dedupePath(request.dedupeKey, request.target?.sessionId), {
              dedupeKey: request.dedupeKey,
              sessionId: request.target?.sessionId,
              kind: request.kind,
              fingerprint: stage.fingerprint,
              completedAt: new Date().toISOString(),
              result: stage.result,
            });
          }
          await writeJson(join(completedDir, name), {
            ...receiptBase,
            completedAt: new Date().toISOString(),
            status: "completed",
            recovered: true,
            deduplicated: false,
            result: stage.result,
          });
          await rm(join(failedDir, name), { force: true });
          await rm(processingPath, { force: true });
          await rm(processingStagePath, { force: true });
          diagnostics.log("recovery.completed", {
            requestId: request.id,
            kind: request.kind,
            delivery: stage.result?.delivery,
          });
        } else {
          const ambiguousSideEffect = stage.stage === "executing";
          const error =
            ambiguousSideEffect
              ? "extension exited while the request side effect was executing"
              : "request owner exited before the request could be delivered";
          const ambiguousResult = ambiguousSideEffect
            ? { ambiguousSideEffect: true, error }
            : undefined;
          if (ambiguousSideEffect && request.dedupeKey) {
            await writeJson(dedupePath(request.dedupeKey, request.target?.sessionId), {
              dedupeKey: request.dedupeKey,
              sessionId: request.target?.sessionId,
              kind: request.kind,
              fingerprint: requestFingerprint(request),
              completedAt: new Date().toISOString(),
              status: "ambiguous",
              result: ambiguousResult,
            });
          }
          await writeJson(join(failedDir, name), {
            ...receiptBase,
            status: "failed",
            ...(ambiguousSideEffect
              ? { ambiguousSideEffect: true, result: ambiguousResult }
              : {}),
            error,
          });
          await rm(processingPath, { force: true });
          await rm(processingStagePath, { force: true });
          diagnostics.log(
            ambiguousSideEffect ? "recovery.ambiguous" : "recovery.failed",
            {
              requestId: request.id,
              kind: request.kind,
              stage: stage.stage,
              error: { message: error },
            },
          );
        }
      } finally {
        await rm(recoveryLockPath(name), { force: true });
      }
    }
  } catch (error) {
    diagnostics.log("recovery.crashed", { error: errorDetails(error) });
    console.error(
      `session-inbox recovery failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  } finally {
    recovering = false;
  }
}

async function findDedupeReservation(request, currentName) {
  if (!request.dedupeKey) return undefined;
  const names = await readdir(processingDir);
  for (const name of names) {
    if (!name.endsWith(".json") || name === currentName) continue;
    try {
      const claimed = JSON.parse(await readFile(join(processingDir, name), "utf8"));
      if (
        claimed.target?.sessionId === session.sessionId &&
        claimed.dedupeKey === request.dedupeKey
      ) {
        return claimed;
      }
    } catch {
      // A concurrent claim transition cannot prove that the key is reserved.
    }
  }
  return undefined;
}

async function pump() {
  if (pumping || recovering) return;
  pumping = true;
  try {
    const names = (await readdir(pendingDir))
      .filter((name) => name.endsWith(".json"))
      .sort();
    for (const name of names) {
      const pendingPath = join(pendingDir, name);
      let request;
      try {
        request = JSON.parse(await readFile(pendingPath, "utf8"));
      } catch {
        continue;
      }
      if (!matchesTarget(request)) continue;

      const claimedPath = join(processingDir, name);
      const claimedStagePath = stagePath(processingDir, name);
      try {
        await rename(pendingPath, claimedPath);
      } catch {
        continue;
      }
      diagnostics.log("request.claimed", {
        requestId: request.id,
        kind: request.kind,
        fingerprint: requestFingerprint(request),
        hasDedupeKey: Boolean(request.dedupeKey),
      });
      await writeJson(claimedStagePath, {
        ownerGeneration: generation,
        stage: "claimed",
        fingerprint: requestFingerprint(request),
        updatedAt: new Date().toISOString(),
      });

      const receiptBase = {
        id: request.id,
        dedupeKey: request.dedupeKey,
        sessionId: session.sessionId,
        tmuxSession,
        generation,
        hostPid: process.ppid,
        handledAt: new Date().toISOString(),
      };
      let removeClaim = true;
      let operationCompleted = false;
      let sideEffectStarted = false;
      let result;
      try {
        let deduplicated = false;
        if (request.dedupeKey) {
          try {
            const record = JSON.parse(
              await readFile(dedupePath(request.dedupeKey), "utf8"),
            );
            if (
              record.sessionId !== session.sessionId ||
              record.kind !== request.kind ||
              record.fingerprint !== requestFingerprint(request)
            ) {
              throw new Error("dedupe key was reused for a different request");
            }
            if (record.status === "ambiguous") {
              throw ambiguousSideEffectError(
                record.result?.error ?? "prior request side effect is ambiguous",
                record.result,
              );
            }
            result = record.result;
            deduplicated = true;
            diagnostics.log("request.deduplicated", {
              requestId: request.id,
              kind: request.kind,
              delivery: result?.delivery,
            });
          } catch (error) {
            if (error?.code !== "ENOENT") throw error;
          }
        }
        if (!deduplicated) {
          const reservation = await findDedupeReservation(request, name);
          if (reservation) {
            if (requestFingerprint(reservation) !== requestFingerprint(request)) {
              throw new Error("dedupe key was reused for a different request");
            }
            throw new Error("dedupe key has an unfinished prior request");
          }
          await writeJson(claimedStagePath, {
            ownerGeneration: generation,
            stage: "executing",
            fingerprint: requestFingerprint(request),
            updatedAt: new Date().toISOString(),
          });
          sideEffectStarted = true;
          diagnostics.log("request.executing", {
            requestId: request.id,
            kind: request.kind,
          });
          result = await execute(request);
          operationCompleted = true;
          removeClaim = false;
          await writeJson(claimedStagePath, {
            ownerGeneration: generation,
            stage: "executed",
            fingerprint: requestFingerprint(request),
            result,
            updatedAt: new Date().toISOString(),
          });
          if (request.dedupeKey) {
            await writeJson(dedupePath(request.dedupeKey), {
              dedupeKey: request.dedupeKey,
              sessionId: session.sessionId,
              kind: request.kind,
              fingerprint: requestFingerprint(request),
              completedAt: new Date().toISOString(),
              status: "completed",
              result,
            });
          }
        }
        await writeJson(join(completedDir, name), {
          ...receiptBase,
          completedAt: new Date().toISOString(),
          status: "completed",
          deduplicated,
          result,
        });
        removeClaim = true;
        diagnostics.log("request.completed", {
          requestId: request.id,
          kind: request.kind,
          deduplicated,
          delivery: result?.delivery,
          idleDelivery: result?.idleDelivery,
          objectiveSet: result?.objectiveSet,
          objectiveStatus: result?.objectiveStatus,
          activation: result?.activation,
          compacted: result?.compacted,
          continuationAccepted: result?.continuationAccepted,
          continuationDelivery: result?.continuationDelivery,
          reloadRequested: result?.reloadRequested,
        });
        if (request.kind === "reload-extensions") {
          await rm(claimedPath, { force: true });
          await rm(claimedStagePath, { force: true });
          removeClaim = false;
          diagnostics.log("extensions.reload_started", { requestId: request.id });
          await session.rpc.extensions.reload();
          diagnostics.log("extensions.reload_returned", { requestId: request.id });
        }
      } catch (error) {
        const ambiguousSideEffect =
          error?.definitiveNoSideEffect !== true &&
          ((sideEffectStarted && !operationCompleted) ||
            error?.ambiguousSideEffect === true);
        if (ambiguousSideEffect) {
          removeClaim = false;
          result =
            error?.result ??
            {
              ambiguousSideEffect: true,
              error: error instanceof Error ? error.message : String(error),
            };
          if (request.dedupeKey) {
            await writeJson(dedupePath(request.dedupeKey), {
              dedupeKey: request.dedupeKey,
              sessionId: session.sessionId,
              kind: request.kind,
              fingerprint: requestFingerprint(request),
              completedAt: new Date().toISOString(),
              status: "ambiguous",
              result,
            });
          }
        }
        await writeJson(join(failedDir, name), {
          ...receiptBase,
          status: "failed",
          ...(ambiguousSideEffect ? { ambiguousSideEffect: true } : {}),
          ...(operationCompleted ? { sideEffectCompleted: true, result } : {}),
          ...(!operationCompleted && ambiguousSideEffect ? { result } : {}),
          error: error instanceof Error ? error.message : String(error),
        });
        diagnostics.log("request.failed", {
          requestId: request.id,
          kind: request.kind,
          sideEffectStarted,
          operationCompleted,
          ambiguousSideEffect,
          error: errorDetails(error),
        });
        if (ambiguousSideEffect) removeClaim = true;
      } finally {
        if (removeClaim) {
          await rm(claimedPath, { force: true });
          await rm(claimedStagePath, { force: true });
        }
      }

      // A send or command may have started or replaced the foreground turn.
      break;
    }
  } catch (error) {
    diagnostics.log("pump.crashed", { error: errorDetails(error) });
    console.error(
      `session-inbox pump failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  } finally {
    pumping = false;
  }
}

await writeHeartbeat();
setInterval(() => void writeHeartbeat(), 5_000);
setInterval(() => void recoverStaleClaims(), 5_000);
setInterval(() => void pump(), 500);
setTimeout(() => void recoverStaleClaims(), 1_000);
setTimeout(() => void pump(), 250);
