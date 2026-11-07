import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { candidatePermissionHandler, matchesFixtureState, runProbe, validateConfig } from "./native_workflow_probe.mjs";

// This SDK double exercises control flow only, never native interoperability.
const sdkDouble = `
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
export const state = {
  rows: [], entries: [], nextId: 1, owners: 0, starts: 0, stops: 0,
  mode: "interactive", connections: [], resumes: [], deleteFails: false,
  events: [], handlers: [], sendCalls: 0, aborts: 0,
};
const emit = (type, data, extra = {}) => {
  const event = { id: randomUUID(), type, data, timestamp: new Date().toISOString(), parentId: null, ...extra };
  for (const handler of state.handlers) handler(event);
  return event;
};
state.emit = emit;
export const RuntimeConnection = {
  forStdio(options) { state.connections.push(options); return options; },
};
export class CopilotClient {
  constructor(options) { this.options = options; }
  async start() {
    if (state.owners) throw new Error("Overlapping owners");
    state.owners++; state.starts++;
  }
  async getStatus() { return { version: "test-double", protocolVersion: 1, token: "excluded" }; }
  async stop() {
    if (state.stopFails) throw new Error("Test shutdown failure");
    state.owners--; state.stops++; return [];
  }
  async forceStop() { state.owners = 0; }
  async resumeSession(id, options) {
    state.resumes.push(options);
    const goalPath = join(this.options.baseDirectory, "session-state", id, "autopilot-objective.json");
    let current = null;
    try { current = JSON.parse(readFileSync(goalPath, "utf8")).current; } catch {}
    if (current && state.coldMismatch && state.starts > 1) current.id = 18;
    const session = {
      sessionId: id,
      on(handler) {
        state.handlers.push(handler);
        return () => { state.handlers = state.handlers.filter(item => item !== handler); };
      },
      async abort() { state.aborts++; },
      async send(message) {
        state.sendCalls++; state.sentPrompt = message.prompt;
        const id = randomUUID();
        state.sentId = id;
        state.sendReady?.();
        if (state.sendFails) throw new Error("Test send transport failure");
        if (state.sendHook) return state.sendHook(id, emit);
        emit("assistant.turn_start", { model: options.model });
        emit("assistant.usage", { apiCallId: "test-api-1", model: options.model });
        emit("assistant.usage", { apiCallId: "test-api-2", model: options.model });
        emit("assistant.message", { content: "Test SDK response", originatingMessageId: id });
        emit("assistant.idle", {});
        emit("session.idle", { mode: "autopilot" });
        return id;
      },
      rpc: {
        eventLog: {
          read: async ({ cursor }) => ({ events: structuredClone(state.events.slice(Number(cursor ?? 0))),
            cursor: String(state.events.length), hasMore: false, cursorStatus: "ok" }),
          tail: async () => ({ cursor: String(state.events.length) }),
        },
        instructions: {
          getSources: async () => {
            const path = join(this.options.baseDirectory, "copilot-instructions.md");
            return state.instructionOverride ?? { sources: [{ id: "personal", label: "Personal",
              sourcePath: path, content: readFileSync(path, "utf8"), type: "home", location: "user" }] };
          },
        },
        model: { getCurrent: async () => ({ modelId: options.model, reasoningEffort: options.reasoningEffort }) },
        autopilotObjective: { getState: async () => ({ state: current && {
          id: current.id, objective: current.objective, status: current.status,
          turnCount: current.turnCount, creditCountNanoAiu: current.creditCountNanoAiu,
        } }) },
        mode: {
          get: async () => state.mode,
          set: async ({ mode }) => { state.mode = mode; return { modeApplied: true }; },
        },
        workspaces: {
          writeAutopilotObjective: async ({ content }) => {
            writeFileSync(goalPath, content); return { operation: "create" };
          },
          readAutopilotObjective: async () => ({ content: readFileSync(goalPath, "utf8") }),
        },
        plan: { readSqlTodos: async () => ({ rows: structuredClone(state.rows) }) },
        schedule: {
          list: async () => ({ entries: structuredClone(state.entries) }),
          stop: async ({ id }) => {
            const entry = state.entries.find(entry => entry.id === id);
            state.entries = state.entries.filter(entry => entry.id !== id);
            return { entry };
          },
        },
        tools: {
          getCurrentMetadata: async () => state.metadataOverride ?? ({
            tools: ["skill", "view", "sql", "manage_schedule"].map(name => ({ name, description: "Native test double" })),
          }),
          initializeAndValidate: async () => ({}),
          execute: async ({ name, arguments: args, toolCallId }) => {
            if (name === "view") {
              if (state.preflightFails) throw new Error("Test native preflight RPC failure");
              const decision = state.ownerBypass ? { kind: "approve-once" } : options.onPermissionRequest({
                kind: "read", intention: "Test view",
                path: state.handlerError ? args.path + ".missing" : args.path, toolCallId,
              }, { sessionId: id });
              if (state.semanticPollution) state.events.push(emit("tool.execution_complete", { result: "Injected test result" }));
              const denied = args.path.endsWith("synthetic-denied-sibling.txt") || decision.kind === "reject";
              return { resultType: denied ? "denied" : "success", textResultForLlm: "Test native view" };
            }
            if (name === "sql" && args.query.startsWith("INSERT")) {
              state.rows.push({ id: "native-workflow-fixture", title: "Synthetic pending work",
                description: "Owned diagnostic fixture", status: "pending" });
            } else if (name === "sql" && args.query.startsWith("DELETE")) {
              if (state.deleteFails) return { resultType: "failure" };
              state.rows = state.rows.filter(row => row.id !== "native-workflow-fixture");
            } else if (name === "manage_schedule") {
              state.entries.push({ id: state.nextId++, intervalMs: 14400000,
                recurring: true, prompt: args.prompt, nextRunAt: new Date().toISOString() });
            }
            return { resultType: "success", textResultForLlm: "test double" };
          },
        },
      },
    };
    session.circular = session;
    return session;
  }
}
`;

