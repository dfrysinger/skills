#!/usr/bin/env node
// Bind one structured self_compact tool call to a detached SDK compaction
// verifier. Portable across Windows and POSIX hosts: Node built-ins only.

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { closeSync, openSync } from "node:fs";
import { appendFile, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CONTINUATION_TEXT,
  RECEIPT_PREFIX,
  RECLAIMABLE_STATES,
  STATE_PREFIX,
  collectCandidates,
  decodeRootEvents,
  exists,
  isEntrypoint,
  lockPaths,
  lockTokenMatches,
  pidIsLive,
  readEventTail,
  readPid,
  readTextOrNull,
  readTrimmedOrNull,
  runPaths,
  sessionInboxRoot,
  sleep,
  summaryCountOf,
  workspaceCwdOf,
  writeAtomic,
  writeExclusive,
  writePrivate,
} from "./resume-after-compact.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));

export class SubmitError extends Error {
  constructor(message, code = 1) {
    super(message);
    this.code = code;
  }
}

function refuse(message, code = 1) {
  throw new SubmitError(`${message}; compact not submitted`, code);
}

function integerSetting(name, raw, fallback, { minimum, maximum, label }) {
  const text = raw === undefined || raw === "" ? String(fallback) : raw;
  if (!/^\d+$/.test(text)) refuse(`${label} must be an integer`);
  const value = Number(text);
  if (value < minimum || value > maximum) {
    refuse(`${label} must be between ${minimum} and ${maximum}`);
  }
  return value;
}

function secondsSetting(name, raw, fallback, { maximum, label }) {
  const text = raw === undefined || raw === "" ? String(fallback) : raw;
  if (!/^\d+(\.\d+)?$/.test(text)) refuse(`${label} must be a number`);
  const value = Number(text);
  if (!(value > 0) || value > maximum) {
    refuse(`${label} must be between 0 and ${maximum} seconds`);
  }
  return value;
}

export function readSettings(env = process.env) {
  return {
    authScanBytes: integerSetting(
      "SELF_COMPACT_AUTH_SCAN_BYTES",
      env.SELF_COMPACT_AUTH_SCAN_BYTES,
      67108864,
      { minimum: 65536, maximum: 67108864, label: "authorization scan bound" },
    ),
    submitScanBytes: integerSetting(
      "SELF_COMPACT_SUBMIT_SCAN_BYTES",
      env.SELF_COMPACT_SUBMIT_SCAN_BYTES,
      1048576,
      { minimum: 65536, maximum: 8388608, label: "submit scan bound" },
    ),
    requestTimeoutSeconds: integerSetting(
      "SELF_COMPACT_REQUEST_TIMEOUT_SECONDS",
      env.SELF_COMPACT_REQUEST_TIMEOUT_SECONDS,
      1800,
      { minimum: 1, maximum: 86400, label: "request timeout" },
    ),
    submitPolls: integerSetting(
      "SELF_COMPACT_SUBMIT_POLLS",
      env.SELF_COMPACT_SUBMIT_POLLS,
      40,
      { minimum: 1, maximum: 200, label: "submit poll count" },
    ),
    submitPollSeconds: secondsSetting(
      "SELF_COMPACT_SUBMIT_POLL_SECONDS",
      env.SELF_COMPACT_SUBMIT_POLL_SECONDS,
      0.05,
      { maximum: 1, label: "submit poll interval" },
    ),
    readyPolls: integerSetting(
      "SELF_COMPACT_READY_POLLS",
      env.SELF_COMPACT_READY_POLLS,
      50,
      { minimum: 1, maximum: 600, label: "readiness poll count" },
    ),
    readyPollSeconds: secondsSetting(
      "SELF_COMPACT_READY_POLL_SECONDS",
      env.SELF_COMPACT_READY_POLL_SECONDS,
      0.1,
      { maximum: 1, label: "readiness poll interval" },
    ),
    handoffPolls: integerSetting(
      "SELF_COMPACT_HANDOFF_POLLS",
      env.SELF_COMPACT_HANDOFF_POLLS,
      100,
      { minimum: 1, maximum: 600, label: "handoff poll count" },
    ),
    handoffPollSeconds: secondsSetting(
      "SELF_COMPACT_HANDOFF_POLL_SECONDS",
      env.SELF_COMPACT_HANDOFF_POLL_SECONDS,
      0.05,
      { maximum: 5, label: "handoff poll interval" },
    ),
    pollSeconds: secondsSetting(
      "SELF_COMPACT_POLL_SECONDS",
      env.SELF_COMPACT_POLL_SECONDS,
      0.25,
      { maximum: 30, label: "verifier poll interval" },
    ),
    maxPolls: integerSetting(
      "SELF_COMPACT_MAX_POLLS",
      env.SELF_COMPACT_MAX_POLLS,
      7200,
      { minimum: 1, maximum: 1000000, label: "verifier poll limit" },
    ),
    authWaitSeconds: secondsSetting(
      "SELF_COMPACT_AUTH_WAIT_SECONDS",
      env.SELF_COMPACT_AUTH_WAIT_SECONDS,
      180,
      { maximum: 180, label: "authorization wait" },
    ),
  };
}

