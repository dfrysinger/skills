#!/usr/bin/env node
// Submit and verify one session-inbox compaction after the authorizing turn ends.
// This module owns the durable self-compact state machine and the shared
// portable primitives used by the foreground submitter.

import { spawn } from "node:child_process";
import { open, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const CONTINUATION_TEXT = "Compaction done; resume, do not compact.";
export const RECEIPT_PREFIX = "self-compact handoff receipt: ";
export const STATE_PREFIX = "self-compact state: ";

export const LOCK_STATES = [
  "foreground",
  "verifier-starting",
  "verifier-owned",
  "authorized",
  "publishing",
  "request-published",
  "compact-observed",
  "checkpoint-observed",
  "continuation-observed",
  "completed",
];

// Only these states can prove that no publication attempt ever began.
export const RECLAIMABLE_STATES = new Set([
  "foreground",
  "verifier-starting",
  "verifier-owned",
  "authorized",
]);

export class MalformedEventError extends Error {}

export class VerifierError extends Error {
  constructor(message, { release = true } = {}) {
    super(message);
    this.release = release;
  }
}

export function isEntrypoint(metaUrl) {
  const entry = process.argv[1];
  if (!entry) return false;
  try {
    return fileURLToPath(metaUrl) === resolve(entry);
  } catch {
    return false;
  }
}

export function sleep(seconds) {
  return new Promise((done) => setTimeout(done, Math.round(seconds * 1000)));
}

export function pidIsLive(pid) {
  if (!Number.isInteger(pid) || pid <= 1) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

export async function readTextOrNull(path) {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    // A file that is absent, being atomically replaced, or momentarily locked
    // by another owner is never treated as proof of anything.
    if (
      error?.code === "ENOENT" ||
      error?.code === "ENOTDIR" ||
      error?.code === "EBUSY" ||
      error?.code === "EPERM" ||
      error?.code === "EACCES"
    ) {
      return null;
    }
    throw error;
  }
}

export async function readTrimmedOrNull(path) {
  const text = await readTextOrNull(path);
  return text === null ? null : text.trim();
}

export async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT" || error?.code === "ENOTDIR") return false;
    throw error;
  }
}

export async function writeAtomic(path, text, mode = 0o600) {
  const temporary = `${path}.next`;
  await writeFile(temporary, text, { mode });
  await rename(temporary, path);
}

export async function writePrivate(path, text) {
  await writeFile(path, text, { mode: 0o600 });
}

export async function writeExclusive(path, text) {
  await writeFile(path, text, { mode: 0o600, flag: "wx" });
}

export function lockPaths(lockDir) {
  return {
    dir: lockDir,
    token: join(lockDir, "token"),
    state: join(lockDir, "state"),
    submitterPid: join(lockDir, "submitter.pid"),
    watcherPid: join(lockDir, "watcher.pid"),
    cancelled: join(lockDir, "cancelled"),
    runId: join(lockDir, "run-id"),
    publishing: join(lockDir, "publish.json"),
    request: join(lockDir, "request.json"),
    outcome: join(lockDir, "outcome.json"),
  };
}

export function runPaths(filesDir, runId) {
  const base = join(filesDir, `self-compact-${runId}`);
  return {
    ready: `${base}.ready`,
    handoff: `${base}.handoff`,
    instructions: `${base}.instructions`,
    continuation: `${base}.continuation`,
    candidate: `${base}.candidate.json`,
    runFile: `${base}.run.json`,
    log: `${base}.log`,
  };
}

export async function readPid(path) {
  const text = await readTrimmedOrNull(path);
  if (text === null) return { present: false, pid: null, valid: true };
  if (!/^\d+$/.test(text)) return { present: true, pid: null, valid: false };
  return { present: true, pid: Number(text), valid: true };
}

export async function lockTokenMatches(lock, lockToken) {
  return (await readTrimmedOrNull(lock.token)) === lockToken;
}

