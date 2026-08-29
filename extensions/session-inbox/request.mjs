#!/usr/bin/env node

import { createHash, randomBytes } from "node:crypto";
import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

import { createDiagnosticLogger, errorDetails } from "./diagnostics.mjs";

const root = process.env.COPILOT_SESSION_INBOX_DIR ?? join(homedir(), ".copilot", "session-inbox");
const diagnostics = createDiagnosticLogger(
  root,
  `requests-${new Date().toISOString().slice(0, 10)}.jsonl`,
  { component: "request", pid: process.pid },
);
process.on("uncaughtException", (error) => {
  diagnostics.log("request.crashed", { error: errorDetails(error) });
  console.error(error);
  process.exit(1);
});

function usage(message) {
  if (message) {
    diagnostics.log("request.invalid", { error: { message } });
    console.error(`session-inbox-request: ${message}`);
  }
  console.error(
    "usage: request.mjs <send|autopilot|compact|new-session-direct|reload-extensions> (--target-name NAME | --target-tmux NAME | --target-session ID) [options]",
  );
  process.exit(64);
}

function parseArgs(argv) {
  const [kind, ...rest] = argv;
  if (
    ![
      "send",
      "autopilot",
      "compact",
      "new-session-direct",
      "reload-extensions",
    ].includes(kind)
  ) {
    usage("invalid request kind");
  }
  const options = { kind };
  for (let index = 0; index < rest.length; index += 1) {
    const flag = rest[index];
    const value = rest[index + 1];
    if (!flag.startsWith("--") || value === undefined) usage(`invalid option ${flag}`);
    options[flag.slice(2)] = value;
    index += 1;
  }
  return options;
}

async function readRequiredFile(path, label) {
  if (!path) usage(`${label} is required`);
  const text = await readFile(path, "utf8");
  if (!text) usage(`${label} must not be empty`);
  return text;
}

const options = parseArgs(process.argv.slice(2));
const targetCount = [
  options["target-name"],
  options["target-tmux"],
  options["target-session"],
].filter(Boolean).length;
if (targetCount !== 1) {
  usage("provide exactly one target");
}
const timeoutSeconds = Number(options.timeout ?? "15");
if (!Number.isFinite(timeoutSeconds) || timeoutSeconds < 0) usage("invalid --timeout");

async function resolveTarget({ targetName, tmuxSession, sessionId }) {
  const instancesDir = join(root, "instances");
  let names;
  try {
    names = await readdir(instancesDir);
  } catch (error) {
    if (error?.code === "ENOENT") {
      usage(`no live session-inbox instance for ${targetName ?? tmuxSession ?? sessionId}`);
    }
    throw error;
  }
  const freshInstances = [];
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    try {
      const instance = JSON.parse(await readFile(join(instancesDir, name), "utf8"));
      const age = Date.now() - Date.parse(instance.updatedAt);
      if (
        instance.sessionId &&
        instance.generation &&
        Number.isFinite(age) &&
        age >= 0 &&
        age <= 15_000
      ) {
        freshInstances.push(instance);
      }
    } catch {
      // A concurrently replaced or malformed heartbeat is not a live target.
    }
  }
  let matches;
  let resolvedBy;
  if (targetName) {
    const tmuxMatches = freshInstances.filter(
      (instance) => instance.tmuxSession === targetName,
    );
    if (tmuxMatches.length > 0) {
      matches = tmuxMatches;
      resolvedBy = "tmux";
    } else {
      matches = freshInstances.filter(
        (instance) => instance.sessionName === targetName,
      );
      resolvedBy = "session-name";
    }
  } else if (tmuxSession) {
    matches = freshInstances.filter(
      (instance) => instance.tmuxSession === tmuxSession,
    );
    resolvedBy = "tmux";
  } else {
    matches = freshInstances.filter((instance) => instance.sessionId === sessionId);
    resolvedBy = "session-id";
  }
  if (matches.length !== 1) {
    const label = targetName ?? tmuxSession ?? sessionId;
    diagnostics.log("target.unresolved", {
      targetType: targetName ? "name" : tmuxSession ? "tmux" : "session",
      target: label,
      resolvedBy,
      freshMatches: matches.map((match) => ({
        sessionId: match.sessionId,
        generation: match.generation,
      })),
    });
    usage(
      matches.length === 0
        ? `no fresh session-inbox instance for ${label}`
        : `multiple fresh session-inbox instances for ${label}`,
    );
  }
  return {
    ...(targetName ? { targetName, resolvedBy } : {}),
    ...(tmuxSession ? { tmuxSession } : {}),
    sessionId: matches[0].sessionId,
    generation: matches[0].generation,
  };
}