export function runTokenFrom(env = process.env, now = Date.now(), pid = process.pid, stamp = "") {
  const supplied = env.SELF_COMPACT_RUN_TOKEN;
  const token =
    supplied === undefined || supplied === ""
      ? createHash("sha256")
          .update(`${Math.floor(now / 1000)}:${pid}:${stamp}`)
          .digest("hex")
          .slice(0, 8)
      : supplied;
  if (!/^[0-9a-f]{8}$/.test(token)) {
    refuse("compact run token must be eight lowercase hex characters");
  }
  return token;
}

export function runStamp(now = new Date()) {
  return `${now.toISOString().replaceAll(/[-:]/g, "").replace(/\.\d+Z$/, "Z")}`;
}

async function candidateWorkspaces(env, sessionStateDir, targetSession) {
  if (env.SELF_COMPACT_WORKSPACE) return [env.SELF_COMPACT_WORKSPACE];
  const direct = join(sessionStateDir, targetSession, "workspace.yaml");
  if (await exists(direct)) return [direct];
  let entries;
  try {
    entries = await readdir(sessionStateDir);
  } catch {
    return [];
  }
  const cwd = process.cwd();
  const found = [];
  for (const entry of entries) {
    const path = join(sessionStateDir, entry, "workspace.yaml");
    const text = await readTextOrNull(path);
    if (text === null) continue;
    if (workspaceCwdOf(text) !== cwd) continue;
    found.push(path);
  }
  return found;
}

export async function scanCandidate(workspaces, toolCallId, scanBytes) {
  const matches = [];
  for (const workspace of workspaces) {
    if (basename(workspace) !== "workspace.yaml") continue;
    const eventsPath = join(dirname(workspace), "events.jsonl");
    if (!(await exists(eventsPath))) continue;
    const tail = await readEventTail(eventsPath, scanBytes);
    if (tail.boundaryExceeded || tail.partial) continue;
    const events = decodeRootEvents(tail.text);
    for (const match of collectCandidates(events, toolCallId)) {
      matches.push({ workspace, ...match });
    }
  }
  if (matches.length !== 1) {
    throw new Error("could not bind one running canonical self-compact helper");
  }
  return matches[0];
}

// A lock is reclaimed only when every recorded owner is dead and the durable
// state proves that no publication attempt ever began.
export async function inspectLockForReclaim(lockDir) {
  const lock = lockPaths(lockDir);
  const state = await readTrimmedOrNull(lock.state);
  if (state === null) return { reclaimable: false, reason: "no recorded state" };
  if (!RECLAIMABLE_STATES.has(state)) {
    return { reclaimable: false, reason: `state ${state} may have published a request` };
  }
  if (await exists(lock.publishing)) {
    return { reclaimable: false, reason: "a publication attempt was recorded" };
  }
  if (await exists(lock.request)) {
    return { reclaimable: false, reason: "request metadata was recorded" };
  }
  const token = await readTrimmedOrNull(lock.token);
  if (token === null) return { reclaimable: false, reason: "no owner token" };
  const runId = await readTrimmedOrNull(lock.runId);
  if (runId === null) return { reclaimable: false, reason: "no run identity" };

  const submitter = await readPid(lock.submitterPid);
  const watcher = await readPid(lock.watcherPid);
  if (!submitter.valid || !watcher.valid) {
    return { reclaimable: false, reason: "unreadable owner process identity" };
  }
  if (!submitter.present) {
    return { reclaimable: false, reason: "no recorded foreground owner" };
  }
  if (pidIsLive(submitter.pid)) {
    return { reclaimable: false, reason: "the foreground owner is still alive" };
  }
  if (watcher.present && pidIsLive(watcher.pid)) {
    return { reclaimable: false, reason: "the verifier owner is still alive" };
  }
  if (state === "foreground" && watcher.present) {
    return { reclaimable: false, reason: "foreground state recorded a verifier owner" };
  }

  return { reclaimable: true, runId, token, state };
}

