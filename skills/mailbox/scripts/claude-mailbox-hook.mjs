// Claude Code SessionStart hook launcher. Spawns the long-lived mailbox watcher
// detached, with the private Claude environment inherited (never argv), and
// returns immediately. Startup, /clear, /compact and in-process /resume all
// re-fire this hook inside the same Claude process; the shared watcher lock
// makes same-generation re-fires exit.
//
// Register as a SessionStart command hook, for example:
//   node "<repo>/skills/mailbox/scripts/claude-mailbox-hook.mjs"
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { ClaudeEnvironmentError, isMainModule, readClaudeEnvironment } from "./claude-mailbox-adapter.mjs";

export const defaultWatcherPath = fileURLToPath(
  new URL("./claude-mailbox-watcher.mjs", import.meta.url),
);
const STDIN_DRAIN_LIMIT_MS = 1_000;

export function launchClaudeWatcher({
  env = process.env,
  spawnProcess = spawn,
  execPath = process.execPath,
  watcherPath = defaultWatcherPath,
} = {}) {
  try {
    readClaudeEnvironment(env);
  } catch (error) {
    if (error instanceof ClaudeEnvironmentError) {
      return { started: false, reason: error.message };
    }
    throw error;
  }
  try {
    const child = spawnProcess(execPath, [watcherPath], {
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env,
    });
    child.on?.("error", () => {});
    child.unref?.();
    return { started: true, pid: child.pid };
  } catch (error) {
    return { started: false, reason: `watcher spawn failed: ${error?.code ?? "UNKNOWN"}` };
  }
}

function main() {
  const outcome = launchClaudeWatcher();
  if (!outcome.started) {
    process.stderr.write(`claude-mailbox-hook: watcher not started: ${outcome.reason}\n`);
  }
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    process.stdout.write("{}\n", () => process.exit(0));
  };
  const timer = setTimeout(finish, STDIN_DRAIN_LIMIT_MS);
  timer.unref();
  process.stdin.on("error", finish);
  process.stdin.on("end", finish);
  process.stdin.on("close", finish);
  process.stdin.resume();
}

if (isMainModule(import.meta.url)) main();
