import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { matchesFixtureState, runProbe, validateConfig } from "./native_workflow_probe.mjs";

// This SDK double exercises control flow only, never native interoperability.
const sdkDouble = `
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
export const state = {
  rows: [], entries: [], nextId: 1, owners: 0, starts: 0, stops: 0,
  mode: "interactive", connections: [], resumes: [], deleteFails: false,
};
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
      rpc: {
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
          initializeAndValidate: async () => ({}),
          execute: async ({ name, arguments: args }) => {
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
