import { execFile, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  copyFile,
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import {
  createDiagnosticLogger,
  errorDetails,
} from "../../../extensions/session-inbox/diagnostics.mjs";

const execFileAsync = promisify(execFile);
const RETRYABLE_FILE_ERRORS = new Set(["EACCES", "EBUSY", "EPERM"]);

export const POKE_UNVERIFIED = 3;
export const POKE_NO_ACTIVE_COPILOT = 4;

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function validateName(name, label = "mailbox name") {
  if (
    typeof name !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(name)
  ) {
    throw new Error(`${label} must contain only letters, numbers, dot, underscore, and hyphen`);
  }
  return name;
}

async function pathExists(path) {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function atomicWrite(path, content, mode = 0o600) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporaryPath = join(
    dirname(path),
    `.${basename(path)}.${process.pid}.${randomBytes(4).toString("hex")}.tmp`,
  );
  try {
    await writeFile(temporaryPath, content, { encoding: "utf8", mode });
    await rename(temporaryPath, path);
  } finally {
    await rm(temporaryPath, { force: true });
  }
}

async function renameWithRetries(source, destination) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      await rename(source, destination);
      return;
    } catch (error) {
      if (!RETRYABLE_FILE_ERRORS.has(error?.code) || attempt >= 9) throw error;
      await sleep(200);
    }
  }
}

async function runNode(script, args, env) {
  const nodeExecutable = process.env.COPILOT_MAILBOX_NODE ?? "node";
  const child = spawn(nodeExecutable, [script, ...args], {
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  return new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (code, signal) => {
      resolve({ code, signal, stdout, stderr });
    });
  });
}

function compactTimestamp(date = new Date()) {
  return date.toISOString().replaceAll(/[-:.]/g, "").replace("Z", "Z-");
}

export function defaultMailboxRoot() {
  return process.env.MAILBOX_ROOT ?? join(homedir(), ".copilot", "mailbox");
}

export function defaultStateRoot() {
  return process.env.MAILBOX_STATE_ROOT ?? join(homedir(), ".copilot", "mailbox-state");
}

export async function resolveOwnName(explicitName) {
  if (explicitName) return validateName(explicitName, "agent name");
  if (process.env.COPILOT_AGENT_NAME) {
    return validateName(process.env.COPILOT_AGENT_NAME, "COPILOT_AGENT_NAME");
  }
  if (!process.env.TMUX_PANE) return undefined;
  try {
    const { stdout } = await execFileAsync("tmux", [
      "display-message",
      "-p",
      "-t",
      process.env.TMUX_PANE,
      "#{session_name}",
    ]);
    const name = stdout.trim();
    return name ? validateName(name, "tmux session name") : undefined;
  } catch {
    return undefined;
  }
}

