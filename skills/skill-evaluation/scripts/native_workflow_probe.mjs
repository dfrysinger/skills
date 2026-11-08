import {
  accessSync, closeSync, constants, lstatSync, openSync,
  readFileSync, writeFileSync,
} from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { userInfo } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { performance } from "node:perf_hooks";
import { pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";

const fields = ["cli", "sdk", "home", "os_home", "cwd", "session_id", "output"];
const phaseFields = [...fields, "profile", "state_file", "prompt_path", "event_log",
  "plugin_path", "evidence_paths", "denied_path", "model", "effort", "prefix_file"];
const conversational = events => events.filter(event =>
  /^(user\.message|assistant\.message|tool\.result|tool\.execution_complete)$/.test(event.type));
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

export function validateProfile(state) {
  const object = (value, keys) => value && typeof value === "object" && !Array.isArray(value)
    && isDeepStrictEqual(Object.keys(value).sort(), [...keys].sort());
  const text = value => typeof value === "string" && value.trim() && !value.includes("\0");
  const texts = value => Array.isArray(value) && value.every(text);
  if (!object(state, ["schema_version", "profile", "provenance", "goal", "mode", "todos",
    "dependencies", "schedules", "model", "effort", "unknowns"])
      || state.schema_version !== 1 || state.profile !== "p01-scheduled-audit"
      || !["historical-projection", "synthetic-calibration"].includes(state.provenance)
      || !["interactive", "autopilot"].includes(state.mode) || !text(state.model)
      || !["low", "medium", "high"].includes(state.effort)
      || !texts(state.unknowns) || !state.unknowns.length) throw new Error("Invalid native state profile");
  const id = value => Number.isInteger(value) && value > 0 && value < 2 ** 31;
  if (!object(state.goal, ["id", "objective", "status"]) || !id(state.goal.id)
      || !text(state.goal.objective) || !["active", "completed"].includes(state.goal.status)) {
    throw new Error("Invalid native goal projection");
  }
  if (!Array.isArray(state.todos) || state.todos.length > 100
      || state.todos.some(row => !object(row, ["id", "title", "description", "status"])
        || !text(row.id) || !text(row.title) || typeof row.description !== "string"
        || row.description.includes("\0") || !["pending", "in_progress", "done", "blocked"].includes(row.status))
      || new Set(state.todos.map(row => row.id)).size !== state.todos.length) {
    throw new Error("Invalid native todo projection");
  }
  const ids = new Set(state.todos.map(row => row.id));
  if (!Array.isArray(state.dependencies) || state.dependencies.length > 200
      || state.dependencies.some(dep => !object(dep, ["todo_id", "depends_on"])
        || !ids.has(dep.todo_id) || !ids.has(dep.depends_on) || dep.todo_id === dep.depends_on)
      || new Set(state.dependencies.map(dep => JSON.stringify([dep.todo_id, dep.depends_on]))).size !== state.dependencies.length) {
    throw new Error("Invalid native dependency projection");
  }
  if (!Array.isArray(state.schedules) || state.schedules.length > 20
      || state.schedules.some(entry => !object(entry, ["id", "interval", "prompt", "status"])
        || !id(entry.id) || !text(entry.prompt) || !/^[1-9][0-9]{0,5}[smhd]$/.test(entry.interval)
        || !["active", "stopped"].includes(entry.status))
      || new Set(state.schedules.map(entry => entry.id)).size !== state.schedules.length) {
    throw new Error("Invalid native schedule projection");
  }
  return state;
}

function parseDataJson(content) {
  const result = JSON.parse(content);
  const stack = [];
  for (const match of content.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\]]/g)) {
    if (match[0] === "{") stack.push(new Set());
    else if (match[0] === "[") stack.push(null);
    else if (match[0] === "}" || match[0] === "]") stack.pop();
    else if (content.slice(match.index + match[0].length).trimStart().startsWith(":")) {
      const key = JSON.parse(match[0]);
      const keys = stack.at(-1);
      if (keys?.has(key)) throw new Error("Duplicate native JSON field");
      keys?.add(key);
    }
  }
  return result;
}

function profileState(config) {
  requirePath(config.state_file, "file");
  const stat = lstatSync(config.state_file);
  if ((stat.mode & 0o077) || stat.uid !== userInfo().uid || stat.nlink !== 1
      || within(config.state_file, config.cwd) || within(config.state_file, config.home)) {
    throw new Error("Native state must be an owner-only single-link file outside model evidence and home");
  }
  const state = validateProfile(parseDataJson(readFileSync(config.state_file, "utf8")));
  if (state.model !== config.model || state.effort !== config.effort) {
    throw new Error("Caller model/effort does not match frozen native descriptor");
  }
  return state;
}