function fixture(t) {
  const root = resolve(`.native-probe-test-${randomUUID()}`);
  const sessionId = randomUUID();
  const config = {
    cli: process.execPath, sdk: join(root, "sdk", "index.js"),
    home: join(root, "native-home"), os_home: join(root, "os-home"),
    cwd: join(root, "evidence"), session_id: sessionId, output: join(root, "setup.json"),
  };
  for (const dir of [
    join(config.home, "session-state", sessionId), config.os_home, config.cwd, join(root, "sdk"),
  ]) mkdirSync(dir, { recursive: true });
  writeFileSync(join(root, "sdk", "package.json"), '{"type":"module"}\n');
  writeFileSync(config.sdk, sdkDouble);
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return { root, config, goalPath: join(config.home, "session-state", sessionId, "autopilot-objective.json") };
}

test("rejects invalid coordinator fields and namespace paths before SDK start", async t => {
  const { config, root } = fixture(t);
  for (const invalid of [
    { ...config, query: "DELETE FROM todos" },
    { ...config, session_id: "../foreign" },
    { ...config, home: join(homedir(), ".copilot") },
    { ...config, os_home: homedir() },
    { ...config, cli: config.cwd },
  ]) {
    const packet = { ...invalid, output: join(root, `${randomUUID()}.json`) };
    const report = await runProbe("setup", packet);
    assert.equal(report.status, "ERROR");
    assert.equal(report.calls.length, 0);
    assert.equal(JSON.parse(readFileSync(packet.output)).status, "ERROR");
  }
  const link = join(root, "linked-home");
  symlinkSync(config.home, link);
  assert.throws(() => validateConfig("setup", { ...config, home: link }), /Symlink/);
  const goalPath = join(config.home, "session-state", config.session_id, "autopilot-objective.json");
  symlinkSync(join(root, "absent-foreign-goal"), goalPath);
  assert.throws(() => validateConfig("setup", config), /Symlink/);
  rmSync(goalPath);
  assert.throws(() => validateConfig("arbitrary", config), /Unknown operation/);
  assert.throws(() => validateConfig("observe", config), /ENOENT/);
});

test("preserves an existing output before importing or starting any SDK", async t => {
  const { config } = fixture(t);
  writeFileSync(config.output, "first outcome");
  const report = await runProbe("setup", config);
  assert.equal(report.error.code, "EEXIST");
  assert.equal(report.calls.length, 0);
  assert.equal(readFileSync(config.output, "utf8"), "first outcome");
});