// Reads the trailing window of an append-only event log the way the previous
// POSIX implementation did: drop a partial first line, refuse a partial last
// line, and report a window that cannot be aligned to a line boundary.
export async function readEventTail(path, maxBytes) {
  const handle = await open(path, "r");
  try {
    const { size } = await handle.stat();
    const floor = size > maxBytes ? size - maxBytes : 0;
    const length = size - floor;
    const buffer = Buffer.alloc(length);
    if (length > 0) {
      const { bytesRead } = await handle.read(buffer, 0, length, floor);
      if (bytesRead !== length) {
        throw new Error(`cannot read the event tail from ${path}`);
      }
    }
    let text = buffer.toString("utf8");
    if (floor > 0) {
      const newline = text.indexOf("\n");
      if (newline < 0) return { size, boundaryExceeded: true };
      text = text.slice(newline + 1);
    }
    if (text.length > 0 && !text.endsWith("\n")) return { size, partial: true };
    return { size, text };
  } finally {
    await handle.close();
  }
}

export function decodeRootEvents(text) {
  const lines = text.split("\n");
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  const events = [];
  for (const line of lines) {
    let event;
    try {
      event = JSON.parse(line);
    } catch {
      throw new MalformedEventError("malformed event JSON");
    }
    if (!event || typeof event !== "object" || Array.isArray(event)) {
      throw new MalformedEventError("malformed event JSON");
    }
    if (event.agentId !== undefined && event.agentId !== null) continue;
    events.push(event);
  }
  return events;
}

export function eventData(event) {
  const data = event?.data;
  return data && typeof data === "object" && !Array.isArray(data) ? data : null;
}

export function toolRequestsOf(event) {
  const requests = eventData(event)?.toolRequests;
  return Array.isArray(requests) ? requests : null;
}

export function briefIsComplete(brief) {
  return (
    typeof brief === "string" &&
    /^Keep:[ \t]*\S[^\n]*/.test(brief) &&
    /\nDrop:[^\n]*/.test(brief) &&
    /\nAfter compaction:[ \t]*\S[^\n]*do not compact again[^\n]*/.test(brief)
  );
}

export function summaryCountOf(workspaceText) {
  const match = /^summary_count:[ \t]*(\d+)[ \t]*$/m.exec(workspaceText ?? "");
  return match ? Number(match[1]) : null;
}

export function workspaceCwdOf(workspaceText) {
  const match = /^cwd:[ \t]*(.*?)[ \t]*$/m.exec(workspaceText ?? "");
  return match ? match[1] : null;
}

export function sessionInboxRoot() {
  return (
    process.env.COPILOT_SESSION_INBOX_DIR ??
    join(homedir(), ".copilot", "session-inbox")
  );
}

export function receiptPathsFor(root, id) {
  return {
    pending: join(root, "pending", `${id}.json`),
    processing: join(root, "processing", `${id}.json`),
    completed: join(root, "completed", `${id}.json`),
    failed: join(root, "failed", `${id}.json`),
  };
}

// Mirrors the freshness contract in extensions/session-inbox/request.mjs: an
// instance heartbeat only proves a live generation for fifteen seconds.
export const INSTANCE_FRESHNESS_MS = 15_000;

export async function resolveFreshGenerations(inboxRoot, sessionId, now = Date.now()) {
  const instancesDir = join(inboxRoot, "instances");
  let names;
  try {
    names = await readdir(instancesDir);
  } catch (error) {
    if (error?.code === "ENOENT" || error?.code === "ENOTDIR") return [];
    throw error;
  }
  const generations = new Set();
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    let instance;
    try {
      instance = JSON.parse(await readFile(join(instancesDir, name), "utf8"));
    } catch {
      // A concurrently replaced or malformed heartbeat is not a live target.
      continue;
    }
    const age = now - Date.parse(instance?.updatedAt);
    if (
      instance?.sessionId === sessionId &&
      instance?.generation &&
      Number.isFinite(age) &&
      age >= 0 &&
      age <= INSTANCE_FRESHNESS_MS
    ) {
      generations.add(instance.generation);
    }
  }
  return [...generations];
}

export function parseJsonLines(text) {
  const values = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("{")) continue;
    try {
      const value = JSON.parse(trimmed);
      if (value && typeof value === "object" && !Array.isArray(value)) {
        values.push(value);
      }
    } catch {
      // Non-JSON transport chatter is not a receipt.
    }
  }
  return values;
}

const ROOT_ACTIVITY_TYPES = new Set([
  "user.message",
  "assistant.turn_start",
  "assistant.turn_end",
  "tool.execution_start",
  "tool.execution_complete",
]);

