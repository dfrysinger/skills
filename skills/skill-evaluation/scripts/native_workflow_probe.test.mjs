import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { chmodSync, linkSync, lstatSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { candidatePermissionHandler, editableFixtureCheck, matchesFixtureState, matchesProfileState,
  runProbe, validateConfig, validateProfile } from "./native_workflow_probe.mjs";

// This SDK double exercises control flow only, never native interoperability.
const sdkDouble = `
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
export const state = {
  rows: [], dependencies: [], entries: [], nextId: 1, owners: 0, starts: 0, stops: 0,
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
  constructor(options) {
    this.options = options;
    this.started = false;
    state.explicitAuthMatched = options.gitHubToken === state.expectedGitHubToken;
    state.loggedInUserEnabled = options.useLoggedInUser;
  }
  async start() {
    if (state.owners) throw new Error("Overlapping owners");
    state.owners++; state.starts++; this.started = true;
    state.startHook?.();
  }
  async getStatus() { return { version: "test-double", protocolVersion: 1, token: "excluded" }; }
  async stop() {
    if (state.stopStalls) {
      state.stalledStops = (state.stalledStops ?? 0) + 1;
      return new Promise(() => {});
    }
    if (state.stopFails) throw new Error("Test shutdown failure");
    if (this.started) state.owners--;
    this.started = false; state.stops++; return [];
  }
  async forceStop() { state.owners = 0; this.started = false; }
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
      async abort() {
        state.aborts++;
        if (state.abortStalls) return new Promise(() => {});
      },
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
          read: async ({ cursor }) => {
            state.eventReads = (state.eventReads ?? 0) + 1;
            if (state.readStalls) return new Promise(() => {});
            return { events: structuredClone(state.events.slice(Number(cursor ?? 0))),
              cursor: String(state.events.length), hasMore: false, cursorStatus: "ok" };
          },
          tail: async () => ({ cursor: String(state.events.length) }),
        },
        instructions: {
          getSources: async () => {
            const path = join(this.options.baseDirectory, "copilot-instructions.md");
            return state.instructionOverride ?? { sources: [{ id: "personal", label: "Personal",
              sourcePath: path, content: readFileSync(path, "utf8"), type: "home", location: "user" }] };
          },
        },
        model: { getCurrent: async () => state.modelOverride ?? ({ modelId: options.model, reasoningEffort: options.reasoningEffort }) },
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
            tools: options.availableTools.map(name => ({ name, description: "Native test double" })),
          }),
          initializeAndValidate: async () => ({}),
          execute: async ({ name, arguments: args, toolCallId }) => {
            const hooked = await state.toolExecuteHook?.({
              name, args, toolCallId, permission: options.onPermissionRequest, sessionId: id,
            });
            if (hooked !== undefined) return hooked;
            if (name === "view") {
              if (state.preflightFails) throw new Error("Test native preflight RPC failure");
              const decision = state.ownerBypass ? { kind: "approve-once" } : options.onPermissionRequest({
                kind: "read", intention: "Test view",
                path: state.handlerError ? args.path + ".missing" : args.path, toolCallId,
              }, { sessionId: id });
              if (state.semanticPollution) state.events.push(emit("tool.execution_complete", { result: "Injected test result" }));
              const denied = args.path.endsWith("synthetic-denied-sibling.txt") || decision.kind === "reject";
              return { resultType: denied ? (state.denialResultType ?? "rejected") : "success", textResultForLlm: "Test native view" };
            }
            if (name === "sql" && args.query.startsWith("INSERT")) {
              const values = [...args.query.matchAll(/'((?:''|[^'])*)'/g)].map(match => match[1].replaceAll("''", "'"));
              if (args.query.startsWith("INSERT INTO todo_deps")) {
                state.dependencies.push({ todo_id: values[0], depends_on: values[1] });
              } else {
                state.rows.push(Object.fromEntries(["id", "title", "description", "status"].map((key, i) => [key, values[i]])));
              }
            } else if (name === "sql" && args.query.startsWith("DELETE")) {
              if (state.deleteFails) return { resultType: "failure" };
              if (args.query === "DELETE FROM todo_deps") state.dependencies = [];
              else if (args.query === "DELETE FROM todos") state.rows = [];
              else state.rows = state.rows.filter(row => row.id !== "native-workflow-fixture");
            } else if (name === "sql" && args.query.startsWith("WITH expected")) {
              const values = [...args.query.split("), missing")[0].matchAll(/'((?:''|[^'])*)'/g)]
                .map(match => match[1].replaceAll("''", "'"));
              const expected = [];
              for (let i = 0; i < values.length; i += 2) expected.push({ todo_id: values[i], depends_on: values[i + 1] });
              const matches = JSON.stringify(expected) === JSON.stringify(state.dependencies) && !state.dependencyMismatch;
              return { resultType: "success", toolTelemetry: { metrics: { rowsReturned: matches ? 0 : 1 } } };
            } else if (name === "sql" && args.query === "SELECT todo_id,depends_on FROM todo_deps") {
              return { resultType: "success", toolTelemetry: { metrics: { rowsReturned: state.dependencies.length } } };
            } else if (name === "manage_schedule") {
              const ms = Number(args.interval.slice(0, -1)) * {s:1000,m:60000,h:3600000,d:86400000}[args.interval.at(-1)];
              state.entries.push({ id: state.nextId++, intervalMs: ms,
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

test("expired setup retains its first error and reserves time to clear owned resources", async t => {
  const { config, state } = await profileFixture(t);
  let clock = 0;
  t.mock.method(performance, "now", () => clock);
  state.startHook = () => { if (state.starts === 2) clock = 330001; };
  const report = await runProbe("setup", config);
  assert.equal(report.status, "ERROR");
  assert.match(report.error.message, /owner deadline exceeded/);
  assert.deepEqual(report.cleanup.todos.rows, []);
  assert.deepEqual(report.cleanup.schedules.entries, []);
  assert.equal(report.cleanup_error, undefined);
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

function nativeProfile() {
  return {
    schema_version: 1, profile: "p01-scheduled-audit", provenance: "synthetic-calibration",
    goal: { id: 8, objective: "Synthetic audit objective", status: "active" },
    mode: "autopilot", model: "fixture-model", effort: "medium",
    todos: [
      { id: "a'quoted", title: "Audit current state", description: "", status: "pending" },
      { id: "b", title: "Preserve unfinished work", description: "", status: "blocked" },
    ],
    dependencies: [{ todo_id: "b", depends_on: "a'quoted" }],
    schedules: [
      { id: 41, interval: "2h", prompt: "Stopped synthetic wake", status: "stopped" },
      { id: 90, interval: "3h", prompt: "Active synthetic wake", status: "active" },
    ],
    unknowns: ["Descriptions and original deadlines are unknown; empty descriptions are execution defaults"],
  };
}

async function profileFixture(t) {
  const owned = fixture(t);
  const { config, root } = owned;
  for (const home of [config.home, config.os_home]) chmodSync(home, 0o700);
  mkdirSync(join(root, "profile-plugin"));
  writeFileSync(join(root, "source-prompt.md"), "Original words {NATIVE_GOAL_PATH}\r\n");
  writeFileSync(join(root, "denied.txt"), "Owned sibling");
  writeFileSync(join(config.cwd, "charter.md"), "Synthetic source charter");
  writeFileSync(join(config.home, "copilot-instructions.md"), "Synthetic personal instructions");
  const profile = nativeProfile();
  const stateFile = join(root, "source-state.json");
  writeFileSync(stateFile, JSON.stringify(profile), { mode: 0o600 });
  const selected = {
    ...config, profile: "p01-scheduled-audit", state_file: stateFile,
    prompt_path: join(root, "source-prompt.md"), event_log: join(root, "source-raw.jsonl"),
    plugin_path: join(root, "profile-plugin"), evidence_paths: [join(config.cwd, "charter.md")],
    denied_path: join(root, "denied.txt"), model: profile.model, effort: profile.effort,
  };
  const { state } = await import(pathToFileURL(config.sdk).href);
  const prior = { id: "source-history", type: "user.message", data: { content: "Remembered old skill" } };
  state.events.push(prior);
  selected.prefix_file = join(root, "imported-prefix.json");
  writeFileSync(selected.prefix_file, JSON.stringify([prior]), { mode: 0o600 });
  return { ...owned, config: selected, profile, state };
}

async function editableProfileFixture(t) {
  const owned = await profileFixture(t);
  const { config, state } = owned;
  config.candidate_permissions = { write_paths: ["target.txt"], shell_commands: ["python3 -I check.py"] };
  writeFileSync(join(config.cwd, "target.txt"), "pending\n");
  writeFileSync(join(config.cwd, "check.py"), editableFixtureCheck);
  state.toolExecuteHook = ({ name, args, toolCallId, permission, sessionId }) => {
    if (!["apply_patch", "bash"].includes(name)) return undefined;
    const patch = typeof args === "string" ? args : args.patch ?? args.input;
    const fileName = name === "apply_patch" ? patch.match(/\*\*\* Update File: ([^\n]+)/)[1] : undefined;
    const request = name === "apply_patch"
      ? { kind: "write", fileName, diff: patch, intention: "Owned test patch", canOfferSessionApproval: false, toolCallId }
      : { kind: "shell", fullCommandText: args.command, intention: "Owned test check", canOfferSessionApproval: false,
        commands: [{ identifier: "python3", readOnly: false }], hasWriteFileRedirection: false,
        possiblePaths: args.command === "python3 -I check.py" ? ["check.py"] : [], possibleUrls: [], toolCallId };
    if (!state.uncorrelatedPermission && permission(request, { sessionId }).kind === "reject") {
      return { resultType: "rejected", textResultForLlm: "Owned test refusal" };
    }
    if (name === "apply_patch") {
      if (!state.missingPatchEffect) {
        writeFileSync(fileName, patch.split("\n").filter(line => line.startsWith("+")).map(line => line.slice(1)).join("\n") + "\n");
      }
      if (state.editableStateMutation) state.rows[0].status = "done";
      if (state.editablePrefixMutation) state.events.push({
        id: randomUUID(), type: "assistant.message", data: { content: "Unexpected owner message" },
      });
      return { resultType: "success", textResultForLlm: "Owned test patch" };
    }
    const result = spawnSync("python3", ["-I", "check.py"], {
      cwd: config.cwd, encoding: "utf8", env: { PATH: process.env.PATH },
    });
    return { resultType: result.status === 0 ? "success" : "failure",
      textResultForLlm: result.stdout,
      structuredContent: { stdout: result.stdout, stderr: result.stderr,
        exitCode: state.unrelatedCheckFailure && result.status === 1 ? 137 : result.status } };
  };
  return owned;
}

test("profile cold hydration preserves goal/rows/dependencies and explicitly maps schedule lifecycle", async t => {
  const { config, profile, state, root } = await profileFixture(t);
  const setup = await runProbe("setup", config);
  assert.equal(setup.status, "SETUP_OBSERVED", setup.error?.message);
  assert.deepEqual(state.rows, profile.todos);
  assert.deepEqual(state.dependencies, profile.dependencies);
  assert.deepEqual(setup.schedule_mapping, [{ source_id: 41, native_id: 1 }, { source_id: 90, native_id: 2 }]);
  assert.ok(matchesProfileState(setup, profile, setup.schedule_mapping));
  assert.equal(setup.goal_file.current.id, 8);
  assert.equal(setup.goal_file.nextId, 9);
  const wrong = structuredClone(setup);
  wrong.schedules.entries[0].prompt = "different";
  assert.equal(matchesProfileState(wrong, profile, setup.schedule_mapping), false);
  const cleanup = await runProbe("cleanup", { ...config, output: join(root, "cleanup.json") });
  assert.equal(cleanup.status, "CLEANED", cleanup.error?.message);
  assert.deepEqual(state.rows, []);
  assert.deepEqual(state.dependencies, []);
  assert.deepEqual(state.entries, []);
  assert.equal(cleanup.cleanup.dependencies_empty, true);
  assert.equal(state.owners, 0);
});

test("trusted profile preflight checks authentic coordinates/model without sending or altering rows/timer", async t => {
  const { config, profile, state, root } = await profileFixture(t);
  assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
  const report = await runProbe("preflight", { ...config, output: join(root, "preflight.json") });
  assert.equal(report.status, "PREFLIGHT_OBSERVED", report.error?.message);
  assert.equal(report.model_send_calls, 0);
  assert.equal(state.sendCalls, 0);
  assert.equal(report.model_result, undefined);
  assert.equal(report.model_completion_event, undefined);
  assert.deepEqual(state.rows, profile.todos);
  assert.equal(state.entries.length, 1);
  assert.ok(Object.values(report.checks).every(value => value === true));
  assert.deepEqual(report.model_configuration, { modelId: "fixture-model", reasoningEffort: "medium" });
  assert.ok(report.preflight.some(item => item.name === "sibling" && item.result.resultType === "rejected"));
  assert.equal(state.owners, 0);
});

test("profile candidate sends supplied bytes once without imposing synthetic marker/row/timer outcomes", async t => {
  const { config, profile, state, root } = await profileFixture(t);
  assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
  const report = await runProbe("candidate", { ...config, output: join(root, "candidate.json") });
  assert.equal(report.status, "CANDIDATE_OBSERVED", report.error?.message);
  assert.equal(state.sendCalls, 1);
  assert.equal(state.sentPrompt, "Original words {NATIVE_GOAL_PATH}\r\n");
  assert.deepEqual(state.rows, profile.todos);
  assert.equal(state.entries.length, 1);
  assert.deepEqual(state.resumes.at(-1).model, "fixture-model");
  assert.deepEqual(state.resumes.at(-1).reasoningEffort, "medium");
});

test("profile data, model, owner-file and coordinate refusals occur before SDK start", async t => {
  const { config, root, state } = await profileFixture(t);
  for (const change of [
    { model: "wrong-model" }, { effort: "high" }, { profile: "other" },
    { evidence_paths: [config.state_file] }, { denied_path: config.evidence_paths[0] },
    { event_log: config.state_file }, { plugin_path: config.cwd },
    { home: config.os_home },
  ]) {
    const report = await runProbe("setup", { ...config, ...change, output: join(root, `${randomUUID()}.json`) });
    assert.equal(report.status, "ERROR");
    assert.equal(report.calls.length, 0);
  }
  for (const field of ["query", "code", "home", "session_id", "grants"]) {
    assert.throws(() => validateProfile({ ...nativeProfile(), [field]: "not data" }), /Invalid/);
  }
  chmodSync(config.state_file, 0o644);
  assert.throws(() => validateConfig("setup", config), /owner-only/);
  chmodSync(config.state_file, 0o600);
  linkSync(config.state_file, join(root, "state-alias.json"));
  assert.throws(() => validateConfig("setup", config), /single-link/);
  assert.equal(state.starts, 0);
});

test("profile partial setup and cold dependency errors clean every owned row/schedule", async t => {
  for (const failure of ["schedule", "dependencies"]) {
    await t.test(failure, async t => {
      const { config, state } = await profileFixture(t);
      if (failure === "schedule") state.nextId = 0;
      else state.dependencyMismatch = true;
      const report = await runProbe("setup", config);
      assert.equal(report.status, "ERROR");
      assert.ok(report.error);
      assert.deepEqual(state.rows, []);
      assert.deepEqual(state.dependencies, []);
      // An invalid ID cannot be passed to schedule.stop, and is retained as cleanup failure.
      if (failure === "dependencies") assert.deepEqual(state.entries, []);
      else assert.ok(report.cleanup.errors.length);
      assert.equal(state.owners, 0);
    });
  }
});

test("profile owner detects prefix and actual model mismatches before any send", async t => {
  for (const failure of ["prefix", "model"]) {
    await t.test(failure, async t => {
      const { config, state, root } = await profileFixture(t);
      assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
      if (failure === "prefix") state.events.push({
        id: "extra", type: "user.message", data: { content: "Not the imported prefix" },
      });
      else state.modelOverride = { modelId: "fixture-model", reasoningEffort: "high" };
      const report = await runProbe("preflight", { ...config, output: join(root, "preflight.json") });
      assert.equal(report.status, "PREMODEL_BLOCKED");
      assert.equal(report.model_send_calls, 0);
      assert.equal(state.sendCalls, 0);
      assert.match(report.firsterror, failure === "prefix" ? /prefix differs/ : /model configuration/);
      assert.equal(state.owners, 0);
    });
  }
});

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

test("literal grants approve typed writes and shell only without widening default permissions", t => {
  const { config, root, goalPath } = fixture(t);
  const target = join(config.cwd, "target.txt");
  const check = join(config.cwd, "check.py");
  writeFileSync(target, "pending\n");
  writeFileSync(check, "Owned fixed check");
  const permissions = { write_paths: ["target.txt", "new.txt"], shell_commands: ["python3 -I check.py"] };
  const receipts = [];
  const handler = candidatePermissionHandler({ ...config, candidate_permissions: permissions }, goalPath, root, receipts);
  const invocation = { sessionId: config.session_id };
  const write = { kind: "write", intention: "Patch data", fileName: target, diff: "Data diff",
    canOfferSessionApproval: true, toolCallId: "write", fileEdits: [
      { before: { path: target, content: "pending\n" }, after: { path: target, content: "ready\n" } },
    ] };
  const shell = { kind: "shell", intention: "Check data", fullCommandText: "python3 -I check.py",
    commands: [{ identifier: "python3", readOnly: false }], canOfferSessionApproval: true,
    hasWriteFileRedirection: false, possiblePaths: ["check.py"], possibleUrls: [], toolCallId: "shell",
    resolvedWorkingDirectory: config.cwd, resolvedPaths: { "check.py": check } };
  assert.equal(handler(write, invocation).kind, "approve-once");
  assert.equal(handler(shell, invocation).kind, "approve-once");
  assert.equal(handler({ ...write, fileName: join(config.cwd, "new.txt"), fileEdits: [
    { after: { path: join(config.cwd, "new.txt"), content: "new data" } },
  ] }, invocation).kind, "approve-once");
  for (const request of [
    { ...write, fileName: check }, { ...write, resolvedPath: check }, { ...write, fileEdits: [] },
    { ...write, fileEdits: [{ before: { path: target, content: "" }, after: { path: check, content: "" } }] },
    { ...write, managedApprovalRequired: true }, { ...write, requestSandboxBypass: true },
    { ...shell, fullCommandText: "python3 check.py" }, { ...shell, hasWriteFileRedirection: true },
    { ...shell, possibleUrls: [{ url: "https://example.invalid" }] },
    { ...shell, requestSandboxPermissive: true }, { ...shell, resolvedWorkingDirectory: root },
    { ...shell, resolvedPaths: { "check.py": target } }, { ...shell, command: "python3 -I check.py" },
  ]) assert.equal(handler(request, invocation).kind, "reject");
  assert.equal(handler(write, { sessionId: randomUUID() }).kind, "reject");
  const defaults = candidatePermissionHandler(config, goalPath, root, []);
  assert.equal(defaults(write, invocation).kind, "reject");
  assert.equal(defaults(shell, invocation).kind, "reject");
  linkSync(target, join(root, "hard-linked-data"));
  assert.equal(handler(write, invocation).kind, "reject");
});

test("cold observation retains edited fixture bytes and confirmed absence", async t => {
  const { config, root } = await editableProfileFixture(t);
  config.evidence_paths.push(join(config.cwd, "target.txt"), join(config.cwd, "check.py"));
  const setup = await runProbe("setup", config);
  assert.equal(setup.status, "SETUP_OBSERVED", setup.error?.message);
  const target = join(config.cwd, "target.txt");
  writeFileSync(target, "ready\n");
  const observed = await runProbe("observe", { ...config, output: join(root, "edited-observation.json") });
  assert.equal(observed.status, "OBSERVED", observed.error?.message);
  assert.deepEqual(observed.editable_fixture, {
    path: "target.txt", exists: true, mode: lstatSync(target).mode & 0o777,
    sha256: createHash("sha256").update("ready\n").digest("hex"),
    content_base64: Buffer.from("ready\n").toString("base64"),
  });
  const checker = join(config.cwd, "check.py");
  assert.deepEqual(observed.editable_checker, {
    path: "check.py", exists: true, mode: lstatSync(checker).mode & 0o777,
    sha256: createHash("sha256").update(editableFixtureCheck).digest("hex"),
    expected_sha256: createHash("sha256").update(editableFixtureCheck).digest("hex"),
    matches_frozen_fixture: true,
  });
  rmSync(target);
  const absent = await runProbe("observe", { ...config, output: join(root, "absent-observation.json") });
  assert.equal(absent.status, "OBSERVED", absent.error?.message);
  assert.deepEqual(absent.editable_fixture, { path: "target.txt", exists: false });
  assert.throws(() => validateConfig("candidate", config), /ENOENT/);
  assert.throws(() => validateConfig("preflight", config), /ENOENT/);
  for (const op of ["observe", "cleanup"]) {
    assert.throws(() => validateConfig(op, {
      ...config, evidence_paths: [join(root, "missing-evidence")],
    }), /Invalid trusted phase coordinates/);
    assert.throws(() => validateConfig(op, {
      ...config, evidence_paths: [`${config.cwd}/./missing-evidence`],
    }), /absolute normalized path/);
  }
  const cleaned = await runProbe("cleanup", { ...config, output: join(root, "absent-cleanup.json") });
  assert.equal(cleaned.status, "CLEANED", cleaned.error?.message);
  assert.deepEqual(cleaned.cleanup.todos.rows, []);
  assert.deepEqual(cleaned.cleanup.schedules.entries, []);
  assert.equal(cleaned.cleanup.dependencies_empty, true);
});

test("cold observation rejects a changed or missing fixed checker", async t => {
  for (const changed of [true, false]) {
    const { config, root } = await editableProfileFixture(t);
    config.evidence_paths.push(join(config.cwd, "target.txt"), join(config.cwd, "check.py"));
    const setup = await runProbe("setup", config);
    assert.equal(setup.status, "SETUP_OBSERVED", setup.error?.message);
    const checker = join(config.cwd, "check.py");
    if (changed) writeFileSync(checker, "Altered checker\n");
    else rmSync(checker);
    const observed = await runProbe("observe", { ...config, output: join(root, "checker-observation.json") });
    assert.equal(observed.status, "ERROR");
    assert.equal(observed.editable_checker.exists, changed);
    assert.equal(observed.editable_checker.matches_frozen_fixture, false);
    assert.match(observed.error.message, /Fixed fixture checker/);
    const cleaned = await runProbe("cleanup", { ...config, output: join(root, "checker-cleanup.json") });
    assert.equal(cleaned.status, "CLEANED", cleaned.error?.message);
  }
});

test("observed SDK bash shell metadata preserves the exact command grant", t => {
  const { config, root, goalPath } = fixture(t);
  const handler = candidatePermissionHandler({ ...config,
    candidate_permissions: { write_paths: [], shell_commands: ["python3 -I check.py"] },
  }, goalPath, root, []);
  const invocation = { sessionId: config.session_id };
  const request = { kind: "shell", toolCallId: "observed-shell", fullCommandText: "python3 -I check.py",
    shellType: "bash", intention: "Check owned fixture data",
    commands: [{ identifier: "python3 -I check.py", readOnly: false }],
    commandSegments: [{ identifier: "python3", fullCommandText: "python3 -I check.py" }],
    possiblePaths: [], canOfferSessionApproval: false, possibleUrls: [], hasWriteFileRedirection: false };
  assert.equal(handler(request, invocation).kind, "approve-once");
  for (const shellType of ["powershell", null, 1]) {
    assert.equal(handler({ ...request, shellType }, invocation).kind, "reject");
  }
  assert.equal(handler({ ...request, fullCommandText: "python3 -V" }, invocation).kind, "reject");
  assert.equal(candidatePermissionHandler(config, goalPath, root, [])(request, invocation).kind, "reject");
});

test("owner permission profiles reuse literal validation before the SDK starts", async t => {
  const { config, root, state } = await profileFixture(t);
  for (const candidate_permissions of [
    null, {}, { write_paths: ["../outside"], shell_commands: [] },
    { write_paths: ["*.txt"], shell_commands: [] },
    { write_paths: [], shell_commands: ["copilot '--yolo'"] },
    { write_paths: [], shell_commands: ["python3 '"] },
  ]) {
    const report = await runProbe("setup", { ...config, candidate_permissions, output: join(root, `${randomUUID()}.json`) });
    assert.equal(report.status, "ERROR");
    assert.equal(state.starts, 0);
  }
});

test("selected literal grants reach SDK metadata without changing default profile selection", async t => {
  const { config, root, state } = await profileFixture(t);
  assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
  for (const candidate_permissions of [
    { write_paths: [], shell_commands: [] },
    { write_paths: ["target.txt"], shell_commands: [] },
    { write_paths: [], shell_commands: ["python3 -I check.py"] },
  ]) {
    const report = await runProbe("preflight", { ...config, candidate_permissions,
      output: join(root, `${randomUUID()}.json`), event_log: join(root, `${randomUUID()}.jsonl`) });
    assert.equal(report.status, "PREFLIGHT_OBSERVED", report.error?.message);
    assert.deepEqual(state.resumes.at(-1).availableTools, ["skill", "view", "sql", "manage_schedule",
      ...(candidate_permissions.write_paths.length ? ["apply_patch"] : []),
      ...(candidate_permissions.shell_commands.length ? ["bash"] : [])]);
    assert.equal(state.sendCalls, 0);
  }
});

test("editable preflight verifies actual file/check decisions and restores before any inference", async t => {
  const { config, root, state, profile } = await editableProfileFixture(t);
  chmodSync(join(config.cwd, "check.py"), 0o444);
  assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
  const report = await runProbe("preflight", { ...config, output: join(root, "editable-preflight.json") });
  assert.equal(report.status, "PREFLIGHT_OBSERVED", report.error?.message);
  assert.equal(report.checks.editable_permission_traversal, true);
  assert.equal(report.editable_preflight.length, 6);
  assert.equal(report.editable_restored, true);
  assert.equal(readFileSync(join(config.cwd, "target.txt"), "utf8"), "pending\n");
  assert.equal(readFileSync(join(config.cwd, "check.py"), "utf8"), editableFixtureCheck);
  assert.equal(lstatSync(join(config.cwd, "check.py")).mode & 0o777, 0o444);
  assert.equal(state.sendCalls, 0);
  assert.deepEqual(state.rows, profile.todos);
  assert.deepEqual(state.resumes.at(-1).availableTools, ["skill", "view", "sql", "manage_schedule", "apply_patch", "bash"]);
});

test("editable preflight accepts observed freeform patch metadata but rejects null JSON tool schemas", async t => {
  for (const nullTool of ["apply_patch", "view", "bash"]) {
    await t.test(nullTool, async t => {
      const { config, root, state } = await editableProfileFixture(t);
      assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
      state.metadataOverride = { tools: ["skill", "view", "sql", "manage_schedule", "apply_patch", "bash"]
        .map(name => ({ name, description: "Native test double",
          input_schema: name === "apply_patch" || name === nullTool ? null : { type: "object" } })) };
      const report = await runProbe("preflight", { ...config, output: join(root, "freeform-metadata.json") });
      assert.equal(report.status, nullTool === "apply_patch" ? "PREFLIGHT_OBSERVED" : "PREMODEL_BLOCKED",
        report.error?.message);
      if (nullTool === "apply_patch") {
        assert.equal(typeof report.calls.find(call => call.name === "tools.execute:apply_patch").arguments.arguments,
          "string");
        assert.equal(report.checks.editable_permission_traversal, true);
        assert.equal(report.editable_restored, true);
      } else {
        assert.match(report.firsterror, /Effective native tool metadata/);
        assert.equal(report.editable_preflight, undefined);
      }
      assert.equal(readFileSync(join(config.cwd, "target.txt"), "utf8"), "pending\n");
      assert.equal(state.sendCalls, 0);
    });
  }
});

test("editable preflight rejects missing mediation, unrelated failure, native mutation and prefix pollution", async t => {
  for (const fault of ["uncorrelatedPermission", "unrelatedCheckFailure", "editableStateMutation", "editablePrefixMutation"]) {
    await t.test(fault, async t => {
      const { config, root, state } = await editableProfileFixture(t);
      assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
      state[fault] = true;
      const report = await runProbe("preflight", { ...config, output: join(root, "blocked-editable.json") });
      assert.equal(report.status, "PREMODEL_BLOCKED");
      assert.equal(report.editable_restored, true);
      assert.equal(state.sendCalls, 0);
      assert.equal(readFileSync(join(config.cwd, "target.txt"), "utf8"), "pending\n");
      assert.equal(readFileSync(join(config.cwd, "check.py"), "utf8"), editableFixtureCheck);
    });
  }
});

test("metadata and successful patch result without its effect do not qualify editable preflight", async t => {
  const { config, root, state } = await editableProfileFixture(t);
  assert.equal((await runProbe("setup", config)).status, "SETUP_OBSERVED");
  state.missingPatchEffect = true;
  const report = await runProbe("preflight", { ...config, output: join(root, "missing-effect.json") });
  assert.equal(report.status, "PREMODEL_BLOCKED");
  assert.match(report.firsterror, /patch effect is missing/);
  assert.equal(report.editable_restored, true);
  assert.equal(state.sendCalls, 0);
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

test("candidate forwards existing evaluator auth through SDK without recording its value", async t => {
  const { config, state, root } = await candidateFixture(t);
  const prior = process.env.COPILOT_GITHUB_TOKEN;
  const token = `synthetic-${randomUUID()}`;
  process.env.COPILOT_GITHUB_TOKEN = token;
  state.expectedGitHubToken = token;
  try {
    const report = await runProbe("candidate", config);
    assert.equal(report.status, "CANDIDATE_OBSERVED");
    assert.equal(state.explicitAuthMatched, true);
    assert.equal(state.loggedInUserEnabled, false);
    for (const text of [
      JSON.stringify(report), readFileSync(config.output, "utf8"),
      readFileSync(join(root, "candidate-raw.jsonl"), "utf8"),
    ]) assert.equal(text.includes(token), false);
  } finally {
    if (prior === undefined) delete process.env.COPILOT_GITHUB_TOKEN;
    else process.env.COPILOT_GITHUB_TOKEN = prior;
  }
});

test("missing or mismatched native sources, tools, mediation and history block before any send", async t => {
  for (const failure of [
    "missing-instructions", "wrong-content", "duplicate-instructions", "disabled-instructions",
    "missing-tools", "wrong-tools", "mcp-tools", "owner-bypass", "semantic-pollution", "cold-mismatch", "handler-error", "preflight-error", "denial-tool-failure",
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
    if (failure === "denial-tool-failure") state.denialResultType = "failure";
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
    assert.equal(report.firsterror, `${report.timeout_ms}-millisecond SDK send/completion deadline exceeded`);
    assert.equal(report.model_send_calls, 1);
    assert.equal(report.model_completion_event, undefined);
    assert.equal(state.aborts, 1);
    assert.equal(state.owners, 0);
    assert.equal(state.handlers.length, 0);
  });
});

test("exhausted owner budget blocks dispatch without a send", async t => {
  const { config, state } = await candidateFixture(t);
  let clockCalls = 0;
  t.mock.method(performance, "now", () => clockCalls++ === 0 ? 0 : 330000);
  const report = await runProbe("candidate", config);
  assert.equal(report.status, "PREMODEL_BLOCKED");
  assert.equal(report.firsterror, "client.start owner deadline exceeded");
  assert.equal(report.timeout_ms, undefined);
  assert.equal(report.max_timeout_ms, 300000);
  assert.equal(report.model_send_calls, 0);
  assert.equal(report.model_started_at, undefined);
  assert.equal(state.sendCalls, 0);
  assert.equal(state.aborts, 0);
  assert.equal(state.owners, 0);
});

test("prolonged preflight reduces the model deadline and leaves time for abort and close", async t => {
  const { config, state } = await candidateFixture(t);
  let clockCalls = 0;
  t.mock.method(performance, "now", () => clockCalls++ === 0 ? 0 : 329980);
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const ready = new Promise(resolve => { state.sendReady = resolve; });
  state.sendHook = id => id;
  const pending = runProbe("candidate", config);
  await ready;
  await new Promise(setImmediate);
  t.mock.timers.tick(19);
  await new Promise(setImmediate);
  assert.equal(state.aborts, 0);
  t.mock.timers.tick(1);
  const report = await pending;
  assert.equal(report.status, "FAILED");
  assert.equal(report.timeout_ms, 20);
  assert.equal(report.max_timeout_ms, 300000);
  assert.equal(report.firsterror, "20-millisecond SDK send/completion deadline exceeded");
  assert.equal(report.model_send_calls, 1);
  assert.equal(state.aborts, 1);
  assert.equal(state.owners, 0);
  assert.equal(state.handlers.length, 0);
});

test("stalled native operations retain errors and close within their budgets", async t => {
  for (const [operation, milliseconds] of [["read", 330000], ["abort", 5000], ["stop", 10000]]) {
    await t.test(operation, async t => {
      const { config, state } = await candidateFixture(t);
      state[`${operation}Stalls`] = true;
      if (operation === "abort") state.sendFails = true;
      t.mock.timers.enable({ apis: ["setTimeout"] });
      let report;
      void runProbe("candidate", config).then(value => { report = value; });
      const entered = () => operation === "read" ? state.eventReads
        : operation === "abort" ? state.aborts : state.stalledStops;
      for (let i = 0; i < 100 && !entered() && !report; i++) {
        await new Promise(resolve => setImmediate(resolve));
      }
      assert.ok(entered(), report?.error?.message ?? "Native operation was not reached");
      t.mock.timers.tick(milliseconds);
      for (let i = 0; i < 100 && !report; i++) await new Promise(resolve => setImmediate(resolve));
      assert.ok(report, "Native operation remained pending after its deadline");
      assert.equal(report.status, operation === "read" ? "PREMODEL_BLOCKED" : "FAILED");
      assert.equal(report.model_send_calls, operation === "read" ? 0 : 1);
      assert.equal(state.owners, 0);
      const name = operation === "read" ? "eventLog.read"
        : operation === "abort" ? "session.abort" : "client.stop";
      assert.match(report.calls.find(call => call.name === name && call.error)?.error.message ?? "",
        /deadline exceeded/);
      if (operation === "abort") assert.equal(report.error.message, "Test send transport failure");
      if (operation === "stop") assert.ok(report.calls.some(call => call.name === "client.forceStop"));
    });
  }
});