async function reclaimLock(lockDir, filesDir) {
  const inspection = await inspectLockForReclaim(lockDir);
  if (!inspection.reclaimable) return inspection;
  const artifacts = runPaths(filesDir, inspection.runId);
  const handoff = await readTextOrNull(artifacts.handoff);
  const ready = await readTrimmedOrNull(artifacts.ready);
  if (ready !== null && ready !== inspection.token) {
    return { reclaimable: false, reason: "readiness artifact does not match the owner token" };
  }
  if (handoff !== null) {
    const lines = handoff.split("\n");
    if (lines[lines.length - 1] === "") lines.pop();
    if (lines.length !== 2 || lines[0] !== inspection.token || !lines[1]) {
      return { reclaimable: false, reason: "handoff artifact is inconsistent" };
    }
  }
  for (const path of [
    artifacts.ready,
    artifacts.handoff,
    artifacts.instructions,
    artifacts.continuation,
    artifacts.candidate,
    artifacts.runFile,
  ]) {
    await rm(path, { force: true });
  }
  await rm(lockDir, { recursive: true, force: true });
  return { reclaimable: true, reclaimed: true };
}

async function acquireLock(lockDir, filesDir) {
  try {
    await mkdir(lockDir);
    return;
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
  }
  const reclaim = await reclaimLock(lockDir, filesDir);
  if (!reclaim.reclaimed) {
    refuse(
      `another or ambiguous self-compact run owns ${lockDir} (${reclaim.reason})`,
    );
  }
  try {
    await mkdir(lockDir);
  } catch {
    refuse(`another or ambiguous self-compact run owns ${lockDir}`);
  }
}

