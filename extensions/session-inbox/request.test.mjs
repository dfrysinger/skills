import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const requestCli = join(dirname(fileURLToPath(import.meta.url)), "request.mjs");

async function waitForRequest(root) {
  const pending = join(root, "pending");
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const { readdir } = await import("node:fs/promises");
      const [name] = (await readdir(pending)).filter((entry) => entry.endsWith(".json"));
      if (name) {
        return {
          name,
          request: JSON.parse(await readFile(join(pending, name), "utf8")),
        };
      }
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error("request was not written");
}

async function runRequest(root, args) {
  const child = spawn(process.execPath, [requestCli, ...args], {
    env: { ...process.env, COPILOT_SESSION_INBOX_DIR: root },
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const exit = new Promise((resolve) => {
    child.on("exit", (code, signal) => resolve({ code, signal, stdout, stderr }));
  });
  return { child, exit };
}

async function diagnosticEntries(root) {
  const directory = join(root, "logs");
  const { readdir } = await import("node:fs/promises");
  const names = await readdir(directory);
  const entries = [];
  for (const name of names) {
    const content = await readFile(join(directory, name), "utf8");
    entries.push(
      ...content
        .trim()
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line)),
    );
  }
  return entries;
}

test("writes an idle-immediate send request and accepts its receipt", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancePath = join(root, "instances", "hotel-session.json");
    await mkdir(dirname(instancePath), { recursive: true });
    await writeFile(
      instancePath,
      `${JSON.stringify({
        sessionId: "hotel-session",
        tmuxSession: "hotel",
        generation: "generation-1",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
    const promptFile = join(root, "prompt.txt");
    await writeFile(promptFile, "wake the recipient");
    const run = await runRequest(root, [
      "send",
      "--target-tmux",
      "hotel",
      "--prompt-file",
      promptFile,
      "--mode",
      "immediate",
      "--agent-mode",
      "autopilot",
      "--dedupe-key",
      "mailbox:hotel:1",
      "--timeout",
      "3",
    ]);
    const { name, request } = await waitForRequest(root);
    assert.equal(request.kind, "send");
    assert.deepEqual(request.target, {
      tmuxSession: "hotel",
      sessionId: "hotel-session",
      generation: "generation-1",
    });
    assert.equal(request.prompt, "wake the recipient");
    assert.equal(request.mode, "immediate");
    assert.equal(request.agentMode, "autopilot");
    assert.equal(request.dedupeKey, "mailbox:hotel:1");

    const receiptPath = join(root, "completed", name);
    await mkdir(dirname(receiptPath), { recursive: true });
    await writeFile(receiptPath, `${JSON.stringify({ status: "completed" })}\n`);
    const result = await run.exit;
    assert.equal(result.code, 0, result.stderr);
    assert.match(result.stdout, /receipt:/);
    const diagnostics = await diagnosticEntries(root);
    assert.ok(diagnostics.some((entry) => entry.event === "request.published"));
    assert.ok(diagnostics.some((entry) => entry.event === "receipt.completed"));
    assert.doesNotMatch(JSON.stringify(diagnostics), /wake the recipient/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("writes a native autopilot objective request", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancePath = join(root, "instances", "session-1-generation-1.json");
    await mkdir(dirname(instancePath), { recursive: true });
    await writeFile(
      instancePath,
      `${JSON.stringify({
        sessionId: "session-1",
        generation: "generation-1",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
    const promptFile = join(root, "objective.txt");
    await writeFile(promptFile, "finish the persistent objective\r\n\n");
    const run = await runRequest(root, [
      "autopilot",
      "--target-session",
      "session-1",
      "--prompt-file",
      promptFile,
      "--timeout",
      "3",
    ]);
    const { name, request } = await waitForRequest(root);
    assert.equal(request.kind, "autopilot");
    assert.equal(request.prompt, "finish the persistent objective");
    assert.equal(request.mode, undefined);
    assert.equal(request.agentMode, undefined);
    assert.equal(
      request.dedupeKey,
      `autopilot:session:session-1:${createHash("sha256")
        .update("finish the persistent objective")
        .digest("hex")}`,
    );

    const receiptPath = join(root, "completed", name);
    await mkdir(dirname(receiptPath), { recursive: true });
    await writeFile(receiptPath, `${JSON.stringify({ status: "completed" })}\n`);
    const result = await run.exit;
    assert.equal(result.code, 0, result.stderr);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("returns failure when the recipient writes a failed receipt", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancePath = join(root, "instances", "session-1-generation-1.json");
    await mkdir(dirname(instancePath), { recursive: true });
    await writeFile(
      instancePath,
      `${JSON.stringify({
        sessionId: "session-1",
        generation: "generation-1",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
    const promptFile = join(root, "prompt.txt");
    await writeFile(promptFile, "wake the recipient");
    const run = await runRequest(root, [
      "send",
      "--target-session",
      "session-1",
      "--prompt-file",
      promptFile,
      "--timeout",
      "3",
    ]);
    const { name, request } = await waitForRequest(root);
    assert.deepEqual(request.target, {
      sessionId: "session-1",
      generation: "generation-1",
    });
    const receiptPath = join(root, "failed", name);
    await mkdir(dirname(receiptPath), { recursive: true });
    await writeFile(
      receiptPath,
      `${JSON.stringify({ status: "failed", error: "recipient rejected request" })}\n`,
    );
    const result = await run.exit;
    assert.equal(result.code, 1);
    assert.match(result.stdout, /recipient rejected request/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects ambiguous targets before writing a request", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const result = await (
      await runRequest(root, ["new-session", "--prompt-file", "unused", "--timeout", "0"])
    ).exit;
    assert.equal(result.code, 64);
    assert.match(result.stderr, /provide exactly one target/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects an invalid timeout before writing a request", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const result = await (
      await runRequest(root, [
        "send",
        "--target-session",
        "session-1",
        "--prompt-file",
        "unused",
        "--timeout",
        "invalid",
      ])
    ).exit;
    assert.equal(result.code, 64);
    assert.match(result.stderr, /invalid --timeout/);
    await assert.rejects(readFile(join(root, "pending")), {
      code: "ENOENT",
    });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects multiple fresh instances for one tmux name", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancesDir = join(root, "instances");
    await mkdir(instancesDir, { recursive: true });
    for (const sessionId of ["session-1", "session-2"]) {
      await writeFile(
        join(instancesDir, `${sessionId}.json`),
        `${JSON.stringify({
          sessionId,
          tmuxSession: "hotel",
          generation: `generation-${sessionId}`,
          updatedAt: new Date().toISOString(),
        })}\n`,
      );
    }
    const promptFile = join(root, "prompt.txt");
    await writeFile(promptFile, "wake the recipient");
    const result = await (
      await runRequest(root, [
        "send",
        "--target-tmux",
        "hotel",
        "--prompt-file",
        promptFile,
        "--timeout",
        "0",
      ])
    ).exit;
    assert.equal(result.code, 64);
    assert.match(result.stderr, /multiple fresh session-inbox instances/);
    const diagnostics = await diagnosticEntries(root);
    assert.ok(diagnostics.some((entry) => entry.event === "target.unresolved"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects multiple fresh generations for one session ID", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancesDir = join(root, "instances");
    await mkdir(instancesDir, { recursive: true });
    for (const generation of ["generation-1", "generation-2"]) {
      await writeFile(
        join(instancesDir, `session-1-${generation}.json`),
        `${JSON.stringify({
          sessionId: "session-1",
          generation,
          updatedAt: new Date().toISOString(),
        })}\n`,
      );
    }
    const promptFile = join(root, "prompt.txt");
    await writeFile(promptFile, "wake the recipient");
    const result = await (
      await runRequest(root, [
        "send",
        "--target-session",
        "session-1",
        "--prompt-file",
        promptFile,
        "--timeout",
        "0",
      ])
    ).exit;
    assert.equal(result.code, 64);
    assert.match(result.stderr, /multiple fresh session-inbox instances/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("target name prefers a fresh tmux identity over session-name fallbacks", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancesDir = join(root, "instances");
    await mkdir(instancesDir, { recursive: true });
    await writeFile(
      join(instancesDir, "tmux-session.json"),
      `${JSON.stringify({
        sessionId: "tmux-session",
        tmuxSession: "hotel",
        sessionName: "other-name",
        generation: "tmux-generation",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
    await writeFile(
      join(instancesDir, "named-session.json"),
      `${JSON.stringify({
        sessionId: "named-session",
        sessionName: "hotel",
        generation: "named-generation",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
    const promptFile = join(root, "prompt.txt");
    await writeFile(promptFile, "wake the recipient");
    const run = await runRequest(root, [
      "send",
      "--target-name",
      "hotel",
      "--prompt-file",
      promptFile,
      "--timeout",
      "0",
    ]);
    const { request } = await waitForRequest(root);
    assert.deepEqual(request.target, {
      targetName: "hotel",
      resolvedBy: "tmux",
      sessionId: "tmux-session",
      generation: "tmux-generation",
    });
    assert.equal((await run.exit).code, 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("target name falls back to the current live session name", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancePath = join(root, "instances", "named-session.json");
    await mkdir(dirname(instancePath), { recursive: true });
    await writeFile(
      instancePath,
      `${JSON.stringify({
        sessionId: "named-session",
        sessionName: "hotel",
        generation: "named-generation",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
    const promptFile = join(root, "prompt.txt");
    await writeFile(promptFile, "wake the recipient");
    const run = await runRequest(root, [
      "send",
      "--target-name",
      "hotel",
      "--prompt-file",
      promptFile,
      "--timeout",
      "0",
    ]);
    const { request } = await waitForRequest(root);
    assert.deepEqual(request.target, {
      targetName: "hotel",
      resolvedBy: "session-name",
      sessionId: "named-session",
      generation: "named-generation",
    });
    assert.equal((await run.exit).code, 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("target name rejects multiple fresh sessions with the same session name", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-inbox-request-"));
  try {
    const instancesDir = join(root, "instances");
    await mkdir(instancesDir, { recursive: true });
    for (const sessionId of ["session-1", "session-2"]) {
      await writeFile(
        join(instancesDir, `${sessionId}.json`),
        `${JSON.stringify({
          sessionId,
          sessionName: "hotel",
          generation: `generation-${sessionId}`,
          updatedAt: new Date().toISOString(),
        })}\n`,
      );
    }
    const promptFile = join(root, "prompt.txt");
    await writeFile(promptFile, "wake the recipient");
    const result = await (
      await runRequest(root, [
        "send",
        "--target-name",
        "hotel",
        "--prompt-file",
        promptFile,
        "--timeout",
        "0",
      ])
    ).exit;
    assert.equal(result.code, 64);
    assert.match(result.stderr, /multiple fresh session-inbox instances/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
