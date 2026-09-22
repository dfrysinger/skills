import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const IDENTITY_LOOKUP_TIMEOUT_MS = 2_000;

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
  return snapshot.workspace?.name?.trim() || undefined;
}

export async function preferredAgentName(session) {
  try {
    const tmuxSession = await currentTmuxSession();
    if (tmuxSession) return tmuxSession;
  } catch {
    // A stale tmux environment must not block the portable session-name fallback.
  }
  return currentSessionName(session);
}