// Foreground authorization: collect every running canonical self_compact
// helper request in the current root turn that matches this tool-call id.
export function collectCandidates(events, expectedCallId) {
  const matches = [];
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (event.type !== "assistant.message") continue;
    const data = eventData(event);
    if (!data) continue;
    const requests = toolRequestsOf(event);
    if (!requests) continue;
    for (const request of requests) {
      if (!request || typeof request !== "object") continue;
      if (request.name !== "self_compact") continue;
      if (request.toolCallId !== expectedCallId) continue;
      const { content } = data;
      if (content !== undefined && content !== null) {
        if (typeof content !== "string" || content.length > 0) {
          throw new Error("self_compact request exposed assistant prose");
        }
      }
      if (requests.length !== 1) {
        throw new Error("self_compact request was batched with another tool");
      }
      const callId = request.toolCallId;
      if (typeof callId !== "string" || callId.length === 0) {
        throw new Error("helper request has no tool-call identity");
      }
      const brief =
        request.arguments &&
        typeof request.arguments === "object" &&
        !Array.isArray(request.arguments)
          ? request.arguments.brief
          : "";
      if (!briefIsComplete(brief)) {
        throw new Error("self_compact tool has no complete brief");
      }

      let turnStart = -1;
      for (let back = index; back >= 0; back -= 1) {
        if (events[back].type === "assistant.turn_start") {
          turnStart = back;
          break;
        }
      }
      if (turnStart < 0) {
        throw new Error("helper request has no containing assistant turn");
      }
      for (let prior = turnStart + 1; prior < index; prior += 1) {
        const type = events[prior].type;
        if (ROOT_ACTIVITY_TYPES.has(type)) {
          throw new Error(
            "conflicting root activity preceded the helper request",
          );
        }
        if (type === "assistant.message") {
          const priorRequests = toolRequestsOf(events[prior]);
          if (priorRequests && priorRequests.length > 0) {
            throw new Error(
              "another root tool request preceded the helper request",
            );
          }
        }
      }

      const starts = [];
      const completions = [];
      for (let scan = 0; scan < events.length; scan += 1) {
        const data = eventData(events[scan]);
        if (!data || data.toolCallId !== callId) continue;
        if (events[scan].type === "tool.execution_start") starts.push(scan);
        if (events[scan].type === "tool.execution_complete") {
          completions.push(scan);
        }
      }
      if (starts.length !== 1 || completions.length > 0) continue;
      const startIndex = starts[0];
      if (startIndex <= index) continue;
      if (eventData(events[startIndex])?.toolName !== "self_compact") continue;
      for (let later = startIndex + 1; later < events.length; later += 1) {
        const type = events[later].type;
        if (ROOT_ACTIVITY_TYPES.has(type)) {
          throw new Error("root activity followed the running helper");
        }
        if (type === "assistant.message") {
          const laterRequests = toolRequestsOf(events[later]);
          if (laterRequests && laterRequests.length > 0) {
            throw new Error("root tool request followed the running helper");
          }
        }
      }
      matches.push({ callId, brief });
    }
  }
  return matches;
}

