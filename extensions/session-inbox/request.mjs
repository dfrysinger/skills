#!/usr/bin/env node

import { randomBytes } from "node:crypto";
import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

function usage(message) {
  if (message) console.error(`session-inbox-request: ${message}`);
  console.error(
    "usage: request.mjs <send|compact|new-session> (--target-tmux NAME | --target-session ID) [options]",
  );
  process.exit(64);
}

function parseArgs(argv) {
  const [kind, ...rest] = argv;
  if (!["send", "compact", "new-session"].includes(kind)) usage("invalid request kind");
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
if (Boolean(options["target-tmux"]) === Boolean(options["target-session"])) {
  usage("provide exactly one target");
}
const timeoutSeconds = Number(options.timeout ?? "15");
if (!Number.isFinite(timeoutSeconds) || timeoutSeconds < 0) usage("invalid --timeout");

const root = process.env.COPILOT_SESSION_INBOX_DIR ?? join(homedir(), ".copilot", "session-inbox");

async function resolveTarget({ tmuxSession, sessionId }) {
  const instancesDir = join(root, "instances");
  let names;
  try {
    names = await readdir(instancesDir);
  } catch (error) {
    if (error?.code === "ENOENT") {
      usage(`no live session-inbox instance for ${tmuxSession ?? sessionId}`);
    }
    throw error;
  }
  const matches = [];
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    try {
      const instance = JSON.parse(await readFile(join(instancesDir, name), "utf8"));
      const age = Date.now() - Date.parse(instance.updatedAt);
      if (
        (tmuxSession ? instance.tmuxSession === tmuxSession : instance.sessionId === sessionId) &&
        instance.sessionId &&
        instance.generation &&
        Number.isFinite(age) &&
        age >= 0 &&
        age <= 15_000
      ) {
        matches.push(instance);
      }
    } catch {
      // A concurrently replaced or malformed heartbeat is not a live target.
    }
  }
  if (matches.length !== 1) {
    const label = tmuxSession ?? sessionId;
    usage(
      matches.length === 0
        ? `no fresh session-inbox instance for ${label}`
        : `multiple fresh session-inbox instances for ${label}`,
    );
  }
  return {
    ...(tmuxSession ? { tmuxSession } : {}),
    sessionId: matches[0].sessionId,
    generation: matches[0].generation,
  };
}

const target = options["target-tmux"]
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

switch (options.kind) {
  case "send":
    request.prompt = await readRequiredFile(options["prompt-file"], "--prompt-file");
    request.mode = options.mode ?? "immediate";
    if (!["enqueue", "immediate"].includes(request.mode)) usage("invalid --mode");
    if (options["agent-mode"]) {
      if (!["interactive", "plan", "autopilot", "shell"].includes(options["agent-mode"])) {
        usage("invalid --agent-mode");
      }
      request.agentMode = options["agent-mode"];
    }
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
  case "new-session":
    request.prompt = await readRequiredFile(options["prompt-file"], "--prompt-file");
    break;
}

const pendingDir = join(root, "pending");
const completedPath = join(root, "completed", `${id}.json`);
const failedPath = join(root, "failed", `${id}.json`);
const temporaryPath = join(pendingDir, `.${id}.tmp`);
const pendingPath = join(pendingDir, `${id}.json`);
await mkdir(pendingDir, { recursive: true, mode: 0o700 });
await writeFile(temporaryPath, `${JSON.stringify(request, null, 2)}\n`, { mode: 0o600 });
await rename(temporaryPath, pendingPath);
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
      console.log(`receipt: ${path}`);
      console.log(JSON.stringify(receipt));
      process.exit(success ? 0 : 1);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 200));
}

console.error(`session-inbox-request: timed out waiting for ${id}`);
process.exit(2);