const target = options["target-name"]
  ? await resolveTarget({ targetName: options["target-name"] })
  : options["target-tmux"]
    ? await resolveTarget({ tmuxSession: options["target-tmux"] })
    : await resolveTarget({ sessionId: options["target-session"] });
const id = `${new Date().toISOString().replaceAll(/[-:.]/g, "")}-${process.pid}-${randomBytes(4).toString("hex")}`;
const request = {
  id,
  createdAt: new Date().toISOString(),
  target,
  kind: options.kind,
  ...(options["dedupe-key"] ? { dedupeKey: options["dedupe-key"] } : {}),
};
diagnostics.setContext({
  requestId: id,
  kind: options.kind,
  targetSessionId: target.sessionId,
  targetGeneration: target.generation,
});

switch (options.kind) {
  case "send":
    request.prompt = await readRequiredFile(options["prompt-file"], "--prompt-file");
    request.mode = options.mode ?? "immediate";
    if (request.mode !== "immediate") usage("--mode must be immediate");
    if (options["agent-mode"]) {
      if (!["interactive", "plan", "autopilot", "shell"].includes(options["agent-mode"])) {
        usage("invalid --agent-mode");
      }
      request.agentMode = options["agent-mode"];
    }
    break;
  case "autopilot":
    request.prompt = (
      await readRequiredFile(options["prompt-file"], "--prompt-file")
    ).replace(/(?:\r?\n)+$/, "");
    if (!request.prompt) usage("--prompt-file must contain a non-empty objective");
    break;
  case "compact":
    request.customInstructions = await readRequiredFile(
      options["instructions-file"],
      "--instructions-file",
    );
    if (options["continuation-file"]) {
      request.continuationPrompt = await readRequiredFile(
        options["continuation-file"],
        "--continuation-file",
      );
    }
    break;
  case "new-session-direct":
    request.prompt = await readRequiredFile(options["prompt-file"], "--prompt-file");
    break;
  case "reload-extensions":
    break;
}
if (request.kind === "autopilot" && !request.dedupeKey) {
  const objectiveDigest = createHash("sha256")
    .update(request.prompt)
    .digest("hex");
  request.dedupeKey = `autopilot:session:${target.sessionId}:${objectiveDigest}`;
}

const pendingDir = join(root, "pending");
const completedPath = join(root, "completed", `${id}.json`);
const failedPath = join(root, "failed", `${id}.json`);
const temporaryPath = join(pendingDir, `.${id}.tmp`);
const pendingPath = join(pendingDir, `${id}.json`);
await mkdir(pendingDir, { recursive: true, mode: 0o700 });
await writeFile(temporaryPath, `${JSON.stringify(request, null, 2)}\n`, { mode: 0o600 });
await rename(temporaryPath, pendingPath);
diagnostics.log("request.published", {
  requestPath: pendingPath,
  hasDedupeKey: Boolean(request.dedupeKey),
  mode: request.mode,
  agentMode: request.agentMode,
});
console.log(`request: ${pendingPath}`);

if (timeoutSeconds === 0) process.exit(0);

const deadline = Date.now() + timeoutSeconds * 1_000;
while (Date.now() < deadline) {
  for (const [path, success] of [
    [completedPath, true],
    [failedPath, false],
  ]) {
    try {
      const receipt = JSON.parse(await readFile(path, "utf8"));
      diagnostics.log(success ? "receipt.completed" : "receipt.failed", {
        receiptPath: path,
        receiptStatus: receipt.status,
        delivery: receipt.result?.delivery,
        ambiguousSideEffect: receipt.ambiguousSideEffect === true,
        error: receipt.error ? { message: receipt.error } : undefined,
      });
      console.log(`receipt: ${path}`);
      console.log(JSON.stringify(receipt));
      process.exit(success ? 0 : 1);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 200));
}

diagnostics.log("receipt.timeout", {
  timeoutSeconds,
  pendingPath,
});
console.error(`session-inbox-request: timed out waiting for ${id}`);
process.exit(2);
