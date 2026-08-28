#!/usr/bin/env node

import { spawn } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const extensionDirectory = dirname(fileURLToPath(import.meta.url));
const requestCli = join(extensionDirectory, "request.mjs");
const inboxRoot =
  process.env.COPILOT_SESSION_INBOX_DIR ??
  join(homedir(), ".copilot", "session-inbox");
const instancesDirectory = join(inboxRoot, "instances");
const pluginPath = join(extensionDirectory, "..", "..", "plugin.json");
const expectedVersion = JSON.parse(await readFile(pluginPath, "utf8")).version;
const requestedNames = new Set(process.argv.slice(2));

async function readInstances({ freshOnly = true } = {}) {
  const instances = [];
  for (const filename of await readdir(instancesDirectory)) {
    if (!filename.endsWith(".json")) continue;
    try {
      const instance = JSON.parse(
        await readFile(join(instancesDirectory, filename), "utf8"),
      );
      const age = Date.now() - Date.parse(instance.updatedAt);
      if (
        instance.sessionId &&
        instance.generation &&
        Number.isFinite(age) &&
        age >= 0 &&
        (!freshOnly || age <= 15_000)
      ) {
        instances.push(instance);
      }
    } catch {
      // A malformed or concurrently replaced heartbeat is not a live target.
    }
  }
  return instances;
}

function displayName(instance) {
  return instance.tmuxSession ?? instance.sessionName ?? instance.sessionId;
}

async function runRequest(args, timeoutSeconds = 15) {
  const child = spawn(process.execPath, [requestCli, ...args, "--timeout", `${timeoutSeconds}`], {
    env: process.env,
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  return new Promise((resolve) => {
    child.on("exit", (code, signal) => resolve({ code, signal, stdout, stderr }));
  });
}

async function waitForReload(sessionId, previousGeneration, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const replacement = (await readInstances()).find(
      (instance) =>
        instance.sessionId === sessionId &&
        instance.generation !== previousGeneration &&
        instance.pluginVersion === expectedVersion,
    );
    if (replacement) return replacement;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return undefined;
}

async function bootstrapReload(instance) {
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "extension-reload-"));
  const promptPath = join(temporaryDirectory, "prompt.txt");
  try {
    await writeFile(
      promptPath,
      "Use the extensions_reload tool now to load the installed plugin update. After it succeeds, continue your existing task.",
      { mode: 0o600 },
    );
    return await runRequest(
      [
        "send",
        "--target-session",
        instance.sessionId,
        "--prompt-file",
        promptPath,
        "--mode",
        "immediate",
        "--dedupe-key",
        `extensions-reload-bootstrap:${instance.sessionId}:${expectedVersion}`,
      ],
      15,
    );
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

async function reloadOne(instance) {
  const name = displayName(instance);
  let request = await runRequest([
    "reload-extensions",
    "--target-session",
    instance.sessionId,
  ]);
  if (request.code !== 0) {
    request = await bootstrapReload(instance);
    if (request.code !== 0) {
      return {
        name,
        ok: false,
        restartRequired: true,
        error: (request.stderr || request.stdout).trim(),
      };
    }
  }
  const replacement = await waitForReload(
    instance.sessionId,
    instance.generation,
  );
  return replacement
    ? {
        name,
        ok: true,
        sessionId: instance.sessionId,
        previousGeneration: instance.generation,
        generation: replacement.generation,
        pluginVersion: replacement.pluginVersion,
      }
    : {
        name,
        ok: false,
        restartRequired: true,
        error: `no ${expectedVersion} heartbeat appeared after reload request`,
      };
}

const allInstances = await readInstances({ freshOnly: false });
const live = allInstances.filter(
  (instance) => Date.now() - Date.parse(instance.updatedAt) <= 15_000,
);
const bySession = new Map();
for (const instance of live) {
  const name = displayName(instance);
  if (requestedNames.size > 0 && !requestedNames.has(name)) continue;
  const existing = bySession.get(instance.sessionId);
  if (!existing || Date.parse(instance.updatedAt) > Date.parse(existing.updatedAt)) {
    bySession.set(instance.sessionId, instance);
  }
}

const unavailable = [];
if (requestedNames.size > 0) {
  const found = new Set([...bySession.values()].map(displayName));
  const missing = [...requestedNames].filter((name) => !found.has(name));
  for (const name of missing) {
    const lastInstance = allInstances
      .filter((instance) => displayName(instance) === name)
      .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))[0];
    unavailable.push({
      name,
      ok: false,
      restartRequired: true,
      error: lastInstance
        ? `session-inbox heartbeat is stale since ${lastInstance.updatedAt}`
        : "no session-inbox heartbeat was found",
    });
  }
}

const targets = [...bySession.values()];
if (targets.length === 0 && unavailable.length === 0) {
  console.error("No fresh named session-inbox instances found");
  process.exit(1);
}

const results = [...unavailable, ...(await Promise.all(targets.map(reloadOne)))];
for (const result of results) {
  if (result.ok) {
    console.log(
      `${result.name}: reloaded ${result.pluginVersion} (${result.previousGeneration} -> ${result.generation})`,
    );
  } else {
    console.error(
      `${result.name}: restart required: ${result.error || "extension reload failed"}`,
    );
  }
}
const restartNames = results
  .filter((result) => result.restartRequired)
  .map((result) => result.name);
console.log(
  `Restart required: ${restartNames.length > 0 ? restartNames.join(", ") : "none"}`,
);
if (restartNames.length > 0) process.exitCode = 2;
