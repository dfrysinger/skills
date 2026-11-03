import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";
import test from "node:test";
import { inspect } from "node:util";

import {
  CODEX_ENV,
  CodexEnvironmentError,
  CodexTransportError,
  codexGeneration,
  createCodexWakeupAdapter,
  readCodexEnvironment,
} from "./codex-mailbox-adapter.mjs";
import { runCodexWatcher } from "./codex-mailbox-watcher.mjs";

const token = () => `synthetic-${randomBytes(18).toString("hex")}`;
const workspace = resolve("codex-adapter-workspace");
const wake = {
  address: "codex:alpha",
  provider: "codex",
  name: "alpha",
  envelopeId: "20261103T120000Z-codex",
  attemptId: "attempt-codex",
  prompt: "check mailbox; skip if empty [mb:codex0001]",
};

const ok = (result) => ({ result });
const loaded = (ids, nextCursor = null) => ok({ data: ids, nextCursor });
const thread = (status, cwd = workspace) => ok({ thread: { cwd, status } });
const turns = (data) => ok({ data, nextCursor: null });
const started = () => ok({ turn: { id: "turn-1" } });
const steered = (turnId) => ok({ turnId });
const wrongTurn = () => ({ error: { code: -32600, message: "invalid request" } });

function fakeTransport(steps) {
  const calls = [];
  let closed = false;
  return {
    calls,
    get closed() {
      return closed;
    },
    connect: async () => ({
      async request(method, params) {
        calls.push({ method, params });
        if (method === "initialize" && steps[0]?.method !== "initialize") {
          return ok({ platformOs: "windows" });
        }
        const step = steps.shift();
        assert.ok(step, `unexpected ${method}`);
        assert.equal(method, step.method);
        if (step.throw) throw step.throw;
        return step.response;
      },
      close() {
        closed = true;
      },
    }),
  };
}

function adapter(transport, extra = {}) {
  return createCodexWakeupAdapter({
    address: "codex:alpha",
    endpoint: "ws://127.0.0.1:8123",
    token: token(),
    workspace,
    launcherPid: process.pid,
    transport,
    isAlive: () => true,
    ...extra,
  });
}

test("environment validation and generation never echo the token", () => {
  const capability = token();
  const env = {
    MAILBOX_SELF_ADDRESS: "codex:alpha",
    CODEX_APP_SERVER_ENDPOINT: "ws://127.0.0.1:8123",
    CODEX_APP_SERVER_TOKEN: capability,
    CODEX_WORKSPACE: workspace,
    CODEX_LAUNCHER_PID: "4242",
    CODEX_ALLOW_ALL: "true",
  };
  const config = readCodexEnvironment(env);
  assert.equal(config.address, "codex:alpha");
  assert.equal(config.launcherPid, 4242);
  assert.equal(config.allowAll, true);
  assert.match(codexGeneration(config), /^[0-9a-f]{64}$/);
  for (const invalid of [
    { ...env, MAILBOX_SELF_ADDRESS: "alpha" },
    { ...env, CODEX_APP_SERVER_ENDPOINT: "ws://example.test:8123" },
    { ...env, CODEX_WORKSPACE: "relative" },
    { ...env, CODEX_LAUNCHER_PID: "0" },
    { ...env, CODEX_ALLOW_ALL: "sometimes" },
    { ...env, CODEX_APP_SERVER_TOKEN: undefined },
  ]) {
    assert.throws(
      () => readCodexEnvironment(invalid),
      (error) => error instanceof CodexEnvironmentError && !error.message.includes(capability),
    );
  }
});

test("merged turn/start success is submitted, never verified", async () => {
  const transport = fakeTransport([
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "idle" }) },
    { method: "turn/start", response: started() },
  ]);
  const outcome = await adapter(transport).wake(wake);
  assert.deepEqual(outcome, {
    outcome: "submitted",
    detail: "codex turn/start accepted; a concurrent start may merge into the same active turn",
  });
  assert.equal(transport.calls[0].method, "initialize");
  assert.equal(transport.calls[3].params.threadId, "thread-1");
  assert.equal(transport.calls[3].params.input[0].text, wake.prompt);
  assert.equal(transport.closed, true);
});

test("allow-all policy is applied by the authority that starts an idle turn", async () => {
  const transport = fakeTransport([
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "idle" }) },
    { method: "turn/start", response: started() },
  ]);
  const outcome = await adapter(transport, { allowAll: true }).wake(wake);
  assert.equal(outcome.outcome, "submitted");
  assert.equal(transport.calls[3].params.approvalPolicy, "never");
  assert.deepEqual(transport.calls[3].params.sandboxPolicy, {
    type: "dangerFullAccess",
  });
});

test("exact thread selection refuses zero, multiple, paginated, and cwd-mismatched threads", async () => {
  const cases = [
    [{ method: "thread/loaded/list", response: loaded([]) }],
    [{ method: "thread/loaded/list", response: loaded(["one", "two"]) }],
    [{ method: "thread/loaded/list", response: loaded(["one"], "more") }],
    [
      { method: "thread/loaded/list", response: loaded(["one"]) },
      { method: "thread/read", response: thread({ type: "idle" }, resolve("other-workspace")) },
    ],
    [
      { method: "thread/loaded/list", response: loaded(["one"]) },
      { method: "thread/read", response: ok({ thread: { status: { type: "idle" } } }) },
    ],
  ];
  for (const steps of cases) {
    const transport = fakeTransport(steps);
    const outcome = await adapter(transport).wake(wake);
    assert.equal(outcome.outcome, "deferred");
    assert.equal(transport.calls.some((call) => call.method.startsWith("turn/")), false);
  }
});

