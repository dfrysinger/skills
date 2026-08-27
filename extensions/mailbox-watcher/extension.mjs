import { homedir } from "node:os";
import { join } from "node:path";

import { joinSession } from "@github/copilot-sdk/extension";

import { createDiagnosticLogger, errorDetails } from "../session-inbox/diagnostics.mjs";
import {
  currentSessionName,
  currentTmuxSession,
} from "../session-inbox/session-identity.mjs";
import { createMailbox } from "../../skills/mailbox/scripts/mailbox-core.mjs";

const stateRoot =
  process.env.MAILBOX_STATE_ROOT ?? join(homedir(), ".copilot", "mailbox-state");
const diagnostics = createDiagnosticLogger(
  stateRoot,
  `watcher-bootstrap-${process.pid}.jsonl`,
  { component: "mailbox-watcher", hostPid: process.ppid, pid: process.pid },
);
const configuredInterval = Number(process.env.MAILBOX_POLL_INTERVAL_MS ?? "2000");
const intervalMs =
  Number.isFinite(configuredInterval) && configuredInterval >= 100
    ? configuredInterval
    : 2_000;

let session;
try {
  session = await joinSession();
} catch (error) {
  diagnostics.log("watcher.start_failed", {
    phase: "joinSession",
    error: errorDetails(error),
  });
  throw error;
}

const mailbox = createMailbox();
let activeName;
let activeController;
let activeWatcher;
let refreshing = false;
let shuttingDown = false;
let identityInterval;

async function stopActiveWatcher() {
  if (!activeWatcher) return;
  activeController.abort();
  await activeWatcher;
  activeController = undefined;
  activeWatcher = undefined;
}

async function refreshIdentity() {
  if (refreshing || shuttingDown) return;
  refreshing = true;
  try {
    let tmuxSession;
    try {
      tmuxSession = await currentTmuxSession();
    } catch (error) {
      diagnostics.log("watcher.identity_failed", {
        sessionId: session.sessionId,
        identitySource: "tmux",
        error: errorDetails(error),
      });
    }
    let sessionName;
    try {
      sessionName = await currentSessionName(session);
    } catch (error) {
      diagnostics.log("watcher.identity_failed", {
        sessionId: session.sessionId,
        identitySource: "session-name",
        error: errorDetails(error),
      });
    }
    const nextName = tmuxSession ?? sessionName;
    if (nextName === activeName && activeWatcher) return;

    await stopActiveWatcher();
    diagnostics.log("watcher.identity_changed", {
      sessionId: session.sessionId,
      previousName: activeName,
      agentName: nextName,
      identitySource: tmuxSession ? "tmux" : sessionName ? "session-name" : undefined,
    });
    activeName = nextName;
    if (!activeName) return;

    activeController = new AbortController();
    const watcher = mailbox
      .watch(activeName, {
        intervalMs,
        signal: activeController.signal,
      })
      .catch((error) => {
        diagnostics.log("watcher.failed", {
          sessionId: session.sessionId,
          agentName: activeName,
          error: errorDetails(error),
        });
      });
    activeWatcher = watcher;
    void watcher.finally(() => {
      if (activeWatcher === watcher) activeWatcher = undefined;
    });
  } catch (error) {
    diagnostics.log("watcher.identity_failed", {
      sessionId: session.sessionId,
      error: errorDetails(error),
    });
  } finally {
    refreshing = false;
  }
}

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  if (identityInterval) clearInterval(identityInterval);
  diagnostics.log("watcher.shutdown", {
    sessionId: session.sessionId,
    signal,
  });
  await stopActiveWatcher();
  process.exit(0);
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => void shutdown(signal));
}

await refreshIdentity();
identityInterval = setInterval(() => void refreshIdentity(), 5_000);