export function validateConfig(op, config) {
  if (!["setup", "observe", "cleanup", "candidate", "preflight"].includes(op)) throw new Error("Unknown operation");
  const selected = config?.profile !== undefined;
  const keys = selected ? phaseFields : fields;
  if (!config || typeof config !== "object" || Array.isArray(config)
      || Object.keys(config).length !== keys.length
      || keys.some(key => !Object.hasOwn(config, key)) || (!selected && op === "preflight")) {
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
  for (const key of ["home", "os_home"]) {
    const stat = lstatSync(config[key]);
    if (stat.uid !== userInfo().uid || (selected && (stat.mode & 0o077))) {
      throw new Error("Expected owned private native homes");
    }
  }
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
  if (lstatSync(sessionPath).uid !== userInfo().uid) throw new Error("Expected an owned imported namespace");
  const goalPath = join(sessionPath, "autopilot-objective.json");
  if ((op !== "setup" && op !== "cleanup") || pathExists(goalPath)) requirePath(goalPath, "file");
  if (op === "setup" && pathExists(goalPath)) throw new Error("Setup requires an absent native goal");
  validateOutput(config);
  if (selected) {
    if (config.profile !== "p01-scheduled-audit") throw new Error("Unsupported native profile");
    profileState(config);
    if (pathExists(goalPath) && (lstatSync(goalPath).uid !== userInfo().uid
        || lstatSync(goalPath).nlink !== 1)) throw new Error("Native goal must be owned and single-link");
    if (within(config.cwd, config.home) || within(config.home, config.cwd)
        || within(config.cwd, config.os_home) || within(config.os_home, config.cwd)
        || within(config.home, config.os_home) || within(config.os_home, config.home)) {
      throw new Error("Native homes and evidence must be disjoint");
    }
    for (const key of ["prompt_path", "denied_path", "prefix_file"]) requirePath(config[key], "file");
    const prefixStat = lstatSync(config.prefix_file);
    if ((prefixStat.mode & 0o077) || prefixStat.uid !== userInfo().uid || prefixStat.nlink !== 1
        || within(config.prefix_file, config.cwd) || within(config.prefix_file, config.home)) {
      throw new Error("Imported prefix must be owner-only outside model evidence/home");
    }
    requirePath(config.plugin_path, "directory");
    if (!Array.isArray(config.evidence_paths) || !config.evidence_paths.length
        || config.evidence_paths.some(path => {
          requirePath(path, "file");
          return !within(path, config.cwd) || within(path, config.plugin_path);
        }) || within(config.denied_path, config.cwd)
        || within(config.denied_path, config.home) || within(config.plugin_path, config.home)
        || within(config.prompt_path, config.cwd) || within(config.prompt_path, config.home)
        || within(config.output, config.cwd)
        || within(config.plugin_path, config.cwd)
        || typeof config.event_log !== "string" || !isAbsolute(config.event_log)
        || resolve(config.event_log) !== config.event_log || within(config.event_log, config.cwd)
        || within(config.event_log, config.home)) throw new Error("Invalid trusted phase coordinates");
    requirePath(dirname(config.event_log), "directory");
    if (new Set([config.output, config.event_log, config.prompt_path, config.state_file,
      config.denied_path, config.prefix_file]).size !== 6) throw new Error("Phase files must be distinct");
  }
  return goalPath;
}

const quoteSql = value => "'" + value.replaceAll("'", "''") + "'";
const intervalMs = interval => Number(interval.slice(0, -1))
  * { s: 1000, m: 60000, h: 3600000, d: 86400000 }[interval.at(-1)];

export function matchesProfileState(observed, state, mapping) {
  const goal = observed.goal?.state;
  const rows = observed.todos?.rows;
  const schedules = observed.schedules?.entries;
  const project = row => Object.fromEntries(["id", "title", "description", "status"].map(key => [key, row[key]]));
  const sort = rows => rows.map(project).sort((a, b) => a.id.localeCompare(b.id));
  const active = state.schedules.filter(entry => entry.status === "active");
  return goal?.id === state.goal.id && goal.objective === state.goal.objective
    && goal.status === state.goal.status && observed.mode === state.mode
    && Array.isArray(rows) && isDeepStrictEqual(sort(rows), sort(state.todos))
    && Array.isArray(mapping) && mapping.length === state.schedules.length
    && mapping.every((item, index) => item.source_id === state.schedules[index].id
      && Number.isInteger(item.native_id) && item.native_id > 0)
    && new Set(mapping.map(item => item.native_id)).size === mapping.length
    && Array.isArray(schedules) && schedules.length === active.length
    && active.every(entry => schedules.some(actual =>
      actual.id === mapping.find(item => item.source_id === entry.id)?.native_id
      && actual.prompt === entry.prompt && actual.recurring === true
      && actual.intervalMs === intervalMs(entry.interval)
      && Number.isFinite(Date.parse(actual.nextRunAt))));
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

export function candidatePermissionHandler(config, goalPath, pluginPath, receipts) {
  return (request, invocation) => {
    const entry = { session_id: invocation?.sessionId, tool_call_id: request?.toolCallId, invocation, request };
    const decision = { kind: "reject" };
    try {
      if (invocation?.sessionId !== config.session_id || !request
          || typeof request.toolCallId !== "string" || !request.toolCallId
          || ["managedApprovalRequired", "requestSandboxBypass", "skipPermission"].some(key =>
            request[key] !== undefined && request[key] !== false)
          || request.sandboxPathGrant !== undefined) {
        return decision;
      }
      if (request.kind === "read") {
        if (Object.keys(request).some(key => ![
          "kind", "intention", "path", "resolvedPath", "toolCallId", "managedApprovalRequired",
          "requestSandboxBypass", "requestSandboxBypassReason", "sandboxPathGrant",
        ].includes(key))) return decision;
        if (typeof request.intention !== "string" || typeof request.path !== "string" || !request.path) return decision;
        const target = resolve(config.cwd, request.path);
        if (request.path !== (isAbsolute(request.path) ? target : relative(config.cwd, target))) return decision;
        requirePath(target, lstatSync(target).isDirectory() ? "directory" : "file");
        if (request.resolvedPath !== undefined && request.resolvedPath !== target) return decision;
        if (!within(target, pluginPath) && (target === goalPath || within(target, config.cwd))) {
          decision.kind = "approve-once";
        }
      } else if (request.kind === "custom-tool"
          && Object.keys(request).every(key => [
            "kind", "args", "toolCallId", "toolDescription", "toolName", "skipPermission", "managedApprovalRequired",
          ].includes(key))
          && typeof request.toolDescription === "string"
          && ["skill", "sql", "manage_schedule"].includes(request.toolName)) {
        decision.kind = "approve-once";
      }
      return decision;
    } catch (error) {
      entry.error = errorInfo(error);
      return decision;
    } finally {
      entry.decision = { ...decision };
      receipts.push(entry);
    }
  };
}

export async function runProbe(op, config) {
  const started = performance.now();
  let ownerDeadline = started + 330000;
  const isCandidate = op === "candidate" || op === "preflight";
  const selected = config?.profile !== undefined;
  let projection;
  let scheduleMapping;
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
  let candidateOptions;
  let eventFile;
  let unsubscribe;
  const candidateEvents = [];
  let emptyFixture = false;
  let mutated = false;
  const fail = error => { report.error ??= errorInfo(error); };
  const call = async (name, arguments_, operation) => {
    const entry = { name, ...(arguments_ === undefined ? {} : { arguments: arguments_ }) };
    report.calls.push(entry);
    const timeout = name === "session.abort" || name === "client.forceStop" ? 5000
      : name === "client.stop" ? 10000
        : Math.max(0, ownerDeadline - performance.now());
    let timer;
    try {
      if (!timeout) throw new Error(`${name} owner deadline exceeded`);
      entry.result = await Promise.race([
        Promise.resolve().then(operation),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error(`${name} deadline exceeded`)), timeout);
        }),
      ]);
      return entry.result;
    } catch (error) {
      entry.error = errorInfo(error);
      throw error;
    } finally {
      clearTimeout(timer);
    }
  };
  const execute = async (name, arguments_) => {
    const toolCallId = selected ? `native-owner-${randomUUID()}` : undefined;
    if (selected) (report.owner_tool_call_ids ??= []).push(toolCallId);
    const result = await call(`tools.execute:${name}`, arguments_,
      () => session.rpc.tools.execute({
        name, arguments: arguments_, ...(toolCallId ? { toolCallId } : {}),
      }));
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
      ...(isCandidate ? {
        mode: "copilot-cli", gitHubToken: process.env.COPILOT_GITHUB_TOKEN,
      } : {}),
    });
    await call("client.start", undefined, () => client.start());
    if (typeof client.getStatus === "function") {
      report.runtime_identity = await call("client.getStatus", undefined, async () => {
        const status = await client.getStatus();
        return { version: status.version, protocolVersion: status.protocolVersion };
      });
    }
    const resumeOptions = candidateOptions ?? options;
    const { onPermissionRequest, ...recordedOptions } = resumeOptions;
    await call("client.resumeSession", { session_id: config.session_id, ...recordedOptions }, async () => {
      session = await client.resumeSession(config.session_id, resumeOptions);
      return { session_id: session.sessionId };
    });
    if (session.sessionId !== config.session_id) throw new Error("Resumed a different namespace");
    if (isCandidate) {
      unsubscribe = session.on(event => {
        try {
          writeFileSync(eventFile, JSON.stringify(event) + "\n");
          candidateEvents.push(event);
        } catch (error) { fail(error); }
      });
    }
    await call("tools.initializeAndValidate", undefined,
      () => session.rpc.tools.initializeAndValidate());
  };
  const observe = async (nativeSql = true) => {
    requirePath(report.goal_path, "file");
    const state = {
      goal: await call("autopilotObjective.getState", undefined,
        () => session.rpc.autopilotObjective.getState()),
      mode: await call("mode.get", undefined, () => session.rpc.mode.get()),
      todos: await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos()),
      schedules: await call("schedule.list", undefined, () => session.rpc.schedule.list()),
    };
    if (nativeSql) await execute("sql", { description: "Read diagnostic rows", query: "SELECT * FROM todos" });
    if (selected) {
      const expected = projection.dependencies.length ? projection.dependencies.map(dep =>
        `SELECT ${quoteSql(dep.todo_id)} AS todo_id,${quoteSql(dep.depends_on)} AS depends_on`).join(" UNION ALL ")
        : "SELECT todo_id,depends_on FROM todo_deps WHERE 0";
      const dependencies = await execute("sql", {
        description: "Compare cold owned dependency projection",
        query: `WITH expected AS (${expected}), missing AS (
          SELECT * FROM expected EXCEPT SELECT todo_id,depends_on FROM todo_deps
        ), extra AS (
          SELECT todo_id,depends_on FROM todo_deps EXCEPT SELECT * FROM expected
        ) SELECT * FROM missing UNION ALL SELECT * FROM extra`,
      });
      state.dependency_comparison = dependencies;
      state.dependencies_match = dependencies.toolTelemetry?.metrics?.rowsReturned === 0;
    }
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
        description: selected ? "Remove the owned profile dependencies" : "Remove the owned diagnostic row",
        query: selected ? "DELETE FROM todo_deps" : "DELETE FROM todos WHERE id='native-workflow-fixture'",
      });
      if (selected) await execute("sql", { description: "Remove owned profile rows", query: "DELETE FROM todos" });
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
    if (selected) {
      try {
        const dependencies = await execute("sql", {
          description: "Verify empty owned dependencies", query: "SELECT todo_id,depends_on FROM todo_deps",
        });
        result.dependencies_empty = dependencies.toolTelemetry?.metrics?.rowsReturned === 0;
      } catch (error) {
        result.errors.push(errorInfo(error));
        fail(error);
      }
    }
    if (!Array.isArray(result.todos?.rows) || !Array.isArray(result.schedules?.entries)
        || result.todos.rows.length || result.schedules.entries.length
        || (selected && !result.dependencies_empty)) {
      const error = new Error("Fixture cleanup did not leave empty native lists");
      result.errors.push(errorInfo(error));
      fail(error);
    }
    return result;
  };
  const candidate = async () => {
    const hash = content => createHash("sha256").update(content).digest("hex");
    const readEvents = async (cursor) => {
      const events = [];
      let more;
      do {
        const batch = await call("eventLog.read", { cursor, max: 1000, includeEphemeral: false },
          () => session.rpc.eventLog.read({ cursor, max: 1000, includeEphemeral: false }));
        if (!Array.isArray(batch?.events) || typeof batch.cursor !== "string"
            || typeof batch.hasMore !== "boolean" || batch.cursorStatus !== "ok"
            || (batch.hasMore && batch.cursor === cursor)
            || batch.events.some(event => typeof event?.type !== "string" || typeof event.id !== "string"
              || !event.data || typeof event.data !== "object")) throw new Error("Unknown native event cursor or batch");
        events.push(...batch.events);
        cursor = batch.cursor;
        more = batch.hasMore;
      } while (more);
      return events;
    };
    report.prefix_before = await readEvents();
    if (selected) {
      const imported = JSON.parse(readFileSync(config.prefix_file, "utf8"));
      if (!Array.isArray(imported) || !conversational(imported).length
          || !isDeepStrictEqual(conversational(report.prefix_before), conversational(imported))) {
        throw new Error("Candidate prefix differs from the retained public import projection");
      }
      report.checks.imported_prefix_correspondence = true;
    }
    const tail = await call("eventLog.tail", undefined, () => session.rpc.eventLog.tail());
    if (typeof tail?.cursor !== "string") throw new Error("Missing native event tail cursor");
    const sources = await call("instructions.getSources", undefined, () => session.rpc.instructions.getSources());
    report.instructions = sources;
    const personalPath = join(config.home, "copilot-instructions.md");
    requirePath(personalPath, "file");
    report.personal_instruction_sha256 = hash(readFileSync(personalPath));
    const source = sources?.sources?.[0];
    if (!Array.isArray(sources?.sources) || sources.sources.length !== 1
        || source.sourcePath !== personalPath || typeof source.content !== "string"
        || hash(source.content) !== report.personal_instruction_sha256
        || source.type !== "home" || source.location !== "user"
        || typeof source.id !== "string" || typeof source.label !== "string"
        || (source.defaultDisabled !== undefined && source.defaultDisabled !== false)) {
      throw new Error("Native instruction sources do not match the sole staged personal file");
    }
    report.instruction_sources = [{ path: source.sourcePath, sha256: hash(source.content), merge_order: 0 }];
    report.checks.instruction_correspondence = true;
    report.effective_tools = await call("tools.getCurrentMetadata", undefined,
      () => session.rpc.tools.getCurrentMetadata());
    const tools = report.effective_tools?.tools;
    if (!Array.isArray(tools) || tools.length !== 4
        || !isDeepStrictEqual(tools.map(tool => tool.name).sort(), ["manage_schedule", "skill", "sql", "view"])
        || tools.some(tool => typeof tool.description !== "string"
          || ["namespacedName", "mcpServerName", "mcpToolName"].some(key => tool[key] !== undefined)
          || (tool.input_schema !== undefined && (!tool.input_schema
            || typeof tool.input_schema !== "object" || Array.isArray(tool.input_schema))))) {
      throw new Error("Effective native tool metadata is missing, unknown or not the exact four tools");
    }
    report.checks.effective_tools = true;
    report.model_configuration = await call("model.getCurrent", undefined, () => session.rpc.model.getCurrent());
    if (report.model_configuration?.modelId !== (selected ? config.model : "gpt-5.6-sol-fast")
        || report.model_configuration.reasoningEffort !== (selected ? config.effort : "high")) {
      throw new Error("Native model configuration mismatch");
    }
    Object.assign(report, await observe(false));
    report.schedule_ids = report.schedules.entries.map(entry => entry.id);
    const file = report.goal_file;
    if (selected ? (!matchesProfileState(report, projection, scheduleMapping)
        || report.dependencies_match !== true
        || file?.version !== 1 || file.nextId !== projection.goal.id + 1
        || file.current?.autopilotOrigin !== "objective"
        || ["continuationCount", "turnCount", "tokenCount", "resumeCount"].some(key => file.current?.[key] !== 0)
        || file.current?.creditCountNanoAiu !== "0"
        || !Number.isFinite(Date.parse(file.current?.createdAt))
        || !Number.isFinite(Date.parse(file.current?.updatedAt))
        || !isDeepStrictEqual(
          Object.fromEntries(["id", "objective", "status"].map(key => [key, file.current?.[key]])), projection.goal))
      : (file?.version !== 1 || file.nextId !== 18
        || file.current?.id !== 17 || file.current.objective !== objective
        || file.current.status !== "completed" || file.current.autopilotOrigin !== "objective"
        || ["continuationCount", "turnCount", "tokenCount", "resumeCount"].some(key => file.current[key] !== 0)
        || file.current.creditCountNanoAiu !== "0"
        || !Number.isFinite(Date.parse(file.current.createdAt)) || !Number.isFinite(Date.parse(file.current.updatedAt))
        || !matchesFixtureState(report, file))) throw new Error("Candidate cold native fixture mismatch");
    report.checks.cold_state = true;
    report.preflight = [];
    try {
      for (const [name, path] of [
        ...(selected ? config.evidence_paths.map((path, index) => [`evidence-${index}`, path])
          : [["plan", join(config.cwd, "plan.md")]]),
        ["goal", report.goal_path],
        ["sibling", selected ? config.denied_path : join(dirname(config.cwd), "synthetic-denied-sibling.txt")],
      ]) {
        requirePath(path, "file");
        const toolCallId = `native-probe-${name}-${randomUUID()}`;
        const arguments_ = { path, ...(selected && op === "preflight" ? { forceReadLargeFiles: true } : {}) };
        const result = await call("tools.execute:view", { name: "view", arguments: arguments_, toolCallId },
          () => session.rpc.tools.execute({ name: "view", arguments: arguments_, toolCallId }));
        report.preflight.push({ name, path, tool_call_id: toolCallId, result });
      }
    } catch (error) {
      fail(error);
      throw error;
    } finally {
      try { report.prefix_delta = await readEvents(tail.cursor); } catch (error) { fail(error); }
      try { report.prefix_after = await readEvents(); } catch (error) { fail(error); }
    }
    if (report.error) throw new Error("Premodel inspection failed");
    if (!isDeepStrictEqual(conversational(report.prefix_before), conversational(report.prefix_after))
        || conversational(report.prefix_delta).length
        || report.preflight.some(item => item.result?.newMessages?.length)) {
      throw new Error("Owner preflight added or changed imported conversation content");
    }
    report.checks.prefix_preserved = true;
    for (const item of report.preflight) {
      const requests = report.permissions.filter(entry => entry.session_id === config.session_id
        && entry.tool_call_id === item.tool_call_id && entry.request?.kind === "read");
      const expected = item.name === "sibling" ? "reject" : "approve-once";
      if ((item.name !== "plan" && requests.length === 0)
          || requests.some(entry => entry.request.path !== item.path || entry.error || entry.decision.kind !== expected)
          || (item.name === "sibling"
            ? !["denied", "rejected"].includes(item.result?.resultType)
            : item.result?.resultType !== "success")) {
        throw new Error(`Native permission traversal failed for ${item.name}; no owner bypass qualifies`);
      }
    }
    if (report.permissions.some(entry => entry.error) || report.error) throw new Error("Premodel handler or event capture failed");
    report.checks.permission_traversal = true;
    if (op === "preflight") {
      report.status = "PREFLIGHT_OBSERVED";
      return;
    }
    if (typeof session.send !== "function" || typeof session.abort !== "function") {
      throw new Error("Missing public SDK send or abort surface");
    }
    const renderedPrompt = readFileSync(report.prompt_path, "utf8");
    report.prompt_sha256 = hash(renderedPrompt);
    report.timeout_ms = Math.max(0, Math.floor(Math.min(report.max_timeout_ms, 330000 - (performance.now() - started))));
    if (!report.timeout_ms) throw new Error("Owned helper budget exhausted before model dispatch");
    const buffered = [];
    let messageId;
    let matchingMessage;
    let active = true;
    let resolveOutcome;
    const outcome = new Promise(resolve => { resolveOutcome = resolve; });
    const consume = event => {
      if (!active || event.agentId || event.data?.parentToolCallId) return;
      if (event.type === "session.error") {
        resolveOutcome({ error: new Error(event.data?.message ?? "Native root session error") });
      } else if (event.type === "session.idle" && event.data?.aborted === true) {
        resolveOutcome({ error: new Error("Native session idle was aborted") });
      } else if (messageId === undefined) {
        buffered.push(event);
      } else if (event.type === "assistant.message") {
        matchingMessage = event.data?.originatingMessageId === messageId
          && typeof event.id === "string" && typeof event.data.content === "string"
          && (event.data.toolRequests === undefined
            || (Array.isArray(event.data.toolRequests) && event.data.toolRequests.length === 0))
          ? event : undefined;
      } else if (event.type === "session.idle") {
        resolveOutcome(matchingMessage && event.data && typeof event.id === "string"
          && (event.data.aborted === undefined || event.data.aborted === false)
          ? { message: matchingMessage, idle: event }
          : { error: new Error("Native session idle lacked a matching root final response") });
      }
    };
    const stopCompletion = session.on(consume);
    report.model_started_at = new Date().toISOString();
    const modelStarted = performance.now();
    report.model_timing_source = "Owned SDK send through correlated native session.idle, not provider HTTP timing";
    let deadlineTimer;
    try {
      try {
        const deadline = new Promise(resolve => {
          deadlineTimer = setTimeout(() => resolve({
            error: new Error(`${report.timeout_ms}-millisecond SDK send/completion deadline exceeded`),
          }), report.timeout_ms);
        });
        void call("session.send", { prompt: renderedPrompt, mode: "immediate" }, () => {
          report.model_send_calls = 1;
          return session.send({ prompt: renderedPrompt, mode: "immediate" });
        }).then(id => {
          if (typeof id !== "string" || !id) throw new Error("SDK send returned no message ID");
          report.model_message_id = id;
          if (!active) return;
          messageId = id;
          for (const event of buffered) consume(event);
          buffered.length = 0;
        }).catch(error => resolveOutcome({ error }));
        const terminal = await Promise.race([outcome, deadline]);
        if (terminal.error) throw terminal.error;
        report.model_result = terminal.message;
        report.model_completion_event = terminal.idle;
      } catch (error) {
        fail(error);
        throw error;
      } finally {
        active = false;
        clearTimeout(deadlineTimer);
        try { stopCompletion(); } catch (error) { fail(error); }
        report.model_completed_at = new Date().toISOString();
        report.model_elapsed_seconds = (performance.now() - modelStarted) / 1000;
      }
      if (report.error) throw new Error("Candidate event capture failed");
      report.status = "CANDIDATE_OBSERVED";
    } catch (error) {
      fail(error);
      try { await call("session.abort", undefined, () => session.abort()); } catch (abortError) { fail(abortError); }
    }
  };
  try {
    if (isCandidate) {
      delete report.model_calls;
      report.model_send_calls = 0;
      report.max_timeout_ms = 300000;
      report.checks = {
        effective_tools: false, instruction_correspondence: false, cold_state: false,
        permission_traversal: false, prefix_preserved: false,
      };
      if (selected) report.checks.imported_prefix_correspondence = false;
      report.permissions = [];
      report.limits = [
        "Fixed synthetic SDK diagnostic only; native mediation and full caller behavior require Actions proof",
        "One SDK send may produce multiple provider HTTP calls; billing and unobserved requests remain unknown",
        "No fabricated CLI results, transcript repair, custom tools or permission bypass",
        "Public send/native idle correlation and full caller completion require Actions proof",
        "Model deadline uses the remaining 330-second owner budget, capped at 300 seconds, reserving 30 seconds under the 360-second helper watchdog",
      ];
    }
    validateOutput(config);
    receipt = openSync(config.output, "wx", 0o600);
    report.goal_path = validateConfig(op, config);
    if (selected) {
      projection = profileState(config);
      report.profile = config.profile;
      report.provenance = projection.provenance;
      report.source_projection = projection;
      report.limits = [
        "Source projection only; unseen rows, descriptions, dependencies, counters and deadlines are not attested",
        ...projection.unknowns,
        "Schedule IDs are explicitly mapped by fresh public creation; deadlines are re-armed",
        "No owner preflight operation is candidate behavior",
      ];
      report.modern_defaults.nextId = projection.goal.id + 1;
      report.modern_defaults.timestamps = "Execution setup timestamps, not original source facts";
      if (op !== "setup") {
        const mappingPath = join(config.home, "session-state", config.session_id, "native-profile-mapping.json");
        requirePath(mappingPath, "file");
        scheduleMapping = JSON.parse(readFileSync(mappingPath, "utf8"));
        report.schedule_mapping = scheduleMapping;
      }
    }
    report.cli = config.cli;
    report.sdk = config.sdk;
    report.connection = { path: config.cli, args: [], useLoggedInUser: false };
    if (isCandidate) {
      const runRoot = dirname(config.cwd);
      report.prompt_path = selected ? config.prompt_path : join(runRoot, "candidate-prompt.md");
      report.event_log = selected ? config.event_log : join(runRoot, "candidate-raw.jsonl");
      report.plugin_path = selected ? config.plugin_path : join(runRoot, "pinned-plugin");
      requirePath(report.prompt_path, "file");
      requirePath(report.plugin_path, "directory");
      if (within(config.output, config.cwd)) throw new Error("Candidate receipt must remain outside evidence");
      eventFile = openSync(report.event_log, "wx", 0o600);
      const permissionHandler = candidatePermissionHandler(config, report.goal_path, report.plugin_path, report.permissions);
      candidateOptions = {
        ...options, model: selected ? config.model : "gpt-5.6-sol-fast",
        reasoningEffort: selected ? config.effort : "high",
        availableTools: ["skill", "view", "sql", "manage_schedule"],
        pluginDirectories: [report.plugin_path], disabledMcpServers: ["github-mcp-server", "playwright"],
        skipCustomInstructions: false, instructionDirectories: [], organizationCustomInstructions: "",
        onPermissionRequest(request, invocation) {
          const decision = permissionHandler(request, invocation);
          const error = report.permissions.at(-1)?.error;
          if (error) fail(error);
          return decision;
        },
      };
      report.connection.mode = "copilot-cli";
      report.connection.workingDirectory = config.cwd;
      report.connection.baseDirectory = config.home;
    }
    sdk = await import(pathToFileURL(config.sdk).href);
    await connect();
    if (isCandidate) {
      await candidate();
    } else if (op === "setup") {
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
        version: 1, nextId: selected ? projection.goal.id + 1 : 18,
        current: {
          ...(selected ? projection.goal : { id: 17, objective, status: "completed" }),
          autopilotOrigin: "objective",
          continuationCount: 0, turnCount: 0, tokenCount: 0,
          creditCountNanoAiu: "0", resumeCount: 0, createdAt: now, updatedAt: now,
        },
      };
      report.modern_defaults.createdAt = now;
      report.modern_defaults.updatedAt = now;
      if (selected) {
        // This checkpoint owns partial setup only after the namespace was proved empty.
        writeFileSync(join(config.home, "session-state", config.session_id, "native-profile-mapping.json"),
          "[]", { flag: "wx", mode: 0o600 });
      }
      mutated = true;
      await call("workspaces.writeAutopilotObjective", { content: JSON.stringify(expectedFile, null, 2) + "\n" },
        () => session.rpc.workspaces.writeAutopilotObjective({
          content: JSON.stringify(expectedFile, null, 2) + "\n",
        }));
      const mode = selected ? projection.mode : "autopilot";
      await call("mode.set", { mode }, () => session.rpc.mode.set({ mode }));
      if (selected) {
        for (const row of projection.todos) await execute("sql", {
          description: "Insert owned source projection row",
          query: `INSERT INTO todos (id,title,description,status) VALUES (${[
            row.id, row.title, row.description, row.status,
          ].map(quoteSql).join(",")})`,
        });
        for (const dep of projection.dependencies) await execute("sql", {
          description: "Insert owned source projection dependency",
          query: `INSERT INTO todo_deps (todo_id,depends_on) VALUES (${[
            dep.todo_id, dep.depends_on,
          ].map(quoteSql).join(",")})`,
        });
        scheduleMapping = [];
        for (const entry of projection.schedules) {
          const before = await call("schedule.list", undefined, () => session.rpc.schedule.list());
          await execute("manage_schedule", { action: "create", interval: entry.interval, prompt: entry.prompt });
          const after = await call("schedule.list", undefined, () => session.rpc.schedule.list());
          const added = after.entries.filter(item => !before.entries.some(old => old.id === item.id));
          if (added.length !== 1 || !Number.isInteger(added[0].id) || added[0].id < 1
              || added[0].prompt !== entry.prompt || added[0].intervalMs !== intervalMs(entry.interval)
              || added[0].recurring !== true) throw new Error("Native schedule creation mapping mismatch");
          scheduleMapping.push({ source_id: entry.id, native_id: added[0].id });
          if (entry.status === "stopped") await call("schedule.stop", { id: added[0].id },
            () => session.rpc.schedule.stop({ id: added[0].id }));
        }
        report.schedule_mapping = scheduleMapping;
        writeFileSync(join(config.home, "session-state", config.session_id, "native-profile-mapping.json"),
          JSON.stringify(scheduleMapping), { mode: 0o600 });
      } else {
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
      }
      await stop();
      if (report.error) throw new Error("Warm producer shutdown failed");
      await connect();
      Object.assign(report, await observe());
      if (selected ? (!matchesProfileState(report, projection, scheduleMapping)
        || report.dependencies_match !== true || !isDeepStrictEqual(report.goal_file, expectedFile))
        : !matchesFixtureState(report, expectedFile)) throw new Error("Cold native checkpoint mismatch");
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
      ownerDeadline = performance.now() + 20000;
      try {
        await connect();
        report.cleanup = await cleanup();
      } catch (error) {
        report.cleanup_error = errorInfo(error);
      } finally {
        try { await stop(); } catch (error) { fail(error); }
      }
    }
    if (isCandidate) {
      if (report.error) report.status = report.model_send_calls ? "FAILED" : "PREMODEL_BLOCKED";
      const usage = candidateEvents.filter(event => event.type === "assistant.usage");
      report.observed_usage_events = usage.length;
      report.observed_api_call_ids = [...new Set(usage.map(event => event.data?.apiCallId).filter(Boolean))];
      report.observed_model_calls = null;
      try { unsubscribe?.(); } catch (error) { fail(error); }
      try { if (eventFile !== undefined) closeSync(eventFile); } catch (error) { fail(error); }
      if (report.error) report.status = report.model_send_calls ? "FAILED" : "PREMODEL_BLOCKED";
      report.firsterror = report.error?.message ?? null;
    } else if (report.error) report.status = "ERROR";
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