test("active exact turn steers only the one in-progress turn", async () => {
  const transport = fakeTransport([
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "active", activeFlags: [] }) },
    { method: "thread/turns/list", response: turns([{ id: "turn-1", status: "inProgress" }]) },
    { method: "turn/steer", response: steered("turn-1") },
  ]);
  const outcome = await adapter(transport).wake(wake);
  assert.equal(outcome.outcome, "submitted");
  assert.equal(transport.calls.at(-1).params.expectedTurnId, "turn-1");
});

test("wrong-turn -32600 re-reads once and steers the exact replacement turn", async () => {
  const transport = fakeTransport([
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "active", activeFlags: [] }) },
    { method: "thread/turns/list", response: turns([{ id: "old-turn", status: "inProgress" }]) },
    { method: "turn/steer", response: wrongTurn() },
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "active", activeFlags: [] }) },
    { method: "thread/turns/list", response: turns([{ id: "new-turn", status: "inProgress" }]) },
    { method: "turn/steer", response: steered("new-turn") },
  ]);
  const outcome = await adapter(transport).wake(wake);
  assert.equal(outcome.outcome, "submitted");
  assert.equal(transport.calls.at(-1).params.expectedTurnId, "new-turn");
});

test("wrong-turn -32600 re-reads once and starts only when the exact thread is idle", async () => {
  const transport = fakeTransport([
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "active", activeFlags: [] }) },
    { method: "thread/turns/list", response: turns([{ id: "old-turn", status: "inProgress" }]) },
    { method: "turn/steer", response: wrongTurn() },
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "idle" }) },
    { method: "turn/start", response: started() },
  ]);
  const outcome = await adapter(transport).wake(wake);
  assert.equal(outcome.outcome, "submitted");
  assert.equal(transport.calls.at(-1).method, "turn/start");
  assert.equal(transport.calls.at(-1).params.threadId, "thread-1");
});

test("endpoint failure is deferred while post-request transport loss is ambiguous", async () => {
  const unavailable = {
    async connect() {
      throw new CodexTransportError("connect", "ECONNREFUSED");
    },
  };
  const deferred = await adapter(unavailable).wake(wake);
  assert.equal(deferred.outcome, "deferred");
  assert.match(deferred.detail, /ECONNREFUSED/);

  const transport = fakeTransport([
    { method: "thread/loaded/list", response: loaded(["thread-1"]) },
    { method: "thread/read", response: thread({ type: "idle" }) },
    { method: "turn/start", throw: new CodexTransportError("request", "ECONNRESET") },
  ]);
  const ambiguous = await adapter(transport).wake(wake);
  assert.equal(ambiguous.outcome, "ambiguous");
  assert.match(ambiguous.detail, /ECONNRESET/);
});

test("adapter binding, token hygiene, and dead launcher gates avoid transport use", async () => {
  const capability = token();
  const transport = fakeTransport([]);
  const instance = createCodexWakeupAdapter({
    address: "codex:alpha",
    endpoint: "ws://127.0.0.1:8123",
    token: capability,
    workspace,
    launcherPid: 999_999,
    transport,
    isAlive: () => false,
  });
  const dead = await instance.wake(wake);
  assert.equal(dead.outcome, "deferred");
  assert.equal(dead.releaseWatcher, true);
  const other = await adapter(transport).wake({ ...wake, address: "codex:beta", name: "beta" });
  assert.equal(other.outcome, "deferred");
  assert.equal(transport.calls.length, 0);
  assert.ok(!inspect(instance, { showHidden: true, depth: 5 }).includes(capability));
  assert.ok(!JSON.stringify(instance).includes(capability));
  assert.ok(!JSON.stringify(dead).includes(capability));
});

test("watcher aborts when the launcher exits without storing token state", async () => {
  const capability = token();
  let alive = true;
  const watchedAddresses = [];
  const mailbox = {
    watchAddresses(address) {
      return [address, `${address}@surface-pro`];
    },
    async watch(address, { signal }) {
      watchedAddresses.push(address);
      await new Promise((resolve) => signal.addEventListener("abort", resolve, { once: true }));
    },
  };
  const timer = setTimeout(() => {
    alive = false;
  }, 20);
  try {
    const outcome = await runCodexWatcher({
      env: {
        [CODEX_ENV.selfAddress]: "codex:alpha",
        [CODEX_ENV.endpoint]: "ws://127.0.0.1:8123",
        [CODEX_ENV.token]: capability,
        [CODEX_ENV.workspace]: workspace,
        [CODEX_ENV.launcherPid]: String(process.pid),
      },
      createMailbox: () => mailbox,
      isAlive: () => alive,
      livenessMs: 5,
    });
    assert.equal(outcome.started, true);
    assert.deepEqual(watchedAddresses.sort(), [
      "codex:alpha",
      "codex:alpha@surface-pro",
    ]);
    assert.ok(!JSON.stringify(outcome).includes(capability));
  } finally {
    clearTimeout(timer);
  }
});

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
    runCodexWatcher({
      env: {
        [CODEX_ENV.selfAddress]: "codex:alpha",
        [CODEX_ENV.endpoint]: "ws://127.0.0.1:8123",
        [CODEX_ENV.token]: token(),
        [CODEX_ENV.workspace]: workspace,
        [CODEX_ENV.launcherPid]: String(process.pid),
      },
      createMailbox: () => mailbox,
      isAlive: () => true,
    }),
    /synthetic route failure/,
  );
  assert.equal(siblingAborted, true);
});
