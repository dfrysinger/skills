// Long-lived Claude mailbox watcher. Started detached by the SessionStart hook
// launcher with the Claude process environment inherited. Takes no argv: the
// messaging token must never appear on a command line.
//
// The watcher lock generation is a non-secret SHA-256 of the messaging socket
// address. A re-fired hook for the same Claude process exits through the shared
// lock; a new socket (new Claude process) waits for the old owner to die or
// release the lock.
import {
  ClaudeEnvironmentError,
  claudeSocketGeneration,
  createClaudeWakeupAdapter,
  isMainModule,
  isProcessAlive,
  readClaudeEnvironment,
} from "./claude-mailbox-adapter.mjs";
import { MailboxConfigurationError, createConfiguredMailbox } from "./mailbox-core.mjs";

const DEFAULT_INTERVAL_MS = 1_000;
const DEFAULT_LIVENESS_MS = 1_000;

export async function runClaudeWatcher({
  env = process.env,
  createMailbox = createConfiguredMailbox,
  mailboxOptions = {},
  signal,
  intervalMs = DEFAULT_INTERVAL_MS,
  livenessMs = DEFAULT_LIVENESS_MS,
  isAlive = isProcessAlive,
  adapterOptions = {},
} = {}) {
  const config = readClaudeEnvironment(env);
  const generation = claudeSocketGeneration(config.socket);
  if (!isAlive(config.claudePid)) return { generation, started: false };

  const adapter = createClaudeWakeupAdapter({
    address: config.address,
    socket: config.socket,
    token: config.token,
    claudePid: config.claudePid,
    isAlive,
    ...adapterOptions,
  });
  const mailbox = createMailbox({ ...mailboxOptions, wakeupAdapters: { claude: adapter } });

  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });
  const livenessTimer = setInterval(() => {
    if (!isAlive(config.claudePid)) abort();
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
    await runClaudeWatcher({ signal: controller.signal });
  } catch (error) {
    const safe =
      error instanceof ClaudeEnvironmentError || error instanceof MailboxConfigurationError
        ? error.message
        : `unexpected error ${error?.code ?? error?.name ?? ""}`.trim();
    process.stderr.write(`claude-mailbox-watcher: ${safe}\n`);
    process.exitCode = 1;
  }
}

if (isMainModule(import.meta.url)) await main();
