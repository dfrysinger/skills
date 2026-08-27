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
const commandsDir = join(root, "commands");
const configuredConfirmationTimeoutMs = Number.parseInt(
  process.env.COPILOT_SESSION_INBOX_CONFIRM_TIMEOUT_MS ?? "10000",
  10,
);
const confirmationTimeoutMs =
  Number.isFinite(configuredConfirmationTimeoutMs) &&
  configuredConfirmationTimeoutMs > 0
    ? configuredConfirmationTimeoutMs
    : 10_000;

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
let idleReady = false;
let idleEpoch = 0;

await Promise.all(
  [
    pendingDir,
    processingDir,
    completedDir,
    failedDir,
    instancesDir,
    dedupeDir,
    commandsDir,
  ].map((dir) => mkdir(dir, { recursive: true, mode: 0o700 })),
);
diagnostics.log("extension.started", {
  extensionPath: import.meta.url,
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
      updatedAt: new Date().toISOString(),
    });
  } finally {
    heartbeatRefreshing = false;
  }
}

async function sendAndConfirm({ prompt, mode = "immediate", agentMode }) {
  let resolveDelivered;
  const delivered = new Promise((resolve) => {
    resolveDelivered = resolve;
  });
  const unsubscribe = session.on("user.message", (event) => {
    if (event.data.content === prompt) resolveDelivered(event);
  });
  try {
    diagnostics.log("sdk.send.started", { mode, agentMode });
    const messageId = await session.send({
      prompt,
      mode,
      ...(agentMode ? { agentMode } : {}),
    });
    const event = await Promise.race([
      delivered,
      new Promise((resolve) =>
        setTimeout(() => resolve(undefined), confirmationTimeoutMs),
      ),
    ]);
    diagnostics.log(event ? "sdk.send.confirmed" : "sdk.send.unconfirmed", {
      messageId,
      delivery: event?.data.delivery,
    });
    return {
      messageId,
      delivery: event?.data.delivery ?? "unconfirmed",
      idleDelivery: event?.data.delivery === "idle",
    };
  } finally {
    unsubscribe();
  }
}

async function execute(request) {
  switch (request.kind) {
    case "send":
      return sendAndConfirm({
        prompt: request.prompt,
        mode: request.mode,
        agentMode: request.agentMode,
      });
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
      let continuationDelivered;
      let continuationDelivery;
      let continuationError;
      if (request.continuationPrompt) {
        try {
          const processing = await session.rpc.metadata.isProcessing();
          if (processing.processing) {
            throw new Error("session remained busy after compaction");
          }
          const continuation = await sendAndConfirm({
            prompt: request.continuationPrompt,
            mode: "immediate",
          });
          continuationDelivered = continuation.idleDelivery;
          if (!continuation.idleDelivery) {
            continuationError = `SDK delivered the continuation as ${
              continuation.delivery ?? "unknown"
            } instead of idle`;
          }
          continuationDelivery = continuation.delivery;
        } catch (error) {
          continuationDelivered = false;
          continuationError = error instanceof Error ? error.message : String(error);
        }
      }
      return {
        compacted: true,
        tokensRemoved: result.tokensRemoved,
        messagesRemoved: result.messagesRemoved,
        ...(continuationDelivered === undefined ? {} : { continuationDelivered }),
        ...(continuationDelivery === undefined ? {} : { continuationDelivery }),
        ...(continuationError ? { continuationError } : {}),
      };
    }
    case "new-session": {
      const markerPath = commandMarkerPath(request.id);
      await writeJson(markerPath, {
        requestId: request.id,
        sessionId: session.sessionId,
        hostPid: process.ppid,
        startedAt: new Date().toISOString(),
        promptSha256: createHash("sha256").update(request.prompt).digest("hex"),
      });
      const result = await session.rpc.commands.enqueue({
        command: `/new ${request.prompt}`,
      });
      if (!result.queued) {
        await rm(markerPath, { force: true });
        throw new Error("the local session did not accept the /new command");
      }
      return { commandQueued: true };
    }
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

function commandMarkerPath(id) {
  return join(commandsDir, `${id}.json`);
}

function ambiguousSideEffectError(message, result) {
  const error = new Error(message);
  error.ambiguousSideEffect = true;
  error.result = result;
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
  if (pumping || recovering || !idleReady) return;
  pumping = true;
  try {
    const [processing, activity] = await Promise.all([
      session.rpc.metadata.isProcessing(),
      session.rpc.metadata.activity(),
    ]);
    if (processing.processing || activity.hasActiveWork) {
      idleReady = false;
      return;
    }

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
          const epoch = idleEpoch;
          const idleWasReady = idleReady;
          const [processingNow, activityNow, pendingNow] = await Promise.all([
            session.rpc.metadata.isProcessing(),
            session.rpc.metadata.activity(),
            session.rpc.queue.pendingItems(),
          ]);
          if (
            !idleReady ||
            epoch !== idleEpoch ||
            processingNow.processing ||
            activityNow.hasActiveWork ||
            pendingNow.items.length > 0
          ) {
            idleReady = false;
            removeClaim = false;
            diagnostics.log("request.deferred", {
              requestId: request.id,
              kind: request.kind,
              idleReady: idleWasReady,
              idleEpochChanged: epoch !== idleEpoch,
              processing: processingNow.processing,
              activeWork: activityNow.hasActiveWork,
              pendingQueueItems: pendingNow.items.length,
            });
            await rename(claimedPath, pendingPath);
            await rm(claimedStagePath, { force: true });
            break;
          }
          idleReady = false;
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
          compacted: result?.compacted,
          continuationDelivery: result?.continuationDelivery,
          commandQueued: result?.commandQueued,
        });
        if (request.kind === "new-session") {
          try {
            await rm(commandMarkerPath(request.id), { force: true });
          } catch (error) {
            console.error(
              `session-inbox could not remove completed command marker: ${
                error instanceof Error ? error.message : String(error)
              }`,
            );
          }
        }
      } catch (error) {
        const ambiguousSideEffect =
          (sideEffectStarted && !operationCompleted) ||
          error?.ambiguousSideEffect === true;
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
        void armAfterIdleEvent();
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

async function armAfterIdleEvent() {
  await new Promise((resolve) => setTimeout(resolve, 250));
  const [processing, activity, pending] = await Promise.all([
    session.rpc.metadata.isProcessing(),
    session.rpc.metadata.activity(),
    session.rpc.queue.pendingItems(),
  ]);
  if (processing.processing || activity.hasActiveWork || pending.items.length > 0) return;
  idleReady = true;
  void pump();
}

session.on("user.message", () => {
  idleEpoch += 1;
  idleReady = false;
  diagnostics.log("session.user_message", { idleEpoch });
});
session.on("session.idle", () => {
  diagnostics.log("session.idle", { idleEpoch });
  void armAfterIdleEvent();
});

await writeHeartbeat();
setInterval(() => void writeHeartbeat(), 5_000);
setInterval(() => void recoverStaleClaims(), 5_000);
setInterval(() => void pump(), 500);
setTimeout(() => void recoverStaleClaims(), 1_000);
setTimeout(() => void armAfterIdleEvent(), 2_000);
