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
import { rmSync } from "node:fs";
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

export function parseMailboxAddress(address) {
  if (typeof address !== "string") {
    throw new Error("mailbox address must be a string");
  }
  const separator = address.indexOf("@");
  if (separator === -1) {
    const name = validateName(address, "mailbox address");
    return { address: name, name };
  }
  if (
    separator === 0 ||
    separator === address.length - 1 ||
    separator !== address.lastIndexOf("@")
  ) {
    throw new Error("mailbox address must be NAME or NAME@MACHINE");
  }
  const name = validateName(address.slice(0, separator), "mailbox agent");
  const machine = validateName(address.slice(separator + 1), "mailbox machine");
  return { address: `${name}@${machine}`, name, machine };
}

export function configuredMachineName(explicitMachine) {
  const machine = explicitMachine ?? process.env.COPILOT_AGENT_MACHINE;
  return machine
    ? validateName(machine, explicitMachine ? "machine name" : "COPILOT_AGENT_MACHINE")
    : undefined;
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
  const machineName =
    options.machineName === null
      ? undefined
      : configuredMachineName(options.machineName);
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

  function mailboxDirectory(address, state) {
    return join(mailboxRoot, parseMailboxAddress(address).address, state);
  }

  function localAddresses(name) {
    const agentName = validateName(name, "agent name");
    return [
      agentName,
      ...(machineName ? [`${agentName}@${machineName}`] : []),
    ];
  }

  function requireLocalAddress(address) {
    const parsed = parseMailboxAddress(address);
    if (parsed.machine && parsed.machine !== machineName) {
      throw new Error(
        `mailbox ${parsed.address} belongs to machine ${parsed.machine}`,
      );
    }
    return parsed;
  }

  async function attachmentsAreReady(address, envelope, requireStableAttachments) {
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
      const path = join(mailboxDirectory(address, "pending"), envelope.id, attachment);
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
    address,
    { requireStableAttachments = false } = {},
  ) {
    const mailboxAddress = parseMailboxAddress(address).address;
    const directory = mailboxDirectory(mailboxAddress, "pending");
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
        if (
          envelope.id !== filename.slice(0, -5) ||
          envelope.to?.name !== mailboxAddress
        ) {
          diagnostics.log("envelope.invalid", {
            mailbox: mailboxAddress,
            path,
            error: { message: "envelope identity does not match its path" },
          });
          continue;
        }
        if (
          !(await attachmentsAreReady(
            mailboxAddress,
            envelope,
            requireStableAttachments,
          ))
        ) {
          diagnostics.log("envelope.attachments_pending", {
            mailbox: mailboxAddress,
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
          mailbox: mailboxAddress,
          path,
          error: errorDetails(error),
        });
      }
    }
    return envelopes;
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
    const target = parseMailboxAddress(recipient);
    validateName(sender, "sender");
    if (!summary) throw new Error("summary is required");
    if (!message) throw new Error("message is required");

    const id = `${compactTimestamp()}${process.pid}-${randomBytes(6).toString("hex")}`;
    const pending = mailboxDirectory(target.address, "pending");
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
        to: { name: target.address },
        summary,
        message,
        attachments: attachmentNames,
        sent_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      };
      await atomicWrite(envelopePath, `${JSON.stringify(envelope, null, 2)}\n`);
      diagnostics.log("envelope.published", {
        envelopeId: id,
        sender,
        recipient: target.address,
        recipientMachine: target.machine,
        attachmentCount: attachmentNames.length,
      });
    } catch (error) {
      await rm(envelopePath, { force: true });
      await rm(attachmentDirectory, { recursive: true, force: true });
      diagnostics.log("envelope.publish_failed", {
        envelopeId: id,
        sender,
        recipient: target.address,
        recipientMachine: target.machine,
        error: errorDetails(error),
      });
      throw error;
    }

    let wakeup = { status: "skipped", detail: "wakeup disabled" };
    if (wake) {
      if (target.machine && target.machine !== machineName) {
        wakeup = {
          status: "remote-pending",
          detail: `waiting for mailbox watcher on ${target.machine}`,
        };
      } else {
        try {
          wakeup = await poke(target.address, {
            targetName: target.name,
            wait,
          });
        } catch (error) {
          diagnostics.log("wakeup.failed", {
            mailbox: target.address,
            envelopeId: id,
            error: errorDetails(error),
          });
          wakeup = { status: "unverified", detail: error.message };
        }
      }
    }
    return { envelope, envelopePath, wakeup };
  }

  async function check(address) {
    return pendingEnvelopes(requireLocalAddress(address).address);
  }

  async function read(address, id) {
    const mailboxAddress = requireLocalAddress(address).address;
    validateName(id, "envelope id");
    const path = join(mailboxDirectory(mailboxAddress, "pending"), `${id}.json`);
    const envelope = JSON.parse(await readFile(path, "utf8"));
    if (envelope.id !== id || envelope.to?.name !== mailboxAddress) {
      throw new Error("envelope identity does not match the requested mailbox");
    }
    return {
      envelope,
      attachmentDirectory: join(mailboxDirectory(mailboxAddress, "pending"), id),
      mailboxAddress,
    };
  }

  async function acknowledge(address, id) {
    const mailboxAddress = requireLocalAddress(address).address;
    validateName(id, "envelope id");
    const pending = mailboxDirectory(mailboxAddress, "pending");
    const delivered = mailboxDirectory(mailboxAddress, "delivered");
    const envelopeSource = join(pending, `${id}.json`);
    const attachmentSource = join(pending, id);
    const envelopeDestination = join(delivered, `${id}.json`);
    const attachmentDestination = join(delivered, id);
    await read(mailboxAddress, id);
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
            mailbox: mailboxAddress,
            error: errorDetails(rollbackError),
          });
        }
      }
      throw error;
    }
    diagnostics.log("envelope.acknowledged", {
      envelopeId: id,
      mailbox: mailboxAddress,
    });
    return envelopeDestination;
  }

  async function checkLocal(name) {
    const results = await Promise.all(
      localAddresses(name).map(async (address) =>
        (await check(address)).map((entry) => ({
          ...entry,
          mailboxAddress: address,
        })),
      ),
    );
    return results.flat().sort((left, right) =>
      left.envelope.id.localeCompare(right.envelope.id),
    );
  }

  async function findLocalEnvelope(name, id) {
    validateName(id, "envelope id");
    const matches = [];
    for (const address of localAddresses(name)) {
      try {
        matches.push(await read(address, id));
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
    if (matches.length === 0) {
      const error = new Error(`envelope ${id} was not found for ${name}`);
      error.code = "ENOENT";
      throw error;
    }
    if (matches.length > 1) {
      throw new Error(
        `envelope ${id} is ambiguous across ${matches
          .map(({ mailboxAddress }) => mailboxAddress)
          .join(" and ")}`,
      );
    }
    return matches[0];
  }

  async function readLocal(name, id) {
    return findLocalEnvelope(validateName(name, "agent name"), id);
  }

  async function acknowledgeLocal(name, id) {
    const match = await findLocalEnvelope(validateName(name, "agent name"), id);
    return acknowledge(match.mailboxAddress, id);
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
        name = requireLocalAddress(entry.name).address;
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
    const envelopes = await checkLocal(validateName(name, "agent name"));
    if (envelopes.length === 0) return "";
    return `You have ${envelopes.length} unread mailbox envelope(s) for ${name}. Run the mailbox check command before continuing other work.`;
  }

  function legacyWatermarkPath(address) {
    const parsed = parseMailboxAddress(address);
    return parsed.machine
      ? undefined
      : join(stateRoot, "watermarks", `${parsed.address}.txt`);
  }

  async function readLegacyWatermarks(address) {
    const result = [];
    const path = legacyWatermarkPath(address);
    if (!path) return result;
    for (const watermarkPath of [path]) {
      try {
        const value = (await readFile(watermarkPath, "utf8")).trim();
        if (value) result.push(value);
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
    return result;
  }

  function notificationDirectory(address) {
    return join(stateRoot, "notified", parseMailboxAddress(address).address);
  }

  async function notifiedIds(address, pendingIds) {
    const directory = notificationDirectory(address);
    let names = [];
    try {
      names = await readdir(directory);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    const result = new Set(names.filter((entry) => entry.endsWith(".notified")).map(
      (entry) => entry.slice(0, -".notified".length),
    ));
    for (const legacy of await readLegacyWatermarks(address)) result.add(legacy);
    for (const notified of result) {
      if (!pendingIds.has(notified)) {
        await rm(join(directory, `${notified}.notified`), { force: true });
      }
    }
    return result;
  }

  async function markNotified(address, ids) {
    const directory = notificationDirectory(address);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    await Promise.all(
      ids.map((id) =>
        atomicWrite(join(directory, `${id}.notified`), `${new Date().toISOString()}\n`),
      ),
    );
  }

  async function poke(
    address,
    {
      targetName = parseMailboxAddress(address).name,
      wait = false,
      requireStableAttachments = false,
    } = {},
  ) {
    const mailboxAddress = requireLocalAddress(address).address;
    validateName(targetName, "target name");
    const envelopes = await pendingEnvelopes(mailboxAddress, {
      requireStableAttachments,
    });
    if (envelopes.length === 0) return { status: "empty" };
    const pendingIds = new Set(envelopes.map(({ envelope }) => envelope.id));
    const notified = await notifiedIds(mailboxAddress, pendingIds);
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
          targetName,
          "--prompt-file",
          promptPath,
          "--mode",
          "enqueue",
          "--dedupe-key",
          `mailbox:${mailboxAddress}:${newest.id}`,
          "--timeout",
          wait ? "35" : "15",
        ],
        {},
      );
      if (
        result.code === 0 &&
        (result.stdout.includes('"delivery":"idle"') ||
          result.stdout.includes('"delivery":"queued"'))
      ) {
        await markNotified(mailboxAddress, [...pendingIds]);
        diagnostics.log("wakeup.delivered", {
          mailbox: mailboxAddress,
          targetName,
          envelopeId: newest.id,
        });
        return { status: "delivered", envelopeId: newest.id };
      }
      const targetUnavailable =
        result.code === 64 &&
        result.stderr.includes("no fresh session-inbox instance");
      diagnostics.log(targetUnavailable ? "wakeup.no_active_session" : "wakeup.unverified", {
        mailbox: mailboxAddress,
        targetName,
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

  async function acquireWatcher(address) {
    const mailboxAddress = parseMailboxAddress(address).address;
    const path = join(stateRoot, "watchers", `${mailboxAddress}.lock`);
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const handle = await open(path, "wx", 0o600);
        await handle.writeFile(
          `${JSON.stringify({
            pid: process.pid,
            address: mailboxAddress,
            startedAt: new Date().toISOString(),
          })}\n`,
        );
        await handle.close();
        const removeLockOnExit = () => {
          rmSync(path, { force: true });
        };
        process.once("exit", removeLockOnExit);
        return async () => {
          process.removeListener("exit", removeLockOnExit);
          await rm(path, { force: true });
        };
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
            throw new Error(
              `mailbox watcher for ${mailboxAddress} is already running as pid ${owner.pid}`,
            );
          } catch (ownerError) {
            if (ownerError?.code === "EPERM") {
              throw new Error(
                `mailbox watcher for ${mailboxAddress} is already running as pid ${owner.pid}`,
              );
            }
            if (ownerError?.code !== "ESRCH") throw ownerError;
          }
        }
        await rm(path, { force: true });
      }
    }
    throw new Error(`could not acquire mailbox watcher for ${mailboxAddress}`);
  }

  async function watch(
    address,
    {
      targetName = parseMailboxAddress(address).name,
      intervalMs = 2_000,
      once = false,
      signal,
    } = {},
  ) {
    const mailboxAddress = requireLocalAddress(address).address;
    validateName(targetName, "target name");
    if (!Number.isFinite(intervalMs) || intervalMs < 100) {
      throw new Error("watch interval must be at least 100 ms");
    }
    const release = await acquireWatcher(mailboxAddress);
    diagnostics.log("watcher.started", {
      mailbox: mailboxAddress,
      targetName,
      intervalMs,
    });
    try {
      do {
        try {
          await poke(mailboxAddress, {
            targetName,
            requireStableAttachments: true,
          });
        } catch (error) {
          diagnostics.log("watcher.poll_failed", {
            mailbox: mailboxAddress,
            targetName,
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
      diagnostics.log("watcher.stopped", {
        mailbox: mailboxAddress,
        targetName,
      });
    }
  }

  return {
    mailboxRoot,
    machineName,
    stateRoot,
    acknowledge,
    acknowledgeLocal,
    check,
    checkLocal,
    localAddresses,
    list,
    poke,
    read,
    readLocal,
    resumeHint,
    send,
    watch,
  };
}
