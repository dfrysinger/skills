import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const IDENTITY_LOOKUP_TIMEOUT_MS = 2_000;

export function configuredCopilotName(environment = process.env) {
  const address = environment.MAILBOX_SELF_ADDRESS;
  if (address === undefined) return undefined;
  const bare = /^([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/.exec(address);
  if (bare) return bare[1];
  const qualified =
    /^(copilot|claude|codex):([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/.exec(address);
  if (!qualified) {
    throw new Error(
      "MAILBOX_SELF_ADDRESS must be a canonical local provider address",
    );
  }
  return qualified[1] === "copilot" ? qualified[2] : undefined;
}

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

export async function preferredAgentName(session, managedName) {
  if (!(await isForegroundSession(session))) return undefined;
  if (managedName) return managedName;
  try {
    const tmuxSession = await currentTmuxSession();
    if (tmuxSession) return tmuxSession;
  } catch {
    // A stale tmux environment must not block the portable session-name fallback.
  }
  return currentSessionName(session);
}