// Verifier authorization: the bound helper ran to completion, carried this
// run's receipt, and its turn ended without competing root activity.
export function classifyAuthorization(tail, { toolCallId, receipt }) {
  if (tail.boundaryExceeded) {
    return { state: "cancel", reason: "authorization boundary exceeds event tail" };
  }
  if (tail.partial) return { state: "wait" };
  let events;
  try {
    events = decodeRootEvents(tail.text);
  } catch (error) {
    if (error instanceof MalformedEventError) {
      return { state: "cancel", reason: "malformed authorization event JSON" };
    }
    throw error;
  }

  const starts = [];
  const completions = [];
  for (let index = 0; index < events.length; index += 1) {
    const data = eventData(events[index]);
    if (!data || data.toolCallId !== toolCallId) continue;
    if (events[index].type === "tool.execution_start") starts.push(index);
    if (events[index].type === "tool.execution_complete") completions.push(index);
  }
  if (starts.length > 1 || completions.length > 1) {
    return { state: "cancel", reason: "duplicate helper execution identity" };
  }
  if (starts.length !== 1 || completions.length !== 1) return { state: "wait" };
  const start = starts[0];
  const completion = completions[0];
  if (completion <= start) {
    return { state: "cancel", reason: "helper completion preceded execution start" };
  }
  for (let index = start + 1; index < completion; index += 1) {
    if (ROOT_ACTIVITY_TYPES.has(events[index].type)) {
      return {
        state: "cancel",
        reason: "conflicting root activity occurred during helper execution",
      };
    }
  }
  const result = eventData(events[completion])?.result;
  const content =
    result && typeof result === "object" && !Array.isArray(result)
      ? result.content
      : undefined;
  if (typeof content !== "string") return { state: "wait" };
  if (!content.split("\n").includes(receipt)) {
    return {
      state: "cancel",
      reason: "helper completion carried no matching handoff receipt",
    };
  }

  let sawTurnEnd = false;
  let turnOpen = false;
  for (let index = completion + 1; index < events.length; index += 1) {
    const type = events[index].type;
    if (type === "assistant.turn_start") {
      turnOpen = true;
      continue;
    }
    if (type === "assistant.turn_end") {
      turnOpen = false;
      sawTurnEnd = true;
      continue;
    }
    if (
      type === "user.message" ||
      type === "tool.execution_start" ||
      type === "tool.execution_complete"
    ) {
      return {
        state: "cancel",
        reason: "new root activity followed helper completion",
      };
    }
    if (type === "assistant.message") {
      const requests = toolRequestsOf(events[index]);
      if (requests && requests.length > 0) {
        return {
          state: "cancel",
          reason: "new root tool request followed helper completion",
        };
      }
    }
  }
  if (!sawTurnEnd || turnOpen) return { state: "wait" };
  return { state: "ready" };
}

async function readEventRange(path, offset) {
  const handle = await open(path, "r");
  try {
    const { size } = await handle.stat();
    if (size < offset) {
      throw new Error(`event log shrank below the recorded boundary in ${path}`);
    }
    const length = size - offset;
    const buffer = Buffer.alloc(length);
    if (length > 0) {
      const { bytesRead } = await handle.read(buffer, 0, length, offset);
      if (bytesRead !== length) {
        throw new Error(`cannot read events after the recorded boundary`);
      }
    }
    return buffer;
  } finally {
    await handle.close();
  }
}

function* completeLines(buffer, offset) {
  let start = 0;
  while (start < buffer.length) {
    const newline = buffer.indexOf(0x0a, start);
    if (newline < 0) return;
    yield {
      line: buffer.toString("utf8", start, newline),
      end: offset + newline + 1,
    };
    start = newline + 1;
  }
}

function decodeRootEvent(line) {
  let event;
  try {
    event = JSON.parse(line);
  } catch {
    throw new MalformedEventError("malformed event JSON");
  }
  if (!event || typeof event !== "object" || Array.isArray(event)) {
    throw new MalformedEventError("malformed event JSON");
  }
  if (event.agentId !== undefined && event.agentId !== null) return null;
  return event;
}

// Only a completion whose custom instructions carry this run's exact brief and
// token proves that this run's compact landed.
export async function probeCompletion(eventsPath, offset, instructions) {
  const buffer = await readEventRange(eventsPath, offset);
  for (const { line, end } of completeLines(buffer, offset)) {
    const event = decodeRootEvent(line);
    if (!event) continue;
    if (event.type !== "session.compaction_complete") continue;
    const data = eventData(event) ?? event;
    if (typeof data.customInstructions !== "string") continue;
    if (data.customInstructions !== instructions) continue;
    if (!data.success) return { state: "failed" };
    const checkpointNumber = data.checkpointNumber;
    if (!/^\d+$/.test(String(checkpointNumber))) return { state: "invalid" };
    return {
      state: "success",
      checkpointNumber: Number(checkpointNumber),
      completionEnd: end,
    };
  }
  return { state: "wait" };
}

export async function probeContinuation(eventsPath, offset, expected) {
  const buffer = await readEventRange(eventsPath, offset);
  let matches = 0;
  for (const { line } of completeLines(buffer, offset)) {
    const event = decodeRootEvent(line);
    if (!event) continue;
    if (event.type === "user.message") {
      const data = eventData(event);
      const content = data ? data.content : event.content;
      if (typeof content === "string" && content === expected) {
        const delivery = data && typeof data.delivery === "string" ? data.delivery : "";
        if (delivery !== "idle" && delivery !== "steering") {
          return { state: "mismatch" };
        }
        matches += 1;
        continue;
      }
      return { state: "mismatch" };
    }
    if (event.type === "assistant.turn_start" && matches === 0) {
      return { state: "activity" };
    }
  }
  if (matches > 1) return { state: "duplicate" };
  return { state: matches === 1 ? "success" : "wait" };
}