test("accepts the coordinator's already isolated subprocess environment", t => {
  const { config, goalPath } = fixture(t);
  const previous = { HOME: process.env.HOME, COPILOT_HOME: process.env.COPILOT_HOME };
  try {
    process.env.HOME = config.os_home;
    process.env.COPILOT_HOME = config.home;
    assert.equal(validateConfig("setup", config), goalPath);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});

test("cold fixture check, observation and cleanup use sequential closed owners", async t => {
  const { root, config, goalPath } = fixture(t);
  const { state } = await import(pathToFileURL(config.sdk).href);
  const setup = await runProbe("setup", config);
  assert.equal(setup.status, "SETUP_OBSERVED", JSON.stringify(setup.error));
  assert.deepEqual(setup.schedule_ids, [1]);
  assert.equal(state.starts, 2);
  assert.equal(state.stops, 2);
  assert.equal(state.owners, 0);
  assert.equal(state.sendCalls, 0);
  assert.equal(JSON.parse(readFileSync(config.output)).status, "SETUP_OBSERVED");
  assert.equal(JSON.stringify(setup).includes("excluded"), false);
  for (const connection of state.connections) {
    assert.equal(connection.path, config.cli);
    assert.deepEqual(connection.args, []);
    assert.deepEqual(Object.keys(connection.env).sort(), [
      "COPILOT_DISABLE_KEYTAR", "COPILOT_HOME", "COPILOT_OTEL_ENABLED", "HOME", "PATH", "TMPDIR",
    ]);
  }
  for (const options of state.resumes) {
    assert.deepEqual(options, {
      continuePendingWork: false, suppressResumeEvent: true, allowTranscriptRecovery: false,
      availableTools: ["sql", "manage_schedule"], manageScheduleEnabled: true,
    });
  }
  const before = readFileSync(goalPath, "utf8");
  state.rows[0].status = "done";
  const observed = await runProbe("observe", { ...config, output: join(root, "observe.json") });
  assert.equal(observed.status, "OBSERVED");
  assert.equal(observed.todos.rows[0].status, "done");
  assert.equal(readFileSync(goalPath, "utf8"), before);
  state.entries.push({ id: 2, prompt: "Additional diagnostic entry" });
  const cleaned = await runProbe("cleanup", { ...config, output: join(root, "cleanup.json") });
  assert.equal(cleaned.status, "CLEANED");
  assert.deepEqual(cleaned.cleanup.todos.rows, []);
  assert.deepEqual(cleaned.cleanup.schedules.entries, []);
  assert.equal(readFileSync(goalPath, "utf8"), before);
  assert.equal(state.owners, 0);
});

test("failed first native ID retains its error and cleans partial resources", async t => {
  const { config, goalPath } = fixture(t);
  const { state } = await import(pathToFileURL(config.sdk).href);
  state.nextId = 7;
  state.deleteFails = true;
  const report = await runProbe("setup", config);
  assert.equal(report.status, "ERROR");
  assert.match(report.error.message, /first native schedule ID 1/);
  assert.deepEqual(report.schedule_ids, [7]);
  assert.deepEqual(report.cleanup.schedules.entries, []);
  assert.ok(report.cleanup.errors.length);
  assert.equal(state.owners, 0);
  assert.equal(JSON.parse(readFileSync(goalPath)).current.id, 17);
  assert.equal(JSON.parse(readFileSync(config.output)).error.message, report.error.message);
});

test("dirty fixtures are rejected without cleanup of preexisting resources", async t => {
  const { config } = fixture(t);
  const { state } = await import(pathToFileURL(config.sdk).href);
  state.rows.push({ id: "preexisting" });
  const report = await runProbe("setup", config);
  assert.match(report.error.message, /empty imported native fixture/);
  assert.equal(report.cleanup, undefined);
  assert.equal(state.rows[0].id, "preexisting");
  assert.equal(state.owners, 0);
  assert.equal(matchesFixtureState({ goal: { state: null } }, {}), false);
});

test("a mismatched cold checkpoint retains observed state and cleans the fixture", async t => {
  const { config } = fixture(t);
  const { state } = await import(pathToFileURL(config.sdk).href);
  state.coldMismatch = true;
  const report = await runProbe("setup", config);
  assert.match(report.error.message, /Cold native checkpoint mismatch/);
  assert.equal(report.goal.state.id, 18);
  assert.deepEqual(report.cleanup.todos.rows, []);
  assert.deepEqual(report.cleanup.schedules.entries, []);
  assert.equal(state.owners, 0);
});

test("shutdown failure forces owner termination and fails setup before handoff", async t => {
  const { config } = fixture(t);
  const { state } = await import(pathToFileURL(config.sdk).href);
  state.stopFails = true;
  const report = await runProbe("setup", config);
  assert.equal(report.status, "ERROR");
  assert.equal(report.error.message, "Test shutdown failure");
  assert.ok(report.shutdown_errors.length);
  assert.ok(report.calls.some(call => call.name === "client.forceStop"));
  assert.deepEqual(report.cleanup.schedules.entries, []);
  assert.deepEqual(report.cleanup.todos.rows, []);
  assert.equal(state.owners, 0);
});

async function candidateFixture(t) {
  const owned = fixture(t);
  const { root, config } = owned;
  const { state } = await import(pathToFileURL(config.sdk).href);
  assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
  mkdirSync(join(root, "pinned-plugin"));
  writeFileSync(join(root, "candidate-prompt.md"), "Unchanged rendered diagnostic prompt.\n");
  writeFileSync(join(root, "synthetic-denied-sibling.txt"), "Synthetic denied sibling.\n");
  writeFileSync(join(config.cwd, "plan.md"), "Synthetic ordinary plan.\n");
  writeFileSync(join(config.home, "copilot-instructions.md"), "Synthetic personal instructions.\n");
  state.events.push({ id: "test-prior-id", type: "user.message", data: { content: "Prior-only test marker" } });
  return { ...owned, state, config: { ...config, output: join(root, "candidate.json") } };
}

test("candidate permission handler approves only canonical owned reads and three native names", t => {
  const { config, root, goalPath } = fixture(t);
  const plan = join(config.cwd, "plan.md");
  const plugin = join(root, "pinned-plugin");
  mkdirSync(plugin);
  writeFileSync(plan, "Test plan");
  writeFileSync(goalPath, "{}");
  writeFileSync(join(root, "sibling.txt"), "Test sibling");
  const alias = join(config.cwd, "alias.md");
  symlinkSync(plan, alias);
  const receipts = [];
  const handler = candidatePermissionHandler(config, goalPath, plugin, receipts);
  const invocation = { sessionId: config.session_id };
  const read = { kind: "read", intention: "Test read", toolCallId: "test-read", path: plan };
  for (const path of [plan, "plan.md", goalPath, config.cwd]) {
    assert.equal(handler({ ...read, path }, invocation).kind, "approve-once");
  }
  for (const request of [
    { ...read, path: join(root, "sibling.txt") }, { ...read, path: plugin },
    { ...read, path: alias }, { ...read, path: "alias.md" },
    { ...read, path: `${config.cwd}/../${config.cwd.split("/").at(-1)}/plan.md` },
    { ...read, resolvedPath: goalPath }, { ...read, managedApprovalRequired: true },
    { ...read, requestSandboxBypass: true }, { ...read, kind: "write" },
    { ...read, arbitraryGrant: true }, { ...read, managedApprovalRequired: 0 },
    { kind: "custom-tool", toolCallId: "test", toolDescription: "Native view", toolName: "view" },
    { kind: "custom-tool", toolCallId: "test", toolDescription: "Native SQL", toolName: "sql", skipPermission: true },
  ]) assert.equal(handler(request, invocation).kind, "reject");
  assert.equal(handler(read, { sessionId: randomUUID() }).kind, "reject");
  for (const toolName of ["skill", "sql", "manage_schedule"]) {
    assert.equal(handler({ kind: "custom-tool", toolDescription: "Native test tool", toolName, toolCallId: "native-test" }, invocation).kind, "approve-once");
  }
  const broken = { kind: "read", intention: "Test error", toolCallId: "broken", get path() { throw new Error("Test handler error"); } };
  assert.equal(handler(broken, invocation).kind, "reject");
  assert.equal(receipts.at(-1).error.message, "Test handler error");
});

test("candidate gates one SDK send and retains unwrapped native events and separate timing", async t => {
  const { config, root, state } = await candidateFixture(t);
  const report = await runProbe("candidate", config);
  assert.equal(report.status, "CANDIDATE_OBSERVED", JSON.stringify(report.error));
  assert.equal(report.firsterror, null);
  assert.equal(report.model_send_calls, 1);
  assert.equal(state.sendCalls, 1);
  assert.equal(report.model_message_id, state.sentId);
  assert.equal(state.sentPrompt, readFileSync(join(root, "candidate-prompt.md"), "utf8"));
  assert.ok(Object.values(report.checks).every(value => value === true));
  assert.equal(report.model_calls, undefined);
  assert.equal(report.observed_model_calls, null);
  assert.equal(report.observed_usage_events, 2);
  assert.deepEqual(report.observed_api_call_ids, ["test-api-1", "test-api-2"]);
  assert.ok(Number.isFinite(Date.parse(report.model_started_at)));
  assert.ok(Number.isFinite(Date.parse(report.model_completed_at)));
  assert.ok(report.model_elapsed_seconds >= 0);
  const events = readFileSync(join(root, "candidate-raw.jsonl"), "utf8").trim().split("\n").map(JSON.parse);
  assert.deepEqual(events.map(event => event.type), [
    "assistant.turn_start", "assistant.usage", "assistant.usage", "assistant.message", "assistant.idle", "session.idle",
  ]);
  assert.equal(events[0].data.model, "gpt-5.6-sol-fast");
  assert.deepEqual(events.find(event => event.type === "assistant.message"), report.model_result);
  assert.deepEqual(events.at(-1), report.model_completion_event);
  assert.equal(report.model_result.data.originatingMessageId, report.model_message_id);
  assert.equal(state.owners, 0);
  assert.deepEqual(state.resumes.at(-1).availableTools, ["skill", "view", "sql", "manage_schedule"]);
  assert.equal(state.resumes.at(-1).skipCustomInstructions, false);
  assert.deepEqual(state.resumes.at(-1).instructionDirectories, []);
  assert.equal(state.resumes.at(-1).organizationCustomInstructions, "");
});

test("missing or mismatched native sources, tools, mediation and history block before any send", async t => {
  for (const failure of [
    "missing-instructions", "wrong-content", "duplicate-instructions", "disabled-instructions",
    "missing-tools", "wrong-tools", "mcp-tools", "owner-bypass", "semantic-pollution", "cold-mismatch", "handler-error", "preflight-error",
  ]) await t.test(failure, async child => {
    const { config, state } = await candidateFixture(child);
    const source = {
      id: "personal", label: "Personal", sourcePath: join(config.home, "copilot-instructions.md"),
      content: readFileSync(join(config.home, "copilot-instructions.md"), "utf8"), type: "home", location: "user",
    };
    if (failure === "missing-instructions") state.instructionOverride = { sources: [] };
    if (failure === "wrong-content") state.instructionOverride = { sources: [{ ...source, content: "Mismatched" }] };
    if (failure === "duplicate-instructions") state.instructionOverride = { sources: [source, source] };
    if (failure === "disabled-instructions") state.instructionOverride = { sources: [{ ...source, defaultDisabled: true }] };
    if (failure === "missing-tools") state.metadataOverride = { tools: null };
    if (failure === "wrong-tools") state.metadataOverride = { tools: [{ name: "bash", description: "Wrong tool" }] };
    if (failure === "mcp-tools") state.metadataOverride = {
      tools: ["skill", "view", "sql", "manage_schedule"].map(name => ({ name, description: "Wrong server", mcpServerName: "foreign" })),
    };
    if (failure === "owner-bypass") state.ownerBypass = true;
    if (failure === "semantic-pollution") state.semanticPollution = true;
    if (failure === "cold-mismatch") state.coldMismatch = true;
    if (failure === "handler-error") state.handlerError = true;
    if (failure === "preflight-error") state.preflightFails = true;
    const report = await runProbe("candidate", config);
    assert.equal(report.status, "PREMODEL_BLOCKED", JSON.stringify(report));
    assert.equal(report.model_send_calls, 0);
    assert.equal(state.sendCalls, 0);
    assert.equal(report.model_started_at, undefined);
    assert.equal(typeof report.firsterror, "string");
    assert.equal(JSON.parse(readFileSync(config.output)).firsterror, report.firsterror);
    assert.equal(state.owners, 0);
    if (failure === "handler-error") {
      assert.ok(report.permissions.some(entry => entry.error));
      assert.equal(report.error.code, "ENOENT");
    }
    if (failure === "preflight-error") {
      assert.equal(report.firsterror, "Test native preflight RPC failure");
      assert.deepEqual(report.prefix_before, report.prefix_after);
    }
  });
});

test("candidate send failure aborts and closes while retaining the first model error", async t => {
  const { config, state } = await candidateFixture(t);
  state.sendFails = true;
  const report = await runProbe("candidate", config);
  assert.equal(report.status, "FAILED");
  assert.equal(report.firsterror, "Test send transport failure");
  assert.equal(report.model_send_calls, 1);
  assert.equal(state.aborts, 1);
  assert.equal(state.owners, 0);
  assert.ok(report.model_elapsed_seconds >= 0);
});

test("late correlated root response completes on autopilot session idle while child events remain retained", async t => {
  const { config, root, state } = await candidateFixture(t);
  const ready = new Promise(resolve => { state.sendReady = resolve; });
  state.sendHook = id => id;
  const pending = runProbe("candidate", config);
  await ready;
  await new Promise(setImmediate);
  state.emit("assistant.message", { content: "Child response", originatingMessageId: state.sentId }, { agentId: "test-child" });
  state.emit("session.idle", { mode: "autopilot" }, { agentId: "test-child" });
  state.emit("session.error", { message: "Child-only error" }, { agentId: "test-child" });
  const matching = state.emit("assistant.message", { content: "Root response", originatingMessageId: state.sentId });
  const terminal = state.emit("session.idle", { mode: "autopilot", aborted: false });
  const report = await pending;
  assert.equal(report.status, "CANDIDATE_OBSERVED", report.firsterror);
  assert.deepEqual(report.model_result, matching);
  assert.deepEqual(report.model_completion_event, terminal);
  assert.equal(report.model_message_id, state.sentId);
  const events = readFileSync(join(root, "candidate-raw.jsonl"), "utf8").trim().split("\n").map(JSON.parse);
  assert.equal(events.filter(event => event.agentId === "test-child").length, 3);
  assert.equal(state.owners, 0);
  assert.equal(state.handlers.length, 0);
});

test("wrong, missing, child or tool-only responses and aborted/error idle cannot complete", async t => {
  for (const failure of ["wrong-id", "missing-id", "missing-send-id", "child-only", "tool-only", "latest-wrong-id", "idle-first", "aborted-idle", "root-error"]) {
    await t.test(failure, async child => {
      const { config, state } = await candidateFixture(child);
      state.sendHook = (id, emit) => {
        if (failure === "idle-first") emit("session.idle", { mode: "autopilot" });
        emit("assistant.message", {
          content: "Test response",
          ...(failure === "missing-id" ? {} : { originatingMessageId: failure === "wrong-id" ? "other-id" : id }),
          ...(failure === "tool-only" ? { toolRequests: [{ toolCallId: "test-tool", name: "sql", arguments: {} }] } : {}),
        }, failure === "child-only" ? { agentId: "test-child" } : {});
        if (failure === "latest-wrong-id") emit("assistant.message", { content: "Unrelated last response", originatingMessageId: "other-id" });
        if (failure === "root-error") emit("session.error", { message: "First native root error" });
        emit("session.idle", { mode: "autopilot", aborted: failure === "aborted-idle" });
        return failure === "missing-send-id" ? undefined : id;
      };
      const report = await runProbe("candidate", config);
      assert.equal(report.status, "FAILED");
      assert.equal(report.model_send_calls, 1);
      assert.equal(report.model_completion_event, undefined);
      assert.equal(state.aborts, 1);
      assert.equal(state.owners, 0);
      assert.equal(state.handlers.length, 0);
      if (failure === "root-error") assert.equal(report.firsterror, "First native root error");
      if (failure === "aborted-idle") assert.equal(report.firsterror, "Native session idle was aborted");
      if (failure === "missing-send-id") assert.equal(report.firsterror, "SDK send returned no message ID");
    });
  }
});

test("assistant idle alone or a stalled admission expires at the fixed deadline and closes", async t => {
  for (const stalled of [false, true]) await t.test(stalled ? "stalled admission" : "assistant idle only", async child => {
    const { config, state } = await candidateFixture(child);
    child.mock.timers.enable({ apis: ["setTimeout"] });
    const ready = new Promise(resolve => { state.sendReady = resolve; });
    state.sendHook = (id, emit) => {
      if (stalled) return new Promise(() => {});
      emit("assistant.message", { content: "Test response", originatingMessageId: id });
      emit("assistant.idle", {});
      return id;
    };
    const pending = runProbe("candidate", config);
    await ready;
    await new Promise(setImmediate);
    child.mock.timers.tick(299999);
    await new Promise(setImmediate);
    assert.equal(state.aborts, 0);
    child.mock.timers.tick(1);
    const report = await pending;
    assert.equal(report.status, "FAILED");
    assert.equal(report.firsterror, "300-second SDK send/completion deadline exceeded");
    assert.equal(report.model_send_calls, 1);
    assert.equal(report.model_completion_event, undefined);
    assert.equal(state.aborts, 1);
    assert.equal(state.owners, 0);
    assert.equal(state.handlers.length, 0);
  });
});
