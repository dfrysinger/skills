// Deterministic guards for the Claude native mailbox adapter, watcher and
// SessionStart hook launcher. Pipe behavior is exercised against fake
// named-pipe servers (Windows named pipes on win32, unix sockets elsewhere);
// post-message failure shapes use injected fake connections. All tokens are
// random synthetic values generated per run.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { EventEmitter } from "node:events";
import net from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { inspect } from "node:util";
import { fileURLToPath } from "node:url";

import {
  ClaudeEnvironmentError,
  claudeSocketGeneration,
  createClaudeWakeupAdapter,
  isProcessAlive,
  parseClaudePid,
  readClaudeEnvironment,
} from "./claude-mailbox-adapter.mjs";
import { launchClaudeWatcher } from "./claude-mailbox-hook.mjs";
import { runClaudeWatcher } from "./claude-mailbox-watcher.mjs";
import { createMailbox } from "./mailbox-core.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const hookPath = join(scriptDirectory, "claude-mailbox-hook.mjs");
const POSITIVE_PROMPT = /^check mailbox; skip if empty \[mb:[^\]]+\]$/;
const WATCH_KEY = "_providers/claude/alpha";
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const newToken = () => `synthetic-${randomBytes(18).toString("hex")}`;

async function sandbox(prefix, body) {
  const root = await mkdtemp(join(tmpdir(), `claude-mailbox-${prefix}-`));
  try {
    await body(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

async function waitFor(description, probe, timeoutMs = 6_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await probe();
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${description}`);
    await sleep(25);
  }
}

function trackSettled(promise) {
  const state = { settled: false, error: undefined, value: undefined };
  state.promise = promise.then(
    (value) => {
      state.settled = true;
      state.value = value;
    },
    (error) => {
      state.settled = true;
      state.error = error;
    },
  );
  return state;
}

async function readIfExists(path) {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return undefined;
    throw error;
  }
}

async function listFiles(directory) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await listFiles(path)));
    else files.push(path);
  }
  return files;
}

async function assertTokenAbsentFromFiles(root, token) {
  for (const file of await listFiles(root)) {
    assert.ok(
      !(await readFile(file)).includes(token),
      `token leaked into durable file ${file.slice(root.length)}`,
    );
  }
}

function pipePath(label) {
  const id = `${process.pid}-${randomBytes(4).toString("hex")}`;
  return process.platform === "win32"
    ? `\\\\.\\pipe\\LOCAL\\cc-msg-test-${label}-${id}`
    : join(tmpdir(), `cc-msg-test-${label}-${id}.sock`);
}

// mode: "accept" (default), "reject-after-auth" (close once auth arrives),
// "never-close" (accept and keep the connection open after the client ends).
async function fakePipe({ token, mode = "accept", label = "p" }) {
  const path = pipePath(label);
  const connections = [];
  const sockets = new Set();
  const server = net.createServer((socket) => {
    const record = { chunks: [], times: [], clientEnded: false, authValid: undefined };
    connections.push(record);
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
    socket.on("error", () => {});
    let buffer = "";
    socket.on("data", (chunk) => {
      record.chunks.push(chunk.toString("utf8"));
      record.times.push(Date.now());
      buffer += chunk.toString("utf8");
      if (record.authValid === undefined && buffer.includes("\n")) {
        try {
          record.authValid = JSON.parse(buffer.split("\n")[0]).token === token;
        } catch {
          record.authValid = false;
        }
        if (!record.authValid || mode === "reject-after-auth") socket.destroy();
      }
    });
    socket.on("end", () => {
      record.clientEnded = true;
    });
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(path, resolve);
  });
  return {
    path,
    connections,
    raw: (index) => connections[index]?.chunks.join("") ?? "",
    async close() {
      for (const socket of sockets) socket.destroy();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

function authLineFor(token) {
  return `${JSON.stringify({ type: "auth", token })}\n`;
}

function messageLineFor(prompt) {
  return `${JSON.stringify({ type: "user", message: { role: "user", content: prompt } })}\n`;
}

const wakeRequest = (prompt = "check mailbox; skip if empty [mb:test0001]") => ({
  address: "claude:alpha",
  provider: "claude",
  name: "alpha",
  envelopeId: "20261103T100000Z-test0001",
  attemptId: "attempt-1",
  prompt,
});

class FakeConnection extends EventEmitter {
  constructor(script) {
    super();
    this.writes = [];
    this.destroyed = false;
    this.ended = false;
    this.script = script;
    process.nextTick(() => script.onCreate?.(this));
  }
  write(data, callback) {
    this.writes.push(String(data));
    process.nextTick(() => callback?.(this.script.writeError?.(this.writes.length)));
    setImmediate(() => this.script.onWrite?.(this, this.writes.length));
    return true;
  }
  end() {
    this.ended = true;
    setImmediate(() => this.script.onEnd?.(this));
  }
  destroy() {
    this.destroyed = true;
  }
}

function injected(script) {
  const created = [];
  return {
    created,
    connect: () => {
      const connection = new FakeConnection(script);
      created.push(connection);
      return connection;
    },
  };
}

function errorWithCode(code, message = code) {
  return Object.assign(new Error(message), { code });
}

function adapterFor(options) {
  return createClaudeWakeupAdapter({
    address: "claude:alpha",
    claudePid: process.pid,
    authGapMs: 20,
    isAlive: () => true,
    ...options,
  });
}

// ---------------------------------------------------------------------------
// Generation, environment, liveness
// ---------------------------------------------------------------------------

test("generation is the plain SHA-256 hex of the socket address and nothing else", () => {
  assert.equal(
    claudeSocketGeneration("a"),
    "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
  );
  const socket = "\\\\.\\pipe\\LOCAL\\cc-msg-0123456789abcdef0123456789abcdef";
  const generation = claudeSocketGeneration(socket);
  assert.equal(generation, createHash("sha256").update(socket, "utf8").digest("hex"));
  assert.match(generation, /^[0-9a-f]{64}$/);
  assert.notEqual(generation, claudeSocketGeneration(`${socket}0`));
  assert.throws(() => claudeSocketGeneration(""), ClaudeEnvironmentError);
});

test("environment validation names variables and never echoes values", () => {
  const token = newToken();
  const base = {
    MAILBOX_SELF_ADDRESS: "claude:alpha",
    CLAUDE_CODE_MESSAGING_SOCKET: "\\\\.\\pipe\\LOCAL\\cc-msg-x",
    CLAUDE_CODE_MESSAGING_TOKEN: token,
    CLAUDE_PID: "4242",
  };
  assert.deepEqual(readClaudeEnvironment(base), {
    address: "claude:alpha",
    name: "alpha",
    socket: base.CLAUDE_CODE_MESSAGING_SOCKET,
    token,
    claudePid: 4242,
  });

  const rejected = [
    { ...base, MAILBOX_SELF_ADDRESS: undefined },
    { ...base, CLAUDE_CODE_MESSAGING_SOCKET: "" },
    { ...base, CLAUDE_CODE_MESSAGING_TOKEN: undefined },
    { ...base, CLAUDE_PID: undefined },
    { ...base, MAILBOX_SELF_ADDRESS: "alpha" },
    { ...base, MAILBOX_SELF_ADDRESS: "codex:alpha" },
    { ...base, MAILBOX_SELF_ADDRESS: "claude:alpha@thinkpad" },
    ...["0", "-5", "12x", "1.5", " 7", "abc"].map((CLAUDE_PID) => ({ ...base, CLAUDE_PID })),
  ];
  for (const env of rejected) {
    assert.throws(
      () => readClaudeEnvironment(env),
      (error) => error instanceof ClaudeEnvironmentError && !error.message.includes(token),
    );
  }
  assert.throws(
    () => readClaudeEnvironment({ ...base, CLAUDE_PID: undefined, CLAUDE_CODE_MESSAGING_TOKEN: undefined }),
    /CLAUDE_CODE_MESSAGING_TOKEN, CLAUDE_PID/,
  );
  assert.equal(parseClaudePid("13964"), 13964);
  assert.equal(parseClaudePid("0"), undefined);
});

test("liveness helper reports a live child and a killed child", async () => {
  const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore" });
  try {
    assert.equal(isProcessAlive(child.pid), true);
    child.kill();
    await waitFor("child exit", () => !isProcessAlive(child.pid));
  } finally {
    child.kill();
  }
});

// ---------------------------------------------------------------------------
// Framing and outcomes against a fake named-pipe server
// ---------------------------------------------------------------------------

test("claude-native-contract: auth line, gap, then one fixed user line; clean close is submitted", async () => {
  const token = newToken();
  const pipe = await fakePipe({ token, label: "framing" });
  try {
    const authGapMs = 150;
    const adapter = adapterFor({ socket: pipe.path, token, authGapMs });
    const prompt = "check mailbox; skip if empty [mb:test0001]";
    const outcome = await adapter.wake(wakeRequest(prompt));

    assert.equal(outcome.outcome, "submitted");
    assert.equal(outcome.releaseWatcher, undefined);
    assert.equal(pipe.connections.length, 1, "one connection per attempt");
    const connection = pipe.connections[0];
    assert.equal(connection.authValid, true);
    assert.equal(pipe.raw(0), authLineFor(token) + messageLineFor(prompt));
    assert.equal(
      messageLineFor(prompt),
      `{"type":"user","message":{"role":"user","content":"${prompt}"}}\n`,
    );
    const messageIndex = connection.chunks.findIndex((chunk) => chunk.includes('"type":"user"'));
    assert.ok(messageIndex > 0, "message arrives in a later write than the auth line");
    assert.ok(
      connection.times[messageIndex] - connection.times[0] >= authGapMs - 40,
      "message waits roughly the auth gap",
    );
    await waitFor("client end", () => connection.clientEnded);
    assert.doesNotMatch(JSON.stringify(outcome), new RegExp(token));
  } finally {
    await pipe.close();
  }
});

test("pipe closed after auth defers and releases without writing a message byte", async () => {
  const token = newToken();
  const pipe = await fakePipe({ token, mode: "reject-after-auth", label: "reject" });
  try {
    const adapter = adapterFor({ socket: pipe.path, token, authGapMs: 120 });
    const outcome = await adapter.wake(wakeRequest());
    assert.equal(outcome.outcome, "deferred");
    assert.equal(outcome.releaseWatcher, true);
    assert.equal(pipe.raw(0), authLineFor(token), "only the auth line was written");
  } finally {
    await pipe.close();
  }
});

test("a wrong token is closed by the server and defers with release", async () => {
  const pipe = await fakePipe({ token: newToken(), label: "wrong-token" });
  try {
    const wrong = newToken();
    const adapter = adapterFor({ socket: pipe.path, token: wrong, authGapMs: 120 });
    const outcome = await adapter.wake(wakeRequest());
    assert.equal(outcome.outcome, "deferred");
    assert.equal(outcome.releaseWatcher, true);
    assert.equal(pipe.raw(0), authLineFor(wrong));
    assert.ok(!JSON.stringify(outcome).includes(wrong));
  } finally {
    await pipe.close();
  }
});

test("missing pipe (ENOENT) is a terminal pre-write error: deferred plus releaseWatcher", async () => {
  const adapter = adapterFor({ socket: pipePath("missing"), token: newToken() });
  const outcome = await adapter.wake(wakeRequest());
  assert.equal(outcome.outcome, "deferred");
  assert.equal(outcome.releaseWatcher, true);
  assert.match(outcome.detail, /ENOENT/);
});

test("a connection that never closes after the message is ambiguous, not submitted", async () => {
  const token = newToken();
  const stalled = injected({ onCreate: (connection) => connection.emit("connect") });
  const outcome = await adapterFor({
    connect: stalled.connect,
    socket: "fake",
    token,
    closeTimeoutMs: 100,
  }).wake(wakeRequest());
  assert.equal(outcome.outcome, "ambiguous");
  assert.equal(outcome.releaseWatcher, undefined);
  assert.deepEqual(stalled.created[0].writes, [authLineFor(token), messageLineFor(wakeRequest().prompt)]);
  assert.equal(stalled.created[0].destroyed, true);
});

test("pre-write error classes: terminal releases, transient or timeout keeps the watcher", async () => {
  const token = newToken();
  const cases = [
    { code: "ENOENT", release: true },
    { code: "ECONNREFUSED", release: true },
    { code: "EBUSY", release: false },
    { code: "EPIPE", release: false },
    { code: "EACCES", release: false },
  ];
  for (const { code, release } of cases) {
    const { connect, created } = injected({
      onCreate: (connection) => connection.emit("error", errorWithCode(code, `${code} ${token}`)),
    });
    const outcome = await adapterFor({ connect, socket: "fake", token }).wake(wakeRequest());
    assert.equal(outcome.outcome, "deferred", code);
    assert.equal(outcome.releaseWatcher === true, release, code);
    assert.deepEqual(created[0].writes, [], `${code}: nothing written before connect`);
    assert.ok(!JSON.stringify(outcome).includes(token), `${code}: error text must not leak`);
  }

  const timedOut = injected({});
  const outcome = await adapterFor({
    connect: timedOut.connect,
    socket: "fake",
    token,
    connectTimeoutMs: 50,
  }).wake(wakeRequest());
  assert.equal(outcome.outcome, "deferred");
  assert.equal(outcome.releaseWatcher, undefined);
  assert.deepEqual(timedOut.created[0].writes, []);
  assert.equal(timedOut.created[0].destroyed, true);

  const throwing = await adapterFor({
    connect: () => {
      throw errorWithCode("ERR_INVALID_ARG_VALUE", token);
    },
    socket: "fake",
    token,
  }).wake(wakeRequest());
  assert.equal(throwing.outcome, "deferred");
  assert.ok(!JSON.stringify(throwing).includes(token));
});

test("errors during the auth gap defer and release without a message write", async () => {
  const token = newToken();
  const closing = injected({
    onCreate: (connection) => connection.emit("connect"),
    onWrite: (connection) => {
      connection.emit("end");
      connection.emit("close", false);
    },
  });
  const closed = await adapterFor({ connect: closing.connect, socket: "fake", token }).wake(wakeRequest());
  assert.equal(closed.outcome, "deferred");
  assert.equal(closed.releaseWatcher, true);
  assert.deepEqual(closing.created[0].writes, [authLineFor(token)]);

  const erroring = injected({
    onCreate: (connection) => connection.emit("connect"),
    onWrite: (connection) => connection.emit("error", errorWithCode("ECONNRESET", token)),
  });
  const reset = await adapterFor({ connect: erroring.connect, socket: "fake", token }).wake(wakeRequest());
  assert.equal(reset.outcome, "deferred");
  assert.equal(reset.releaseWatcher, true);
  assert.deepEqual(erroring.created[0].writes, [authLineFor(token)]);
  assert.ok(!JSON.stringify(reset).includes(token));
});

test("post-message connection errors are ambiguous and never leak error text", async () => {
  const token = newToken();
  const resetAfterMessage = injected({
    onCreate: (connection) => connection.emit("connect"),
    onWrite: (connection, count) => {
      if (count === 2) connection.emit("error", errorWithCode("ECONNRESET", `reset ${token}`));
    },
  });
  const reset = await adapterFor({ connect: resetAfterMessage.connect, socket: "fake", token }).wake(wakeRequest());
  assert.equal(reset.outcome, "ambiguous");
  assert.equal(reset.releaseWatcher, undefined);
  assert.match(reset.detail, /ECONNRESET/);
  assert.ok(!JSON.stringify(reset).includes(token));
  assert.deepEqual(resetAfterMessage.created[0].writes, [
    authLineFor(token),
    messageLineFor(wakeRequest().prompt),
  ]);

  const closedWithError = injected({
    onCreate: (connection) => connection.emit("connect"),
    onEnd: (connection) => connection.emit("close", true),
  });
  const withError = await adapterFor({ connect: closedWithError.connect, socket: "fake", token }).wake(wakeRequest());
  assert.equal(withError.outcome, "ambiguous");

  const failedWrite = injected({
    onCreate: (connection) => connection.emit("connect"),
    writeError: (count) => (count === 2 ? errorWithCode("EPIPE") : undefined),
    onEnd: (connection) => connection.emit("close", false),
  });
  const writeFailure = await adapterFor({ connect: failedWrite.connect, socket: "fake", token }).wake(wakeRequest());
  assert.equal(writeFailure.outcome, "ambiguous");

  const clean = injected({
    onCreate: (connection) => connection.emit("connect"),
    onEnd: (connection) => connection.emit("close", false),
  });
  const submitted = await adapterFor({ connect: clean.connect, socket: "fake", token }).wake(wakeRequest());
  assert.equal(submitted.outcome, "submitted");
  assert.equal(clean.created[0].ended, true);
});

test("liveness and binding gates never touch the pipe", async () => {
  const token = newToken();
  const probe = injected({});
  const dead = await adapterFor({
    connect: probe.connect,
    socket: "fake",
    token,
    claudePid: 999_999,
    isAlive: (pid) => {
      assert.equal(pid, 999_999);
      return false;
    },
  }).wake(wakeRequest());
  assert.equal(dead.outcome, "deferred");
  assert.equal(dead.releaseWatcher, true);

  const adapter = adapterFor({ connect: probe.connect, socket: "fake", token });
  const other = await adapter.wake({ ...wakeRequest(), address: "claude:beta", name: "beta" });
  assert.equal(other.outcome, "deferred");
  assert.equal(other.releaseWatcher, undefined);
  const wrongProvider = await adapter.wake({ ...wakeRequest(), provider: "codex" });
  assert.equal(wrongProvider.outcome, "deferred");
  const emptyPrompt = await adapter.wake(wakeRequest(""));
  assert.equal(emptyPrompt.outcome, "deferred");
  assert.equal(probe.created.length, 0, "no connection was attempted");
});

test("the token is held only in the adapter closure", () => {
  const token = newToken();
  const adapter = adapterFor({ socket: "fake", token });
  assert.ok(!inspect(adapter, { showHidden: true, depth: 5 }).includes(token));
  assert.ok(!JSON.stringify(adapter).includes(token));
  assert.throws(
    () => createClaudeWakeupAdapter({ address: "claude:alpha", socket: "fake", token: "" }),
    ClaudeEnvironmentError,
  );
});

// ---------------------------------------------------------------------------
// Watcher with the real mailbox core: lock generations and delivery
// ---------------------------------------------------------------------------

function mailboxOptions(root) {
  return {
    mailboxRoot: join(root, "mailbox"),
    stateRoot: join(root, "state"),
    remoteMailboxRoot: null,
    machineName: null,
    terminalPokeCli: null,
    requestCli: join(root, "unused-request.mjs"),
  };
}

function watcherEnv(socket, token, claudePid = process.pid) {
  return {
    MAILBOX_SELF_ADDRESS: "claude:alpha",
    CLAUDE_CODE_MESSAGING_SOCKET: socket,
    CLAUDE_CODE_MESSAGING_TOKEN: token,
    CLAUDE_PID: String(claudePid),
  };
}

function startWatcher(root, env, extra = {}) {
  const controller = new AbortController();
  const watching = trackSettled(
    runClaudeWatcher({
      env,
      createMailbox,
      mailboxOptions: mailboxOptions(root),
      signal: controller.signal,
      intervalMs: 100,
      livenessMs: 50,
      adapterOptions: { authGapMs: 20 },
      ...extra,
    }),
  );
  return { controller, watching };
}

test("watcher aborts sibling routes when one route fails", async () => {
  let siblingAborted = false;
  const mailbox = {
    watchAddresses(address) {
      return [address, `${address}@surface-pro`];
    },
    async watch(address, { signal }) {
      if (address.endsWith("@surface-pro")) {
        throw new Error("synthetic route failure");
      }
      await new Promise((resolve) => {
        signal.addEventListener(
          "abort",
          () => {
            siblingAborted = true;
            resolve();
          },
          { once: true },
        );
      });
    },
  };
  await assert.rejects(
    runClaudeWatcher({
      env: watcherEnv("synthetic-pipe", newToken()),
      createMailbox: () => mailbox,
      isAlive: () => true,
    }),
    /synthetic route failure/,
  );
  assert.equal(siblingAborted, true);
});

async function readLockOwner(root) {
  const text = await readIfExists(join(root, "state", "watchers", ...`${WATCH_KEY}.lock`.split("/")));
  try {
    return text ? JSON.parse(text) : undefined;
  } catch {
    return undefined;
  }
}

async function waitForOwner(root, generation, watching) {
  return waitFor(`lock owned by ${generation.slice(0, 8)}`, async () => {
    if (watching?.error) throw watching.error;
    const owner = await readLockOwner(root);
    return owner?.generation === generation ? owner : undefined;
  });
}

function unverifiedFile(root, id) {
  return join(root, "state", "notified", ...WATCH_KEY.split("/"), `${id}.unverified`);
}

async function sendProviderMail(root) {
  return createMailbox(mailboxOptions(root)).send({
    recipient: "claude:alpha",
    sender: "whisky",
    summary: "wakeup state",
    message: "durable body",
    wake: false,
  });
}

test("the watcher delivers durable mail once through the pipe and records a submitted marker", async () => {
  await sandbox("deliver", async (root) => {
    const token = newToken();
    const pipe = await fakePipe({ token, label: "deliver" });
    const { controller, watching } = startWatcher(root, watcherEnv(pipe.path, token));
    try {
      await waitForOwner(root, claudeSocketGeneration(pipe.path), watching);
      const sent = await sendProviderMail(root);
      const id = sent.envelope.id;
      const marker = await waitFor("submitted marker", async () => {
        const text = await readIfExists(unverifiedFile(root, id));
        if (!text) return undefined;
        const value = JSON.parse(text);
        return value.outcome === "submitted" ? value : undefined;
      });
      assert.equal(marker.outcome, "submitted");
      assert.equal(pipe.connections.length, 1);
      const [authLine, messageLine, rest] = pipe.raw(0).split("\n");
      assert.equal(authLine, JSON.stringify({ type: "auth", token }));
      const message = JSON.parse(messageLine);
      assert.deepEqual(Object.keys(message), ["type", "message"]);
      assert.equal(message.type, "user");
      assert.equal(message.message.role, "user");
      assert.match(message.message.content, POSITIVE_PROMPT);
      assert.equal(rest, "");
      await sleep(400);
      assert.equal(pipe.connections.length, 1, "terminal outcomes are never replayed");
    } finally {
      controller.abort();
      await watching.promise;
      await pipe.close();
    }
    assert.equal(watching.error, undefined);
    assert.equal(await readLockOwner(root), undefined, "lock released on exit");
    await assertTokenAbsentFromFiles(root, token);
  });
});

test("generation-ownership: same socket re-fire exits; changed socket waits then takes over after release", async () => {
  await sandbox("generation", async (root) => {
    const tokenA = newToken();
    const tokenB = newToken();
    const pipeA = await fakePipe({ token: tokenA, label: "gen-a" });
    const pipeB = await fakePipe({ token: tokenB, label: "gen-b" });
    const generationA = claudeSocketGeneration(pipeA.path);
    const generationB = claudeSocketGeneration(pipeB.path);
    const watcherA = startWatcher(root, watcherEnv(pipeA.path, tokenA));
    let watcherB;
    let refire;
    try {
      const ownerA = await waitForOwner(root, generationA, watcherA.watching);

      refire = startWatcher(root, watcherEnv(pipeA.path, tokenA));
      await waitFor("same-generation re-fire exit", () => refire.watching.settled);
      assert.equal(refire.watching.error, undefined);
      assert.deepEqual(await readLockOwner(root), ownerA, "re-fire left the lock untouched");
      assert.equal(watcherA.watching.settled, false);

      watcherB = startWatcher(root, watcherEnv(pipeB.path, tokenB));
      await sleep(400);
      assert.equal(watcherB.watching.settled, false, "changed generation waits");
      assert.deepEqual(await readLockOwner(root), ownerA);
      assert.equal(pipeB.connections.length, 0);

      // Claude A's pipe disappears: the old watcher hits ENOENT before any
      // write, releases, and the waiting generation retries the same mail.
      await pipeA.close();
      const sent = await sendProviderMail(root);
      await waitFor("old watcher release", () => watcherA.watching.settled);
      assert.equal(watcherA.watching.error, undefined);
      await waitForOwner(root, generationB, watcherB.watching);
      await waitFor("waiter delivery", () => pipeB.connections.length === 1);
      assert.equal(pipeB.raw(0).split("\n")[0], JSON.stringify({ type: "auth", token: tokenB }));
      await waitFor("submitted marker", () => readIfExists(unverifiedFile(root, sent.envelope.id)));
      assert.equal(pipeA.connections.length, 0, "dead endpoint was never written to");
    } finally {
      watcherA.controller.abort();
      refire?.controller.abort();
      watcherB?.controller.abort();
      await Promise.all([watcherA.watching.promise, refire?.watching.promise, watcherB?.watching.promise]);
      await pipeA.close().catch(() => {});
      await pipeB.close();
    }
    await assertTokenAbsentFromFiles(root, tokenA);
    await assertTokenAbsentFromFiles(root, tokenB);
  });
});

test("watcher exits and releases its lock when CLAUDE_PID dies; a dead PID never starts", async () => {
  await sandbox("liveness", async (root) => {
    const token = newToken();
    const pipe = await fakePipe({ token, label: "liveness" });
    try {
      let alive = true;
      const { watching } = startWatcher(root, watcherEnv(pipe.path, token, 4242), {
        isAlive: () => alive,
      });
      await waitForOwner(root, claudeSocketGeneration(pipe.path), watching);
      alive = false;
      await waitFor("watcher exit after Claude death", () => watching.settled);
      assert.equal(watching.error, undefined);
      assert.equal(await readLockOwner(root), undefined);

      const dead = startWatcher(root, watcherEnv(pipe.path, token, 4242), { isAlive: () => false });
      await dead.watching.promise;
      assert.deepEqual(dead.watching.value, {
        generation: claudeSocketGeneration(pipe.path),
        started: false,
      });
      assert.equal(await readLockOwner(root), undefined);

      await assert.rejects(
        runClaudeWatcher({ env: { ...watcherEnv(pipe.path, token), CLAUDE_PID: "nope" } }),
        ClaudeEnvironmentError,
      );
    } finally {
      await pipe.close();
    }
  });
});

// ---------------------------------------------------------------------------
// Hook launcher
// ---------------------------------------------------------------------------

test("hook launcher spawns the watcher detached with the environment and no secret on argv", () => {
  const token = newToken();
  const env = watcherEnv("\\\\.\\pipe\\LOCAL\\cc-msg-x", token, 4242);
  const calls = [];
  let unrefs = 0;
  const outcome = launchClaudeWatcher({
    env,
    execPath: "node-exec",
    watcherPath: "watcher.mjs",
    spawnProcess: (...args) => {
      calls.push(args);
      return { pid: 77, on() {}, unref: () => unrefs++ };
    },
  });
  assert.deepEqual(outcome, { started: true, pid: 77 });
  assert.equal(unrefs, 1);
  assert.equal(calls.length, 1);
  const [command, args, options] = calls[0];
  assert.equal(command, "node-exec");
  assert.deepEqual(args, ["watcher.mjs"]);
  assert.equal(options.detached, true);
  assert.equal(options.stdio, "ignore");
  assert.equal(options.windowsHide, true);
  assert.equal(options.env, env, "private environment is inherited, not copied to argv");
  assert.ok(!JSON.stringify([command, args]).includes(token));
});

test("hook launcher spawns nothing for incomplete environments and survives spawn failure", () => {
  const token = newToken();
  let spawned = 0;
  const spawnProcess = () => {
    spawned++;
    return { pid: 1, on() {}, unref() {} };
  };
  const missing = launchClaudeWatcher({
    env: { ...watcherEnv("sock", token), CLAUDE_PID: undefined },
    spawnProcess,
  });
  assert.equal(missing.started, false);
  assert.match(missing.reason, /CLAUDE_PID/);
  assert.ok(!missing.reason.includes(token));
  assert.equal(
    launchClaudeWatcher({ env: { ...watcherEnv("sock", token), MAILBOX_SELF_ADDRESS: "alpha" }, spawnProcess }).started,
    false,
  );
  assert.equal(spawned, 0);

  const failed = launchClaudeWatcher({
    env: watcherEnv("sock", token),
    spawnProcess: () => {
      throw errorWithCode("ENOENT", token);
    },
  });
  assert.equal(failed.started, false);
  assert.ok(!failed.reason.includes(token));
});

function runHook(env, stdin = '{"hook_event_name":"SessionStart","source":"startup"}') {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const child = spawn(process.execPath, [hookPath], { env, stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr, elapsedMs: Date.now() - started }));
    child.stdin.end(stdin);
  });
}

function cleanEnvironment(extra) {
  const env = {};
  for (const [name, value] of Object.entries(process.env)) {
    if (/^(MAILBOX_|COPILOT_AGENT_|COPILOT_MAILBOX_|CLAUDE_)/i.test(name)) continue;
    env[name] = value;
  }
  return { ...env, ...extra };
}

test("hook CLI without Claude environment prints {} and exits 0 naming only variables", async () => {
  const result = await runHook(cleanEnvironment({}));
  assert.equal(result.code, 0);
  assert.equal(result.stdout.trim(), "{}");
  assert.match(result.stderr, /MAILBOX_SELF_ADDRESS/);
});

test("end to end: hook spawns a detached watcher that delivers, dedupes re-fire, and exits with Claude", async () => {
  await sandbox("e2e", async (root) => {
    const token = newToken();
    const pipe = await fakePipe({ token, label: "e2e" });
    const claude = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore" });
    let watcherPid;
    try {
      const configPath = join(root, "mailbox-config.json");
      await mkdir(root, { recursive: true });
      await writeFile(
        configPath,
        JSON.stringify({ schemaVersion: 1, machineName: "thinkpad", remoteMailboxRoot: join(root, "remote") }),
      );
      const env = cleanEnvironment({
        ...watcherEnv(pipe.path, token, claude.pid),
        MAILBOX_LOCAL_ROOT: join(root, "mailbox"),
        MAILBOX_STATE_ROOT: join(root, "state"),
        MAILBOX_CONFIG_PATH: configPath,
      });

      const first = await runHook(env);
      assert.equal(first.code, 0);
      assert.equal(first.stdout.trim(), "{}");
      assert.equal(first.stderr, "");
      assert.ok(first.elapsedMs < 4_000, `hook returned in ${first.elapsedMs}ms`);

      const owner = await waitForOwner(root, claudeSocketGeneration(pipe.path));
      watcherPid = owner.pid;
      assert.notEqual(watcherPid, process.pid);
      assert.equal(isProcessAlive(watcherPid), true);

      const refire = await runHook(env, '{"hook_event_name":"SessionStart","source":"compact"}');
      assert.equal(refire.code, 0);
      await sleep(1_500);
      assert.deepEqual(await readLockOwner(root), owner, "re-fire did not replace the owner");

      const sent = await sendProviderMail(root);
      await waitFor("watcher delivery", () => readIfExists(unverifiedFile(root, sent.envelope.id)), 10_000);
      assert.equal(pipe.connections.length, 1);
      assert.equal(pipe.raw(0).split("\n")[0], JSON.stringify({ type: "auth", token }));

      claude.kill();
      await waitFor("watcher exit after Claude death", () => !isProcessAlive(watcherPid), 10_000);
      await waitFor("lock removal", async () => (await readLockOwner(root)) === undefined, 3_000);

      for (const output of [first, refire]) {
        assert.ok(!output.stdout.includes(token) && !output.stderr.includes(token));
      }
      await assertTokenAbsentFromFiles(root, token);
    } finally {
      claude.kill();
      if (watcherPid && isProcessAlive(watcherPid)) {
        try {
          process.kill(watcherPid);
        } catch {}
      }
      await pipe.close();
    }
  });
});
