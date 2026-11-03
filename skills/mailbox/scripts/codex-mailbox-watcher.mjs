// Long-lived Codex mailbox watcher. The Agent Stack launcher owns this process,
// the app-server, and the TUI in one Windows Job Object. It takes no argv so
// endpoint capability tokens remain launch-scoped environment data.
import {
  CODEX_ENV,
  CodexEnvironmentError,
  codexGeneration,
  createCodexWakeupAdapter,
  isProcessAlive,
  readCodexEnvironment,
} from "./codex-mailbox-adapter.mjs";
import { realpathSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { MailboxConfigurationError, createConfiguredMailbox } from "./mailbox-core.mjs";

const DEFAULT_INTERVAL_MS = 1_000;
const DEFAULT_LIVENESS_MS = 1_000;

export async function runCodexWatcher({
  env = process.env,
  createMailbox = createConfiguredMailbox,
  mailboxOptions = {},
  signal,
  intervalMs = DEFAULT_INTERVAL_MS,
  livenessMs = DEFAULT_LIVENESS_MS,
  isAlive = isProcessAlive,
  adapterOptions = {},
} = {}) {
  const config = readCodexEnvironment(env);
  const generation = codexGeneration(config);
  if (!isAlive(config.launcherPid)) return { generation, started: false };
  const adapter = createCodexWakeupAdapter({
    ...config,
    isAlive,
    ...adapterOptions,
  });
  const mailbox = createMailbox({ ...mailboxOptions, wakeupAdapters: { codex: adapter } });
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });
  const livenessTimer = setInterval(() => {
    if (!isAlive(config.launcherPid)) abort();
  }, livenessMs);
  try {
    await mailbox.watch(config.address, {
      generation,
      intervalMs,
      signal: controller.signal,
    });
  } finally {
    clearInterval(livenessTimer);
    signal?.removeEventListener("abort", abort);
  }
  return { generation, started: true };
}

async function main() {
  const controller = new AbortController();
  for (const name of ["SIGINT", "SIGTERM", "SIGBREAK"]) {
    process.on(name, () => controller.abort());
  }
  try {
    await runCodexWatcher({ signal: controller.signal });
  } catch (error) {
    const safe =
      error instanceof CodexEnvironmentError || error instanceof MailboxConfigurationError
        ? error.message
        : `unexpected error ${error?.code ?? error?.name ?? ""}`.trim();
    process.stderr.write(`codex-mailbox-watcher: ${safe}\n`);
    process.exitCode = 1;
  }
}

function isMainModule(importMetaUrl, argvPath = process.argv[1]) {
  if (!argvPath) return false;
  try {
    return realpathSync(resolve(argvPath)) === realpathSync(fileURLToPath(importMetaUrl));
  } catch {
    return false;
  }
}

if (isMainModule(import.meta.url)) {
  await main();
}