export function createMailbox(options = {}) {
  const mailboxRoot = options.mailboxRoot ?? defaultMailboxRoot();
  const stateRoot = options.stateRoot ?? defaultStateRoot();
  const requestCli =
    options.requestCli ??
    join(
      dirname(fileURLToPath(import.meta.url)),
      "../../../extensions/session-inbox/request.mjs",
    );
  const diagnostics = createDiagnosticLogger(stateRoot, "mailbox.jsonl", {
    component: "mailbox",
    pid: process.pid,
  });
  const attachmentObservations = new Map();

  function mailboxDirectory(name, state) {
    return join(mailboxRoot, validateName(name), state);
  }

  async function attachmentsAreReady(name, envelope, requireStableAttachments) {
    if (!Array.isArray(envelope.attachments)) return false;
    let ready = true;
    for (const attachment of envelope.attachments) {
      if (
        typeof attachment !== "string" ||
        basename(attachment) !== attachment ||
        attachment === "." ||
        attachment === ".."
      ) {
        return false;
      }
      const path = join(mailboxDirectory(name, "pending"), envelope.id, attachment);
      try {
        const metadata = await stat(path);
        if (!metadata.isFile()) return false;
        if (requireStableAttachments) {
          const signature = `${metadata.size}:${metadata.mtimeMs}`;
          if (attachmentObservations.get(path) !== signature) ready = false;
          attachmentObservations.set(path, signature);
        }
      } catch (error) {
        if (error?.code !== "ENOENT" && !RETRYABLE_FILE_ERRORS.has(error?.code)) {
          throw error;
        }
        ready = false;
      }
    }
    return ready;
  }

  async function pendingEnvelopes(
    name,
    { requireStableAttachments = false } = {},
  ) {
    const directory = mailboxDirectory(name, "pending");
    let names;
    try {
      names = await readdir(directory);
    } catch (error) {
      if (error?.code === "ENOENT") return [];
      throw error;
    }
    const envelopes = [];
    for (const filename of names.filter((entry) => entry.endsWith(".json")).sort()) {
      const path = join(directory, filename);
      try {
        const envelope = JSON.parse(await readFile(path, "utf8"));
        if (envelope.id !== filename.slice(0, -5) || envelope.to?.name !== name) {
          diagnostics.log("envelope.invalid", {
            mailbox: name,
            path,
            error: { message: "envelope identity does not match its path" },
          });
          continue;
        }
        if (
          !(await attachmentsAreReady(
            name,
            envelope,
            requireStableAttachments,
          ))
        ) {
          diagnostics.log("envelope.attachments_pending", {
            mailbox: name,
            envelopeId: envelope.id,
            attachmentCount: Array.isArray(envelope.attachments)
              ? envelope.attachments.length
              : undefined,
          });
          continue;
        }
        envelopes.push({ envelope, path });
      } catch (error) {
        diagnostics.log("envelope.unreadable", {
          mailbox: name,
          path,
          error: errorDetails(error),
        });
      }
    }
    return envelopes;
  }

  async function pendingEnvelopeIds(name) {
    const directory = mailboxDirectory(name, "pending");
    try {
      return new Set(
        (await readdir(directory))
          .filter((entry) => entry.endsWith(".json"))
          .map((entry) => entry.slice(0, -5)),
      );
    } catch (error) {
      if (error?.code === "ENOENT") return new Set();
      throw error;
    }
  }

  async function send({
    recipient,
    sender = "unknown",
    summary,
    message,
    files = [],
    wake = true,
    wait = false,
  }) {
    validateName(recipient, "recipient");
    validateName(sender, "sender");
    if (!summary) throw new Error("summary is required");
    if (!message) throw new Error("message is required");

    const id = `${compactTimestamp()}${process.pid}-${randomBytes(6).toString("hex")}`;
    const pending = mailboxDirectory(recipient, "pending");
    const envelopePath = join(pending, `${id}.json`);
    const attachmentDirectory = join(pending, id);
    const attachmentNames = [];
    let envelope;
    await mkdir(pending, { recursive: true, mode: 0o700 });
    try {
      if (files.length > 0) await mkdir(attachmentDirectory, { mode: 0o700 });
      for (const source of files) {
        let destinationName = basename(source);
        if (!destinationName) throw new Error(`attachment has no filename: ${source}`);
        if (attachmentNames.includes(destinationName)) {
          const dot = destinationName.lastIndexOf(".");
          const stem = dot > 0 ? destinationName.slice(0, dot) : destinationName;
          const extension = dot > 0 ? destinationName.slice(dot) : "";
          let suffix = 2;
          while (attachmentNames.includes(`${stem}-${suffix}${extension}`)) suffix += 1;
          destinationName = `${stem}-${suffix}${extension}`;
        }
        await copyFile(source, join(attachmentDirectory, destinationName));
        attachmentNames.push(destinationName);
      }
      envelope = {
        id,
        from: { name: sender },
        to: { name: recipient },
        summary,
        message,
        attachments: attachmentNames,
        sent_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      };
      await atomicWrite(envelopePath, `${JSON.stringify(envelope, null, 2)}\n`);
      diagnostics.log("envelope.published", {
        envelopeId: id,
        sender,
        recipient,
        attachmentCount: attachmentNames.length,
      });
    } catch (error) {
      await rm(envelopePath, { force: true });
      await rm(attachmentDirectory, { recursive: true, force: true });
      diagnostics.log("envelope.publish_failed", {
        envelopeId: id,
        sender,
        recipient,
        error: errorDetails(error),
      });
      throw error;
    }

    let wakeup = { status: "skipped", detail: "wakeup disabled" };
    if (wake) {
      try {
        wakeup = await poke(recipient, { wait });
      } catch (error) {
        diagnostics.log("wakeup.failed", {
          mailbox: recipient,
          envelopeId: id,
          error: errorDetails(error),
        });
        wakeup = { status: "unverified", detail: error.message };
      }
    }
    return { envelope, envelopePath, wakeup };
  }

  async function check(name) {
    return pendingEnvelopes(validateName(name));
  }

  async function read(name, id) {
    validateName(name);
    validateName(id, "envelope id");
    const path = join(mailboxDirectory(name, "pending"), `${id}.json`);
    const envelope = JSON.parse(await readFile(path, "utf8"));
    if (envelope.id !== id || envelope.to?.name !== name) {
      throw new Error("envelope identity does not match the requested mailbox");
    }
    return {
      envelope,
      attachmentDirectory: join(mailboxDirectory(name, "pending"), id),
    };
  }

  async function acknowledge(name, id) {
    validateName(name);
    validateName(id, "envelope id");
    const pending = mailboxDirectory(name, "pending");
    const delivered = mailboxDirectory(name, "delivered");
    const envelopeSource = join(pending, `${id}.json`);
    const attachmentSource = join(pending, id);
    const envelopeDestination = join(delivered, `${id}.json`);
    const attachmentDestination = join(delivered, id);
    await read(name, id);
    await mkdir(delivered, { recursive: true, mode: 0o700 });

    let movedAttachments = false;
    if (await pathExists(attachmentSource)) {
      await renameWithRetries(attachmentSource, attachmentDestination);
      movedAttachments = true;
    }
    try {
      await renameWithRetries(envelopeSource, envelopeDestination);
    } catch (error) {
      if (movedAttachments) {
        try {
          await renameWithRetries(attachmentDestination, attachmentSource);
        } catch (rollbackError) {
          diagnostics.log("envelope.ack_rollback_failed", {
            envelopeId: id,
            mailbox: name,
            error: errorDetails(rollbackError),
          });
        }
      }
      throw error;
    }
    diagnostics.log("envelope.acknowledged", { envelopeId: id, mailbox: name });
    return envelopeDestination;
  }

  async function list() {
    let mailboxes;
    try {
      mailboxes = await readdir(mailboxRoot, { withFileTypes: true });
    } catch (error) {
      if (error?.code === "ENOENT") return [];
      throw error;
    }
    const result = [];
    for (const entry of mailboxes.filter((candidate) => candidate.isDirectory())) {
      let name;
      try {
        name = validateName(entry.name);
      } catch {
        continue;
      }
      const pending = await countJson(mailboxDirectory(name, "pending"));
      const delivered = await countJson(mailboxDirectory(name, "delivered"));
      result.push({ name, pending, delivered });
    }
    return result.sort((left, right) => left.name.localeCompare(right.name));
  }

  async function countJson(directory) {
    try {
      return (await readdir(directory)).filter((entry) => entry.endsWith(".json")).length;
    } catch (error) {
      if (error?.code === "ENOENT") return 0;
      throw error;
    }
  }

  async function resumeHint(name) {
    const envelopes = await pendingEnvelopes(validateName(name));
    if (envelopes.length === 0) return "";
    return `You have ${envelopes.length} unread mailbox envelope(s) in ${join(
      mailboxRoot,
      name,
      "pending",
    )}. Run the mailbox check command before continuing other work.`;
  }

  function legacyWatermarkPath(name) {
    return join(stateRoot, "watermarks", `${validateName(name)}.txt`);
  }

  async function readLegacyWatermarks(name) {
    const result = [];
    for (const path of [legacyWatermarkPath(name)]) {
      try {
        const value = (await readFile(path, "utf8")).trim();
        if (value) result.push(value);
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
    return result;
  }

  function notificationDirectory(name) {
    return join(stateRoot, "notified", validateName(name));
  }

  async function notifiedIds(name, pendingIds) {
    const directory = notificationDirectory(name);
    let names = [];
    try {
      names = await readdir(directory);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    const result = new Set(names.filter((entry) => entry.endsWith(".notified")).map(
      (entry) => entry.slice(0, -".notified".length),
    ));
    for (const legacy of await readLegacyWatermarks(name)) result.add(legacy);
    for (const notified of result) {
      if (!pendingIds.has(notified)) {
        await rm(join(directory, `${notified}.notified`), { force: true });
      }
    }
    return result;
  }

  async function markNotified(name, ids) {
    const directory = notificationDirectory(name);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    await Promise.all(
      ids.map((id) =>
        atomicWrite(join(directory, `${id}.notified`), `${new Date().toISOString()}\n`),
      ),
    );
  }

  async function acquireNotificationClaim(name) {
    const path = join(stateRoot, "notifying", `${validateName(name)}.lock`);
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const handle = await open(path, "wx", 0o600);
        await handle.writeFile(
          `${JSON.stringify({
            pid: process.pid,
            name,
            startedAt: new Date().toISOString(),
          })}\n`,
        );
        await handle.close();
        return async () => rm(path, { force: true });
      } catch (error) {
        if (error?.code !== "EEXIST") throw error;
        let owner;
        try {
          owner = JSON.parse(await readFile(path, "utf8"));
        } catch {
          owner = undefined;
        }
        const age = Date.now() - Date.parse(owner?.startedAt);
        if (Number.isFinite(age) && age <= 60_000 && owner?.pid) {
          try {
            process.kill(owner.pid, 0);
            return undefined;
          } catch (ownerError) {
            if (ownerError?.code === "EPERM") return undefined;
            if (ownerError?.code !== "ESRCH") throw ownerError;
          }
        }
        await rm(path, { force: true });
      }
    }
    throw new Error(`could not acquire mailbox notification claim for ${name}`);
  }

  async function pokeWithoutClaim(
    name,
    { wait = false, requireStableAttachments = false } = {},
  ) {
    validateName(name);
    const allPendingIds = await pendingEnvelopeIds(name);
    const envelopes = await pendingEnvelopes(name, { requireStableAttachments });
    if (envelopes.length === 0) return { status: "empty" };
    const readyIds = new Set(envelopes.map(({ envelope }) => envelope.id));
    const notified = await notifiedIds(name, allPendingIds);
    const unnotified = envelopes.filter(({ envelope }) => !notified.has(envelope.id));
    if (unnotified.length === 0) {
      return { status: "already-poked", envelopeId: envelopes.at(-1).envelope.id };
    }
    const newest = unnotified.at(-1).envelope;

    const temporaryDirectory = join(stateRoot, "tmp");
    await mkdir(temporaryDirectory, { recursive: true, mode: 0o700 });
    const promptPath = join(
      temporaryDirectory,
      `mailbox-poke-${process.pid}-${randomBytes(4).toString("hex")}.txt`,
    );
    const marker = `[mb:${newest.id.slice(newest.id.lastIndexOf("-") + 1)}]`;
    await writeFile(promptPath, `check mailbox; skip if empty ${marker}`, {
      encoding: "utf8",
      mode: 0o600,
    });
    try {
      const result = await runNode(
        requestCli,
        [
          "send",
          "--target-name",
          name,
          "--prompt-file",
          promptPath,
          "--mode",
          "immediate",
          "--dedupe-key",
          `mailbox:immediate-v2:${name}:${newest.id}`,
          "--timeout",
          wait ? "35" : "15",
        ],
        {},
      );
      const accepted =
        result.stdout.includes('"messageAccepted":true') ||
        /"messageId":"[^"]+"/.test(result.stdout) ||
        /"delivery":"(?:idle|queued|steering)"/.test(result.stdout);
      if (result.code === 0 && accepted) {
        await markNotified(name, [...readyIds]);
        diagnostics.log("wakeup.accepted", {
          mailbox: name,
          envelopeId: newest.id,
        });
        return { status: "delivered", envelopeId: newest.id };
      }
      const targetUnavailable =
        result.code === 64 &&
        result.stderr.includes("no fresh session-inbox instance");
      diagnostics.log(targetUnavailable ? "wakeup.no_active_session" : "wakeup.unverified", {
        mailbox: name,
        envelopeId: newest.id,
        requestExitCode: result.code,
        requestSignal: result.signal,
        error: result.stderr ? { message: result.stderr.trim() } : undefined,
      });
      return {
        status: targetUnavailable ? "no-active-copilot" : "unverified",
        envelopeId: newest.id,
        detail: (result.stderr || result.stdout).trim(),
      };
    } finally {
      await rm(promptPath, { force: true });
    }
  }

  async function poke(
    name,
    { wait = false, requireStableAttachments = false } = {},
  ) {
    validateName(name);
    const release = await acquireNotificationClaim(name);
    if (!release) {
      diagnostics.log("wakeup.in_progress", { mailbox: name });
      return { status: "in-progress" };
    }
    try {
      return await pokeWithoutClaim(name, { wait, requireStableAttachments });
    } finally {
      await release();
    }
  }

  async function acquireWatcher(name) {
    validateName(name);
    const path = join(stateRoot, "watchers", `${name}.lock`);
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const handle = await open(path, "wx", 0o600);
        await handle.writeFile(
          `${JSON.stringify({
            pid: process.pid,
            name,
            startedAt: new Date().toISOString(),
          })}\n`,
        );
        await handle.close();
        return async () => rm(path, { force: true });
      } catch (error) {
        if (error?.code !== "EEXIST") throw error;
        let owner;
        try {
          owner = JSON.parse(await readFile(path, "utf8"));
        } catch {
          owner = undefined;
        }
        if (owner?.pid) {
          try {
            process.kill(owner.pid, 0);
            throw new Error(`mailbox watcher for ${name} is already running as pid ${owner.pid}`);
          } catch (ownerError) {
            if (ownerError?.code === "EPERM") {
              throw new Error(`mailbox watcher for ${name} is already running as pid ${owner.pid}`);
            }
            if (ownerError?.code !== "ESRCH") throw ownerError;
          }
        }
        await rm(path, { force: true });
      }
    }
    throw new Error(`could not acquire mailbox watcher for ${name}`);
  }

  async function watch(name, { intervalMs = 2_000, once = false, signal } = {}) {
    validateName(name);
    if (!Number.isFinite(intervalMs) || intervalMs < 100) {
      throw new Error("watch interval must be at least 100 ms");
    }
    const release = await acquireWatcher(name);
    diagnostics.log("watcher.started", { mailbox: name, intervalMs });
    try {
      do {
        try {
          await poke(name, { requireStableAttachments: true });
        } catch (error) {
          diagnostics.log("watcher.poll_failed", {
            mailbox: name,
            error: errorDetails(error),
          });
        }
        if (once) break;
        await new Promise((resolve) => {
          const onAbort = () => {
            clearTimeout(timer);
            resolve();
          };
          const timer = setTimeout(() => {
            signal?.removeEventListener("abort", onAbort);
            resolve();
          }, intervalMs);
          signal?.addEventListener("abort", onAbort, { once: true });
        });
      } while (!signal?.aborted);
    } finally {
      await release();
      diagnostics.log("watcher.stopped", { mailbox: name });
    }
  }

  return {
    mailboxRoot,
    stateRoot,
    acknowledge,
    check,
    list,
    poke,
    read,
    resumeHint,
    send,
    watch,
  };
}
