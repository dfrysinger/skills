import {
  accessSync, closeSync, constants, lstatSync, openSync,
  readFileSync, writeFileSync,
} from "node:fs";
import { userInfo } from "node:os";
import { dirname, isAbsolute, join, resolve, sep } from "node:path";
import { performance } from "node:perf_hooks";
import { pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";

const fields = ["cli", "sdk", "home", "os_home", "cwd", "session_id", "output"];
const objective = "Synthetic native workflow diagnostic. Not a historical task.";
const prompt = "Synthetic native workflow diagnostic only.";
const rowId = "native-workflow-fixture";
const options = {
  continuePendingWork: false,
  suppressResumeEvent: true,
  allowTranscriptRecovery: false,
  availableTools: ["sql", "manage_schedule"],
  manageScheduleEnabled: true,
};

function requirePath(path, kind) {
  if (typeof path !== "string" || !isAbsolute(path) || resolve(path) !== path) {
    throw new Error("Expected an absolute normalized path");
  }
  for (let part = path; ; part = dirname(part)) {
    if (lstatSync(part).isSymbolicLink()) throw new Error("Symlink paths are not allowed");
    if (part === dirname(part)) break;
  }
  const stat = lstatSync(path);
  if (kind === "file" ? !stat.isFile() : !stat.isDirectory()) {
    throw new Error(`Expected a regular ${kind}`);
  }
}

function within(path, root) {
  return path === root || path.startsWith(root + sep);
}

function pathExists(path) {
  try {
    lstatSync(path);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

function validateOutput(config) {
  if (typeof config?.output !== "string" || !isAbsolute(config.output)
      || resolve(config.output) !== config.output
      || (typeof config.home === "string" && within(config.output, config.home))
      || fields.filter(key => key !== "output").some(key => config[key] === config.output)) {
    throw new Error("Expected a distinct receipt path outside the native home");
  }
  requirePath(dirname(config.output), "directory");
}

export function validateConfig(op, config) {
  if (!["setup", "observe", "cleanup"].includes(op)) throw new Error("Unknown operation");
  if (!config || typeof config !== "object" || Array.isArray(config)
      || Object.keys(config).length !== fields.length
      || fields.some(key => !Object.hasOwn(config, key))) {
    throw new Error("Expected only the fixed coordinator configuration fields");
  }
  if (typeof config.session_id !== "string"
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(config.session_id)) {
    throw new Error("Expected an imported session UUID");
  }
  for (const key of ["cli", "sdk"]) requirePath(config[key], "file");
  if (!config.sdk.endsWith("/index.js")) throw new Error("Expected the bundled SDK index.js");
  accessSync(config.cli, constants.X_OK);
  for (const key of ["home", "os_home", "cwd"]) requirePath(config[key], "directory");
  const hostHome = resolve(userInfo().homedir);
  const liveHomes = [hostHome, join(hostHome, ".copilot")];
  if (config.os_home === sep || config.home === sep
      || liveHomes.includes(config.os_home)
      || liveHomes.some(path => within(path, config.home))
      || within(config.home, join(hostHome, ".copilot"))) {
    throw new Error("Expected isolated homes, not a live namespace");
  }
  const sessionPath = join(config.home, "session-state", config.session_id);
  requirePath(sessionPath, "directory");
  const goalPath = join(sessionPath, "autopilot-objective.json");
  if (op !== "setup" || pathExists(goalPath)) requirePath(goalPath, "file");
  if (op === "setup" && pathExists(goalPath)) throw new Error("Setup requires an absent native goal");
  validateOutput(config);
  return goalPath;
}

function errorInfo(error) {
  return {
    name: error?.name ?? "Error",
    message: error?.message ?? String(error),
    ...(error?.code ? { code: error.code } : {}),
  };
}

export function matchesFixtureState(state, expectedFile) {
  const goal = state.goal?.state;
  const file = state.goal_file;
  const rows = state.todos?.rows;
  const entries = state.schedules?.entries;
  return goal?.id === 17 && goal.objective === objective && goal.status === "completed"
    && goal.turnCount === 0 && goal.creditCountNanoAiu === "0"
    && state.mode === "autopilot"
    && isDeepStrictEqual(file, expectedFile)
    && Array.isArray(rows) && rows.length === 1
    && rows[0].id === rowId && rows[0].title === "Synthetic pending work"
    && rows[0].description === "Owned diagnostic fixture" && rows[0].status === "pending"
    && Array.isArray(entries) && entries.length === 1 && entries[0].id === 1
    && entries[0].intervalMs === 14400000 && entries[0].recurring === true
    && entries[0].prompt === prompt
    && typeof entries[0].nextRunAt === "string"
    && Number.isFinite(Date.parse(entries[0].nextRunAt));
}

export async function runProbe(op, config) {
  const started = performance.now();
  const report = {
    status: "ERROR", session_id: config?.session_id,
    calls: [], shutdown_errors: [], model_calls: 0,
    modern_defaults: {
      version: 1, nextId: 18, autopilotOrigin: "objective",
      continuationCount: 0, turnCount: 0, tokenCount: 0,
      creditCountNanoAiu: "0", resumeCount: 0,
      timestamps: "Current setup timestamps, explicitly synthetic",
    },
    limits: [
      "Fixed synthetic diagnostic only; not historical state or a production profile",
      "Linux standalone/SDK interoperability and CLI-p behavior require Actions proof",
      "No model calls, schedule delivery, credential capture or permission overrides",
      "Cold schedule loading may re-arm nextRunAt; original counters are unknown",
    ],
  };
  let receipt;
  let client;
  let session;
  let sdk;
  let emptyFixture = false;
  let mutated = false;
  const fail = error => { report.error ??= errorInfo(error); };
  const call = async (name, arguments_, operation) => {
    const entry = { name, ...(arguments_ === undefined ? {} : { arguments: arguments_ }) };
    report.calls.push(entry);
    try {
      entry.result = await operation();
      return entry.result;
    } catch (error) {
      entry.error = errorInfo(error);
      throw error;
    }
  };
  const execute = async (name, arguments_) => {
    const result = await call(`tools.execute:${name}`, arguments_,
      () => session.rpc.tools.execute({ name, arguments: arguments_ }));
    if (result.resultType !== "success") throw new Error(`${name} did not succeed`);
    return result;
  };
  const stop = async () => {
    if (!client) return;
    const owner = client;
    let closed = false;
    try {
      const errors = await call("client.stop", undefined, () => owner.stop());
      for (const error of errors) report.shutdown_errors.push(errorInfo(error));
      if (errors.length) {
        fail(errors[0]);
        await call("client.forceStop", undefined, () => owner.forceStop());
      }
      closed = true;
    } catch (error) {
      report.shutdown_errors.push(errorInfo(error));
      fail(error);
      try {
        await call("client.forceStop", undefined, () => owner.forceStop());
        closed = true;
      } catch (forcedError) {
        report.shutdown_errors.push(errorInfo(forcedError));
        throw forcedError;
      }
    } finally {
      if (closed) {
        client = undefined;
        session = undefined;
      }
    }
  };
  const connect = async () => {
    if (client) throw new Error("Previous native owner has not stopped");
    client = new sdk.CopilotClient({
      connection: sdk.RuntimeConnection.forStdio({
        path: config.cli, args: [],
        env: {
          PATH: process.env.PATH ?? "",
          HOME: config.os_home, COPILOT_HOME: config.home,
          TMPDIR: config.cwd,
          COPILOT_DISABLE_KEYTAR: "1", COPILOT_OTEL_ENABLED: "false",
        },
      }),
      workingDirectory: config.cwd, baseDirectory: config.home,
      useLoggedInUser: false, logLevel: "error",
    });
    await call("client.start", undefined, () => client.start());
    if (typeof client.getStatus === "function") {
      report.runtime_identity = await call("client.getStatus", undefined, async () => {
        const status = await client.getStatus();
        return { version: status.version, protocolVersion: status.protocolVersion };
      });
    }
    await call("client.resumeSession", { session_id: config.session_id, ...options }, async () => {
      session = await client.resumeSession(config.session_id, options);
      return { session_id: session.sessionId };
    });
    if (session.sessionId !== config.session_id) throw new Error("Resumed a different namespace");
    await call("tools.initializeAndValidate", undefined,
      () => session.rpc.tools.initializeAndValidate());
  };
  const observe = async () => {
    requirePath(report.goal_path, "file");
    const state = {
      goal: await call("autopilotObjective.getState", undefined,
        () => session.rpc.autopilotObjective.getState()),
      mode: await call("mode.get", undefined, () => session.rpc.mode.get()),
      todos: await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos()),
      schedules: await call("schedule.list", undefined, () => session.rpc.schedule.list()),
    };
    await execute("sql", { description: "Read diagnostic rows", query: "SELECT * FROM todos" });
    const nativeFile = await call("workspaces.readAutopilotObjective", undefined,
      () => session.rpc.workspaces.readAutopilotObjective());
    state.goal_content = readFileSync(report.goal_path, "utf8");
    if (nativeFile.content !== state.goal_content) throw new Error("Native goal path/content mismatch");
    state.goal_file = JSON.parse(state.goal_content);
    return state;
  };
  const cleanup = async () => {
    const result = { errors: [] };
    report.cleanup = result;
    try {
      const entries = await call("schedule.list", undefined, () => session.rpc.schedule.list());
      result.schedule_ids = entries.entries.map(entry => entry.id);
      for (const entry of entries.entries) {
        try {
          if (!Number.isInteger(entry.id) || entry.id < 1) throw new Error("Invalid native schedule ID");
          await call("schedule.stop", { id: entry.id }, () => session.rpc.schedule.stop({ id: entry.id }));
        } catch (error) {
          result.errors.push(errorInfo(error));
          fail(error);
        }
      }
    } catch (error) {
      result.errors.push(errorInfo(error));
      fail(error);
    }
    try {
      await execute("sql", {
        description: "Remove the owned diagnostic row",
        query: "DELETE FROM todos WHERE id='native-workflow-fixture'",
      });
    } catch (error) {
      result.errors.push(errorInfo(error));
      fail(error);
    }
    try {
      result.todos = await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos());
    } catch (error) {
      result.errors.push(errorInfo(error));
      fail(error);
    }
    try {
      result.schedules = await call("schedule.list", undefined, () => session.rpc.schedule.list());
    } catch (error) {
      result.errors.push(errorInfo(error));
      fail(error);
    }
    if (!Array.isArray(result.todos?.rows) || !Array.isArray(result.schedules?.entries)
        || result.todos.rows.length || result.schedules.entries.length) {
      const error = new Error("Fixture cleanup did not leave empty native lists");
      result.errors.push(errorInfo(error));
      fail(error);
    }
    return result;
  };
  try {
    validateOutput(config);
    receipt = openSync(config.output, "wx", 0o600);
    report.goal_path = validateConfig(op, config);
    report.cli = config.cli;
    report.sdk = config.sdk;
    report.connection = { path: config.cli, args: [], useLoggedInUser: false };
    sdk = await import(pathToFileURL(config.sdk).href);
    await connect();
    if (op === "setup") {
      report.before = {
        goal: await call("autopilotObjective.getState", undefined,
          () => session.rpc.autopilotObjective.getState()),
        todos: await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos()),
        schedules: await call("schedule.list", undefined, () => session.rpc.schedule.list()),
      };
      await execute("sql", { description: "Check the empty diagnostic", query: "SELECT * FROM todos" });
      if (pathExists(report.goal_path) || report.before.goal.state !== null
          || report.before.todos.rows.length || report.before.schedules.entries.length) {
        throw new Error("Setup requires an empty imported native fixture");
      }
      emptyFixture = true;
      const now = new Date().toISOString();
      const expectedFile = {
        version: 1, nextId: 18,
        current: {
          id: 17, objective, status: "completed", autopilotOrigin: "objective",
          continuationCount: 0, turnCount: 0, tokenCount: 0,
          creditCountNanoAiu: "0", resumeCount: 0, createdAt: now, updatedAt: now,
        },
      };
      report.modern_defaults.createdAt = now;
      report.modern_defaults.updatedAt = now;
      mutated = true;
      await call("workspaces.writeAutopilotObjective", { content: JSON.stringify(expectedFile, null, 2) + "\n" },
        () => session.rpc.workspaces.writeAutopilotObjective({
          content: JSON.stringify(expectedFile, null, 2) + "\n",
        }));
      await call("mode.set", { mode: "autopilot" }, () => session.rpc.mode.set({ mode: "autopilot" }));
      await execute("sql", {
        description: "Insert the owned diagnostic row",
        query: "INSERT INTO todos (id,title,description,status) VALUES ('native-workflow-fixture','Synthetic pending work','Owned diagnostic fixture','pending')",
      });
      await execute("manage_schedule", { action: "create", interval: "4h", prompt });
      const created = await call("schedule.list", undefined, () => session.rpc.schedule.list());
      report.schedule_ids = created.entries.map(entry => entry.id);
      if (created.entries.length !== 1 || created.entries[0].id !== 1) {
        throw new Error("Expected first native schedule ID 1 in the fresh home");
      }
      await stop();
      if (report.error) throw new Error("Warm producer shutdown failed");
      await connect();
      Object.assign(report, await observe());
      if (!matchesFixtureState(report, expectedFile)) throw new Error("Cold native checkpoint mismatch");
      report.status = "SETUP_OBSERVED";
    } else {
      if (op === "cleanup") {
        report.cleanup = await cleanup();
        report.schedule_ids = report.cleanup.schedule_ids;
        if (report.error) throw new Error("Cleanup failed");
        report.status = "CLEANED";
      } else {
        Object.assign(report, await observe());
        report.schedule_ids = report.schedules.entries.map(entry => entry.id);
        report.status = "OBSERVED";
      }
    }
  } catch (error) {
    fail(error);
  } finally {
    try {
      await stop();
    } catch (error) {
      fail(error);
    }
    // A failed producer owns only the fixture proven empty before its first write.
    if (report.error && op === "setup" && emptyFixture && mutated) {
      try {
        await connect();
        report.cleanup = await cleanup();
      } catch (error) {
        report.cleanup_error = errorInfo(error);
      } finally {
        try { await stop(); } catch (error) { fail(error); }
      }
    }
    if (report.error) report.status = "ERROR";
    report.elapsed_seconds = (performance.now() - started) / 1000;
    if (receipt !== undefined) {
      try {
        writeFileSync(receipt, JSON.stringify(report, null, 2) + "\n");
      } finally {
        closeSync(receipt);
      }
    }
  }
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 4) throw new Error("Usage: native_workflow_probe.mjs OP CONFIG_JSON");
    const report = await runProbe(process.argv[2], JSON.parse(process.argv[3]));
    console.log(JSON.stringify({ status: report.status, error: report.error }));
    if (report.error) process.exitCode = 1;
  } catch (error) {
    console.error(JSON.stringify(errorInfo(error)));
    process.exitCode = 1;
  }
}