export async function countCheckpointFiles(checkpointsDir, checkpointNumber) {
  const prefix = `${String(checkpointNumber).padStart(3, "0")}-`;
  let names;
  try {
    names = await readdir(checkpointsDir, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT" || error?.code === "ENOTDIR") return 0;
    throw error;
  }
  return names.filter(
    (entry) =>
      entry.isFile() && entry.name.startsWith(prefix) && entry.name.endsWith(".md"),
  ).length;
}

export function classifyRequestOutcome({ status, output, targetSession, targetGeneration }) {
  const published = /^request: /m.test(output);
  if (status !== 0 && !published) {
    return {
      outcome: "rejected",
      published: false,
      reason: "session-inbox rejected the compact request before publication",
      release: true,
    };
  }
  const receipts = parseJsonLines(output);
  // A receipt only speaks for this run when it names the exact session and the
  // generation resolved before the publication attempt.
  const ownsRun = (receipt) =>
    receipt.sessionId === targetSession && receipt.generation === targetGeneration;
  let effectiveStatus = status;
  if (status === 1) {
    const ambiguous = receipts.some(
      (receipt) => receipt.status === "failed" && receipt.ambiguousSideEffect,
    );
    if (ambiguous) {
      return {
        outcome: "ambiguous",
        published,
        reason:
          "extension exited during compact execution; outcome is ambiguous",
        release: false,
      };
    }
    const postCompactFailure = receipts.some(
      (receipt) =>
        receipt.status === "failed" &&
        ownsRun(receipt) &&
        receipt.sideEffectCompleted &&
        receipt.result &&
        typeof receipt.result === "object" &&
        receipt.result.compacted,
    );
    if (postCompactFailure) {
      effectiveStatus = 0;
    } else {
      return {
        outcome: "failed",
        published,
        reason: "session-inbox reported a failed compact request",
        release: true,
      };
    }
  }
  if (effectiveStatus !== 0) {
    return {
      outcome: "ambiguous",
      published,
      reason: `session-inbox compact request outcome is ambiguous (status ${status})`,
      release: false,
    };
  }

  let valid = false;
  let foreignGeneration = false;
  let continuation = "missing";
  for (const receipt of receipts) {
    if (receipt.sessionId !== targetSession) continue;
    const result =
      receipt.result && typeof receipt.result === "object" ? receipt.result : null;
    const completed = receipt.status === "completed";
    const completedSideEffect =
      receipt.status === "failed" &&
      Boolean(receipt.sideEffectCompleted) &&
      Boolean(result?.compacted);
    if (!completed && !completedSideEffect) continue;
    if (!ownsRun(receipt)) {
      foreignGeneration = true;
      continue;
    }
    valid = true;
    if (result && Object.hasOwn(result, "continuationAccepted")) {
      continuation = result.continuationAccepted ? "accepted" : "failed";
    }
  }
  if (!valid) {
    return {
      outcome: "unmatched",
      published,
      reason: foreignGeneration
        ? `session-inbox handled the compact under a different target generation than ${targetGeneration}`
        : "session-inbox returned no matching completed receipt",
      release: false,
    };
  }
  return { outcome: "completed", published, continuation, release: false };
}

function requiredString(run, key) {
  const value = run[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new VerifierError(`run metadata field ${key} is invalid`, {
      release: false,
    });
  }
  return value;
}

function requiredNumber(run, key, { minimum = 0, maximum = Infinity } = {}) {
  const value = run[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new VerifierError(`run metadata field ${key} is invalid`, {
      release: false,
    });
  }
  if (value < minimum || value > maximum) {
    throw new VerifierError(`run metadata field ${key} is out of range`, {
      release: false,
    });
  }
  return value;
}

function validateRun(run) {
  for (const key of [
    "runId",
    "runToken",
    "lockToken",
    "toolCallId",
    "targetSession",
    "workspace",
    "events",
    "checkpointsDir",
    "filesDir",
    "lockDir",
    "ready",
    "handoff",
    "instructions",
    "continuation",
    "candidate",
    "runFile",
    "log",
    "nodeBin",
    "requestCli",
    "inboxRoot",
  ]) {
    requiredString(run, key);
  }
  requiredNumber(run, "baselineSummaryCount", { minimum: 0 });
  requiredNumber(run, "requestTimeoutSeconds", { minimum: 1 });
  requiredNumber(run, "pollSeconds", { minimum: 0.001, maximum: 30 });
  requiredNumber(run, "maxPolls", { minimum: 1 });
  requiredNumber(run, "authWaitSeconds", { minimum: 0.001, maximum: 180 });
  requiredNumber(run, "authScanBytes", { minimum: 65536 });
  requiredNumber(run, "handoffPolls", { minimum: 1 });
  requiredNumber(run, "handoffPollSeconds", { minimum: 0.001, maximum: 5 });
  return run;
}

function logLine(text) {
  process.stdout.write(`${text}\n`);
}

async function recordState(lock, name) {
  await writeAtomic(lock.state, `${name}\n`);
  logLine(`${STATE_PREFIX}${name}`);
}

async function runRequest(run) {
  const args = [
    run.requestCli,
    "compact",
    "--target-session",
    run.targetSession,
    "--instructions-file",
    run.instructions,
    "--continuation-file",
    run.continuation,
    "--dedupe-key",
    `self-compact:${run.targetSession}:${run.lockToken}`,
    "--timeout",
    String(run.requestTimeoutSeconds),
  ];
  return await new Promise((done, failed) => {
    const child = spawn(run.nodeBin, args, {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", failed);
    child.on("close", (code, signal) => {
      done({
        status: signal ? 128 : (code ?? 128),
        output: `${stdout}${stderr}`,
      });
    });
  });
}

export async function verify(runFilePath) {
  const runText = await readTextOrNull(runFilePath);
  if (runText === null) {
    throw new VerifierError("run metadata is unavailable", { release: false });
  }
  let run;
  try {
    run = validateRun(JSON.parse(runText));
  } catch (error) {
    if (error instanceof VerifierError) throw error;
    throw new VerifierError("run metadata is malformed", { release: false });
  }
  const lock = lockPaths(run.lockDir);
  const failures = { release: true };

  const fail = (message, { release = true } = {}) => {
    throw new VerifierError(message, { release });
  };

  try {
    if (!(await lockTokenMatches(lock, run.lockToken))) {
      fail("watcher lock token mismatch");
    }
    if (!(await exists(run.events))) fail("session event log is unavailable");
    if (!(await exists(run.instructions))) {
      fail("bound compaction instructions are unavailable");
    }
    if (!(await exists(run.continuation))) fail("continuation prompt is unavailable");
    if (!(await exists(run.nodeBin))) fail("node is unavailable");
    if (!(await exists(run.requestCli))) {
      fail("session-inbox request CLI is unavailable");
    }

    await writePrivate(lock.watcherPid, `${process.pid}\n`);
    await recordState(lock, "verifier-owned");
    await writeAtomic(run.ready, `${run.lockToken}\n`);

    const handoffMatches = async () => {
      const text = await readTextOrNull(run.handoff);
      if (text === null || !text.endsWith("\n")) return false;
      const lines = text.split("\n");
      lines.pop();
      return (
        lines.length === 2 &&
        lines[0] === run.lockToken &&
        lines[1] === run.toolCallId
      );
    };

    let handedOff = false;
    for (let poll = 0; poll < run.handoffPolls; poll += 1) {
      if (await exists(lock.cancelled)) fail("foreground cancelled before handoff");
      if (await handoffMatches()) {
        handedOff = true;
        break;
      }
      await sleep(run.handoffPollSeconds);
    }
    if (!handedOff && !(await handoffMatches())) {
      fail("positive handoff was not established");
    }

    const receipt = `${RECEIPT_PREFIX}${run.lockToken}`;
    const authorizationPolls = Math.floor(run.authWaitSeconds / run.pollSeconds) + 1;
    let authorized = false;
    for (let poll = 0; poll < authorizationPolls; poll += 1) {
      let tail;
      try {
        tail = await readEventTail(run.events, run.authScanBytes);
      } catch {
        fail("authorization parser failed");
      }
      const probe = classifyAuthorization(tail, {
        toolCallId: run.toolCallId,
        receipt,
      });
      if (probe.state === "ready") {
        authorized = true;
        break;
      }
      if (probe.state === "cancel") fail(probe.reason);
      await sleep(run.pollSeconds);
    }
    if (!authorized) fail("timed out waiting for the authorizing turn to end");
    await recordState(lock, "authorized");

    let boundary;
    try {
      boundary = (await stat(run.events)).size;
    } catch {
      boundary = null;
    }
    if (boundary === null) fail("could not snapshot the pre-request event boundary");

    const dedupeKey = `self-compact:${run.targetSession}:${run.lockToken}`;
    // Resolving the live target generation is the last definitive check before
    // the publication attempt: an unknown or ambiguous target releases.
    let generations;
    try {
      generations = await resolveFreshGenerations(run.inboxRoot, run.targetSession);
    } catch {
      fail("could not read session-inbox instance heartbeats", { release: true });
    }
    if (generations.length === 0) {
      fail(`no fresh session-inbox instance for ${run.targetSession}`, {
        release: true,
      });
    }
    if (generations.length > 1) {
      fail(`multiple fresh session-inbox instances for ${run.targetSession}`, {
        release: true,
      });
    }
    const targetGeneration = generations[0];

    await writeAtomic(
      lock.publishing,
      `${JSON.stringify(
        {
          attemptedAt: new Date().toISOString(),
          eventOffset: boundary,
          targetSession: run.targetSession,
          targetGeneration,
          toolCallId: run.toolCallId,
          runToken: run.runToken,
          lockToken: run.lockToken,
          dedupeKey,
          receiptRoot: run.inboxRoot,
          watcherPid: process.pid,
        },
        null,
        2,
      )}\n`,
    );
    // Past this marker a side effect may exist; the lock is never reclaimed
    // automatically again.
    await recordState(lock, "publishing");
    failures.release = false;

    logLine(`submitting one session-inbox compact request for session ${run.targetSession}`);
    const { status, output } = await runRequest(run);
    process.stdout.write(output.endsWith("\n") || output === "" ? output : `${output}\n`);

    const publishedMatch = /^request: (.+)$/m.exec(output);
    if (publishedMatch) {
      const pendingPath = publishedMatch[1].trim();
      const id = basename(pendingPath).replace(/\.json$/, "");
      let publishedGeneration = null;
      const pendingText = await readTextOrNull(pendingPath);
      if (pendingText !== null) {
        try {
          publishedGeneration = JSON.parse(pendingText)?.target?.generation ?? null;
        } catch {
          publishedGeneration = null;
        }
      }
      await writeAtomic(
        lock.request,
        `${JSON.stringify(
          {
            id,
            publishedPath: pendingPath,
            targetGeneration,
            publishedGeneration,
            generationMatchesResolved:
              publishedGeneration === null ? null : publishedGeneration === targetGeneration,
            dedupeKey,
            ...receiptPathsFor(run.inboxRoot, id),
          },
          null,
          2,
        )}\n`,
      );
      await recordState(lock, "request-published");
    }

    const classified = classifyRequestOutcome({
      status,
      output,
      targetSession: run.targetSession,
      targetGeneration,
    });
    if (classified.outcome !== "completed") {
      failures.release = classified.release;
      fail(
        classified.release
          ? classified.reason
          : `${classified.reason}; lock retained at ${lock.dir}`,
        { release: classified.release },
      );
    }

    const instructions = await readFile(run.instructions, "utf8");
    let completion = { state: "wait" };
    for (let poll = 0; poll < run.maxPolls; poll += 1) {
      try {
        completion = await probeCompletion(run.events, boundary, instructions);
      } catch {
        fail("could not inspect compaction completion events", { release: false });
      }
      if (completion.state === "success") break;
      if (completion.state === "failed") {
        fail("matching compaction completion reported failure", { release: true });
      }
      if (completion.state === "invalid") {
        fail("matching compaction completion had no checkpoint number", {
          release: false,
        });
      }
      await sleep(run.pollSeconds);
    }
    if (completion.state !== "success") {
      fail(
        `matching token-bound compaction completion was not observed; lock retained at ${lock.dir}`,
        { release: false },
      );
    }
    if (!(completion.checkpointNumber > run.baselineSummaryCount)) {
      fail("matching compaction did not advance the checkpoint number", {
        release: false,
      });
    }
    await recordState(lock, "compact-observed");

    let checkpointLanded = false;
    for (let poll = 0; poll < run.maxPolls; poll += 1) {
      const workspaceText = await readTextOrNull(run.workspace);
      const current = summaryCountOf(workspaceText);
      if (current !== null && current >= completion.checkpointNumber) {
        const count = await countCheckpointFiles(
          run.checkpointsDir,
          completion.checkpointNumber,
        );
        if (count === 1) {
          checkpointLanded = true;
          break;
        }
      }
      await sleep(run.pollSeconds);
    }
    if (!checkpointLanded) {
      fail(
        `matching compact did not produce exactly one checkpoint file for checkpoint ${completion.checkpointNumber}`,
        { release: false },
      );
    }
    await recordState(lock, "checkpoint-observed");

    if (classified.continuation === "failed") {
      fail(
        `compact succeeded but the SDK continuation was not delivered; lock retained at ${lock.dir}`,
        { release: false },
      );
    }

    const continuationText = await readFile(run.continuation, "utf8");
    let continuationState = { state: "wait" };
    for (let poll = 0; poll < run.maxPolls; poll += 1) {
      try {
        continuationState = await probeContinuation(
          run.events,
          completion.completionEnd,
          continuationText,
        );
      } catch {
        fail("could not inspect continuation events", { release: false });
      }
      if (continuationState.state === "success") break;
      if (continuationState.state === "duplicate") {
        fail("session-inbox delivered the continuation more than once", {
          release: false,
        });
      }
      if (
        continuationState.state === "mismatch" ||
        continuationState.state === "activity"
      ) {
        fail("other root activity won the continuation race", { release: false });
      }
      await sleep(run.pollSeconds);
    }
    if (continuationState.state !== "success") {
      fail(
        `matching compact landed without the fixed continuation; lock retained at ${lock.dir}`,
        { release: false },
      );
    }
    await recordState(lock, "continuation-observed");
    await recordState(lock, "completed");

    await releaseRun(run, lock, { release: true });
    logLine(
      `verified token-bound compaction checkpoint ${completion.checkpointNumber} and one SDK continuation`,
    );
    return { ok: true, checkpointNumber: completion.checkpointNumber };
  } catch (error) {
    const release = error instanceof VerifierError ? error.release : failures.release;
    const message = error?.message ?? String(error);
    process.stderr.write(`self-compact cancelled: ${message}\n`);
    try {
      if (!release && (await lockTokenMatches(lock, run.lockToken))) {
        await writeAtomic(
          lock.outcome,
          `${JSON.stringify(
            {
              outcome: "retained",
              reason: message,
              state: await readTrimmedOrNull(lock.state),
              at: new Date().toISOString(),
            },
            null,
            2,
          )}\n`,
        );
      }
      await releaseRun(run, lock, { release });
    } catch (cleanupError) {
      process.stderr.write(
        `self-compact cleanup failed: ${cleanupError?.message ?? cleanupError}\n`,
      );
    }
    return { ok: false, reason: message, released: release };
  }
}

async function releaseRun(run, lock, { release }) {
  await rm(run.ready, { force: true });
  await rm(run.handoff, { force: true });
  if (!release) return;
  await rm(run.instructions, { force: true });
  await rm(run.continuation, { force: true });
  await rm(run.candidate, { force: true });
  await rm(run.runFile, { force: true });
  if (await lockTokenMatches(lock, run.lockToken)) {
    await rm(lock.dir, { recursive: true, force: true });
  }
}

if (isEntrypoint(import.meta.url)) {
  const [runFilePath, ...rest] = process.argv.slice(2);
  if (!runFilePath || rest.length > 0) {
    process.stderr.write("usage: resume-after-compact.mjs RUN_METADATA_FILE\n");
    process.exit(2);
  }
  let outcome;
  try {
    outcome = await verify(runFilePath);
  } catch (error) {
    process.stderr.write(
      `self-compact cancelled: ${error?.message ?? String(error)}\n`,
    );
    process.exit(1);
  }
  process.exit(outcome.ok ? 0 : 1);
}
