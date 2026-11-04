import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const IDENTITY_LOOKUP_TIMEOUT_MS = 2_000;

export async function isForegroundSession(session) {
  // The joined SDK session has no public foreground accessor; use its existing
  // parent transport for the same read-only RPC as getForegroundSessionId().
  if (typeof session.connection?.sendRequest !== "function") {
    throw new Error("foreground session lookup is unavailable");
  }
  let timeout;
  const foreground = await Promise.race([
    session.connection.sendRequest("session.getForeground", {}),
    new Promise((_, reject) => {
      timeout = setTimeout(
        () => reject(new Error("foreground session lookup timed out")),
        IDENTITY_LOOKUP_TIMEOUT_MS,
      );
    }),
  ]).finally(() => clearTimeout(timeout));
  if (
    !foreground ||
    typeof foreground !== "object" ||
    Array.isArray(foreground) ||
    (foreground.sessionId !== undefined &&
      (typeof foreground.sessionId !== "string" || !foreground.sessionId))
  ) {
    throw new Error("invalid foreground session response");
  }
  return Boolean(session.sessionId && foreground.sessionId === session.sessionId);
}

export async function currentTmuxSession() {
  if (!process.env.TMUX_PANE) return undefined;
  const { stdout } = await execFileAsync(
    "tmux",
    [
      "display-message",
      "-p",
      "-t",
      process.env.TMUX_PANE,
      "#{session_name}",
    ],
    { timeout: IDENTITY_LOOKUP_TIMEOUT_MS },
  );
  return stdout.trim() || undefined;
}

export async function currentSessionName(session) {
  let timeout;
  const snapshot = await Promise.race([
    session.rpc.metadata.snapshot(),
    new Promise((_, reject) => {
      timeout = setTimeout(
        () => reject(new Error("session metadata identity lookup timed out")),
        IDENTITY_LOOKUP_TIMEOUT_MS,
      );
    }),
  ]).finally(() => clearTimeout(timeout));
  if (snapshot.workspace?.user_named !== true) return undefined;
  return snapshot.workspace.name?.trim() || undefined;
}

export async function preferredAgentName(session) {
  if (!(await isForegroundSession(session))) return undefined;
  try {
    const tmuxSession = await currentTmuxSession();
    if (tmuxSession) return tmuxSession;
  } catch {
    // A stale tmux environment must not block the portable session-name fallback.
  }
  return currentSessionName(session);
}