export async function submit({ argv = process.argv.slice(2), env = process.env } = {}) {
  if (argv.length !== 2 || argv[0] !== "--tool-call-id") {
    throw new SubmitError(
      "usage: submit-compact.mjs --tool-call-id ID\nsubmit-compact: invoke through the self_compact extension tool",
      2,
    );
  }
  const requestedCallId = argv[1];
  if (typeof requestedCallId !== "string" || requestedCallId === "" || requestedCallId.includes("\n")) {
    throw new SubmitError(
      "submit-compact: tool-call identity is invalid; compact not submitted",
      2,
    );
  }

  const settings = readSettings(env);
  const verifier = env.SELF_COMPACT_VERIFIER ?? join(scriptDirectory, "resume-after-compact.mjs");
  const requestCli =
    env.SELF_COMPACT_REQUEST_CLI ??
    join(scriptDirectory, "..", "..", "..", "extensions", "session-inbox", "request.mjs");
  const sessionStateDir =
    env.SELF_COMPACT_SESSION_STATE_DIR ?? join(homedir(), ".copilot", "session-state");
  const targetSession = env.SELF_COMPACT_TARGET_SESSION ?? env.COPILOT_AGENT_SESSION_ID ?? "";
  const nodeBin = env.SELF_COMPACT_NODE_BIN ?? process.execPath;

  if (!(await exists(verifier))) refuse("detached verifier is unavailable");
  if (!(await exists(requestCli))) refuse("session-inbox request CLI is unavailable");
  if (!targetSession) refuse("COPILOT_AGENT_SESSION_ID is unavailable");
  if (targetSession.includes("\n")) refuse("target session ID is invalid");
  if (!(await exists(nodeBin))) refuse("node is unavailable");

  const stamp = runStamp();
  const token = runTokenFrom(env, Date.now(), process.pid, stamp);

  const workspaces = await candidateWorkspaces(env, sessionStateDir, targetSession);
  if (workspaces.length === 0) refuse("could not find a candidate Copilot workspace");

  let candidate = null;
  let lastReason = "no matching helper request";
  for (let poll = 0; poll < settings.submitPolls; poll += 1) {
    try {
      candidate = await scanCandidate(workspaces, requestedCallId, settings.submitScanBytes);
      break;
    } catch (error) {
      lastReason = error?.message ?? String(error);
    }
    await sleep(settings.submitPollSeconds);
  }
  if (!candidate) refuse(`current-turn authorization failed: ${lastReason}`);

  const workspace = candidate.workspace;
  const workspaceText = await readTextOrNull(workspace);
  if (workspaceText === null) refuse("authorized workspace is unavailable");
  const baselineSummaryCount = summaryCountOf(workspaceText);
  if (baselineSummaryCount === null) {
    refuse("active session has no numeric summary_count");
  }

  const sessionDir = dirname(workspace);
  const eventsPath = join(sessionDir, "events.jsonl");
  const checkpointsDir = join(sessionDir, "checkpoints");
  const filesDir = join(sessionDir, "files");
  if (!(await exists(eventsPath))) refuse("active session event log is unavailable");
  await mkdir(filesDir, { recursive: true });

  const runId = `${stamp}-${process.pid}`;
  const lockDir = join(filesDir, "self-compact.lock");
  const lock = lockPaths(lockDir);
  const lockToken = `${token}-${runId}`;
  const artifacts = runPaths(filesDir, runId);

  await acquireLock(lockDir, filesDir);

  let verifierLaunched = false;
  let handoffComplete = false;
  const appendLog = async (line) => {
    await appendFile(artifacts.log, `${line}\n`, { mode: 0o600 });
  };

  try {
    await writeExclusive(lock.token, `${lockToken}\n`);
    await writeExclusive(lock.submitterPid, `${process.pid}\n`);
    await writeExclusive(lock.runId, `${runId}\n`);
    await writeAtomic(lock.state, "foreground\n");
    await appendLog(`${STATE_PREFIX}foreground`);

    await writePrivate(
      artifacts.candidate,
      `${JSON.stringify(
        { workspace, callId: candidate.callId, brief: candidate.brief },
        null,
        2,
      )}\n`,
    );
    await writePrivate(
      artifacts.instructions,
      `${candidate.brief}\n\nSELF_COMPACT_RUN_TOKEN: ${token}`,
    );
    await writePrivate(artifacts.continuation, CONTINUATION_TEXT);
    await writePrivate(
      artifacts.runFile,
      `${JSON.stringify(
        {
          version: 1,
          runId,
          runToken: token,
          lockToken,
          toolCallId: candidate.callId,
          targetSession,
          workspace,
          events: eventsPath,
          checkpointsDir,
          filesDir,
          lockDir,
          baselineSummaryCount,
          ready: artifacts.ready,
          handoff: artifacts.handoff,
          instructions: artifacts.instructions,
          continuation: artifacts.continuation,
          candidate: artifacts.candidate,
          runFile: artifacts.runFile,
          log: artifacts.log,
          nodeBin,
          requestCli,
          inboxRoot: sessionInboxRoot(),
          requestTimeoutSeconds: settings.requestTimeoutSeconds,
          pollSeconds: settings.pollSeconds,
          maxPolls: settings.maxPolls,
          authWaitSeconds: settings.authWaitSeconds,
          authScanBytes: settings.authScanBytes,
          handoffPolls: settings.handoffPolls,
          handoffPollSeconds: settings.handoffPollSeconds,
        },
        null,
        2,
      )}\n`,
    );

    await writeAtomic(lock.state, "verifier-starting\n");
    await appendLog(`${STATE_PREFIX}verifier-starting`);

    const logFd = openSync(artifacts.log, "a", 0o600);
    let child;
    try {
      child = spawn(process.execPath, [verifier, artifacts.runFile], {
        detached: true,
        stdio: ["ignore", logFd, logFd],
        windowsHide: true,
      });
    } finally {
      closeSync(logFd);
    }
    verifierLaunched = true;
    child.unref();

    let ready = false;
    for (let poll = 0; poll < settings.readyPolls; poll += 1) {
      if ((await readTrimmedOrNull(artifacts.ready)) === lockToken) {
        ready = true;
        break;
      }
      if (!pidIsLive(child.pid)) break;
      await sleep(settings.readyPollSeconds);
    }
    if (!ready) {
      ready = (await readTrimmedOrNull(artifacts.ready)) === lockToken;
    }
    if (!ready || !pidIsLive(child.pid)) {
      throw new SubmitError(
        `submit-compact: detached SDK verifier did not become ready; lock retained at ${lockDir}`,
      );
    }

    await writeAtomic(artifacts.handoff, `${lockToken}\n${candidate.callId}\n`);
    handoffComplete = true;

    return {
      lockToken,
      log: artifacts.log,
      stdout: [
        `${RECEIPT_PREFIX}${lockToken}`,
        "self-compact SDK verifier armed; foreground helper complete",
        `watcher log: ${artifacts.log}`,
      ].join("\n"),
    };
  } catch (error) {
    if (!verifierLaunched) {
      for (const path of [
        artifacts.ready,
        artifacts.handoff,
        artifacts.instructions,
        artifacts.continuation,
        artifacts.candidate,
        artifacts.runFile,
      ]) {
        await rm(path, { force: true });
      }
      const state = await readTrimmedOrNull(lock.state);
      if (
        (state === "foreground" || state === "verifier-starting" || state === null) &&
        (await lockTokenMatches(lock, lockToken))
      ) {
        await rm(lockDir, { recursive: true, force: true });
      }
    } else if (!handoffComplete) {
      await writeFile(lock.cancelled, `${new Date().toISOString()}\n`, {
        mode: 0o600,
      }).catch(() => {});
    }
    throw error;
  }
}

if (isEntrypoint(import.meta.url)) {
  try {
    const outcome = await submit();
    process.stdout.write(`${outcome.stdout}\n`);
    process.exit(0);
  } catch (error) {
    const message = error?.message ?? String(error);
    const text = message.startsWith("submit-compact")
      ? message
      : `submit-compact: ${message}`;
    process.stderr.write(`${text}\n`);
    process.exit(error instanceof SubmitError ? error.code : 1);
  }
}
