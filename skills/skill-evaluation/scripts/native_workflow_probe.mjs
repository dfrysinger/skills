import {
  accessSync, closeSync, constants, lstatSync, openSync,
  readFileSync, writeFileSync,
} from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { userInfo } from "node:os";
import { execFileSync } from "node:child_process";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";

const fields = ["cli", "sdk", "home", "os_home", "cwd", "session_id", "output"];
const phaseFields = [...fields, "profile", "state_file", "prompt_path", "event_log",
  "plugin_path", "evidence_paths", "denied_path", "model", "effort", "prefix_file"];
const contextFields = [...fields, "profile", "prompt_path", "event_log", "plugin_path",
  "model", "effort", "prefix_file", "context_fixture_file"];
const historicalProfile = config => config?.profile === "native-historical-context";
const continuationProfile = config => historicalProfile(config) && Object.hasOwn(config, "continuation_file");
const contextProfile = config => historicalProfile(config) || config?.profile === "native-context-calibration";
const conversational = events => events.filter(event =>
  /^(user\.message|assistant\.message|tool\.result|tool\.execution_complete)$/.test(event.type));
const objective = "Synthetic native workflow diagnostic. Not a historical task.";
const prompt = "Synthetic native workflow diagnostic only.";
const rowId = "native-workflow-fixture";
const hash = content => createHash("sha256").update(content).digest("hex");
const options = {
  continuePendingWork: false,
  suppressResumeEvent: true,
  allowTranscriptRecovery: false,
  availableTools: ["sql", "manage_schedule"],
  manageScheduleEnabled: true,
};

export const editableFixtureCheck = `from pathlib import Path

if Path(__file__).with_name("target.txt").read_bytes() != b"ready\\n":
    print("invalid fixture data")
    raise SystemExit(1)
print("PASS fixture data")
`;

function permissionProfile(config) {
  if (!Object.hasOwn(config, "candidate_permissions")) return { write_paths: [], shell_commands: [] };
  execFileSync("python3", ["-I", "-c",
    "import json,sys; sys.path.insert(0,sys.argv[1]); from session_restore import permission_rules; permission_rules(json.load(sys.stdin))",
    dirname(fileURLToPath(import.meta.url))], {
    input: JSON.stringify(config.candidate_permissions), env: { PATH: process.env.PATH },
    stdio: ["pipe", "pipe", "pipe"],
  });
  return config.candidate_permissions;
}

function candidateTools(config) {
  if (historicalProfile(config)) return contextFixture(config).required_tools;
  return ["skill", "view", "sql", "manage_schedule",
    ...(config.candidate_permissions?.write_paths.length ? ["apply_patch"] : []),
    ...(config.candidate_permissions?.shell_commands.length ? ["bash"] : [])];
}

function requirePath(path, kind, allowMissingFile = false) {
  if (typeof path !== "string" || !isAbsolute(path) || resolve(path) !== path) {
    throw new Error("Expected an absolute normalized path");
  }
  if (kind === "file" && allowMissingFile && !pathExists(path)) {
    requirePath(dirname(path), "directory");
    return;
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

function contextFixture(config) {
  const path = config.context_fixture_file;
  requirePath(path, "file");
  const stat = lstatSync(path);
  if ((stat.mode & 0o077) || stat.uid !== userInfo().uid || stat.nlink !== 1
      || within(path, config.cwd) || within(path, config.home) || within(path, config.plugin_path)) {
    throw new Error("Context locator must be owner-only outside candidate roots");
  }
  const fixture = parseDataJson(readFileSync(path, "utf8"));
  if (historicalProfile(config)) {
    if (fixture?.schema_version === 3) {
      const keys = ["schema_version", "canonical_file", "canonical_sha256", "source_binding",
        "trigger_file", "trigger_sha256", "root_skills", "correspondence", "excluded_fields",
        "snapshot", "required_tools", "limitations"];
      const completed = Object.hasOwn(fixture, "completed_objective");
      const active = Object.hasOwn(fixture, "active_objective");
      const autopilot = Object.hasOwn(fixture, "recorded_autopilot_request");
      if (completed) keys.push("completed_objective");
      if (active) keys.push("active_objective");
      if (autopilot) keys.push("recorded_autopilot_request");
      if (!isDeepStrictEqual(Object.keys(fixture).sort(), keys.sort())
          || active !== autopilot || (active && completed)
          || [active && fixture.active_objective, autopilot && fixture.recorded_autopilot_request]
            .filter(value => value !== false).some(value => !value
              || !isDeepStrictEqual(Object.keys(value).sort(), ["path", "sha256"])
              || !/^[0-9a-f]{64}$/.test(value.sha256)
              || [config.home, config.os_home, config.cwd, config.plugin_path]
                .some(root => within(value.path, root)))
          || (completed && (!fixture.completed_objective
            || !isDeepStrictEqual(Object.keys(fixture.completed_objective).sort(), ["path", "sha256"])
            || !/^[0-9a-f]{64}$/.test(fixture.completed_objective.sha256)
            || [config.home, config.os_home, config.cwd, config.plugin_path]
              .some(root => within(fixture.completed_objective.path, root))))
          || !/^[0-9a-f]{64}$/.test(fixture.canonical_sha256)
          || !/^[0-9a-f]{64}$/.test(fixture.trigger_sha256)
          || !Array.isArray(fixture.root_skills) || !Array.isArray(fixture.correspondence)
          || !Array.isArray(fixture.excluded_fields)
          || !Array.isArray(fixture.required_tools) || !fixture.required_tools.length
          || fixture.required_tools.some(name => typeof name !== "string" || !name.trim())
          || new Set(fixture.required_tools).size !== fixture.required_tools.length
          || !Array.isArray(fixture.limitations) || !fixture.limitations.length
          || new Set(fixture.correspondence.map(item => item.native_event_id)).size !== fixture.correspondence.length) {
        throw new Error("Invalid recorded context locator");
      }
      for (const [path, expected] of [
        [fixture.canonical_file, fixture.canonical_sha256], [fixture.trigger_file, fixture.trigger_sha256],
        ...(completed ? [[fixture.completed_objective.path, fixture.completed_objective.sha256]] : []),
        ...(active ? [[fixture.active_objective.path, fixture.active_objective.sha256],
          [fixture.recorded_autopilot_request.path, fixture.recorded_autopilot_request.sha256]] : []),
      ]) {
        requirePath(path, "file");
        const stat = lstatSync(path);
        if (stat.uid !== userInfo().uid || stat.nlink !== 1 || (stat.mode & 0o077)
            || !within(path, dirname(config.context_fixture_file))
            || createHash("sha256").update(readFileSync(path)).digest("hex") !== expected) {
          throw new Error("Recorded context/trigger owner artifact differs");
        }
      }
      const canonical = parseDataJson(readFileSync(fixture.canonical_file, "utf8"));
      const deferred = parseDataJson(readFileSync(fixture.trigger_file, "utf8"));
      const completedStore = completed
        ? parseDataJson(readFileSync(fixture.completed_objective.path, "utf8")) : null;
      const activeStore = active ? parseDataJson(readFileSync(fixture.active_objective.path, "utf8")) : null;
      const recordedRequest = autopilot
        ? parseDataJson(readFileSync(fixture.recorded_autopilot_request.path, "utf8")) : null;
      const ownerRoot = dirname(config.context_fixture_file);
      if (typeof deferred.source_event_path !== "string" || !deferred.source_event_path
          || isAbsolute(deferred.source_event_path)
          || !within(resolve(ownerRoot, deferred.source_event_path), ownerRoot)
          || relative(ownerRoot, resolve(ownerRoot, deferred.source_event_path)) !== deferred.source_event_path) {
        throw new Error("Invalid recorded trigger source event path");
      }
      const sourcePath = resolve(ownerRoot, deferred.source_event_path);
      requirePath(sourcePath, "file");
      const sourceStat = lstatSync(sourcePath);
      const sourceBytes = readFileSync(sourcePath);
      if (!within(sourcePath, ownerRoot) || sourceStat.uid !== userInfo().uid
          || sourceStat.nlink !== 1 || (sourceStat.mode & 0o077)
          || !/^[0-9a-f]{64}$/.test(deferred.source_line_sha256)
          || createHash("sha256").update(sourceBytes).digest("hex") !== deferred.source_line_sha256) {
        throw new Error("Recorded trigger source event owner artifact differs");
      }
      const sourceEvent = parseDataJson(sourceBytes.toString("utf8"));
      if (sourceEvent?.type !== "user.message" || sourceEvent.id !== deferred.event_id
          || typeof deferred.timestamp !== "string" || !deferred.timestamp
          || sourceEvent.timestamp !== deferred.timestamp
          || typeof deferred.content !== "string" || (!autopilot && !deferred.content)
          || sourceEvent.data?.content !== deferred.content
          || typeof sourceEvent.data.content !== "string"
          || (!autopilot && (sourceEvent.agentId || sourceEvent.data.parentToolCallId
            || sourceEvent.data.source || sourceEvent.data.isAutopilotContinuation
            || sourceEvent.data.attachments?.length))
          || (Object.hasOwn(sourceEvent.data, "transformedContent")
            ? sourceEvent.data.transformedContent : sourceEvent.data.content) !== canonical.chat_messages.at(-1)?.content
          || typeof canonical.chat_messages.at(-1)?.content !== "string") {
        throw new Error("Recorded trigger source event correspondence differs");
      }
      if (fixture.source_binding?.sha256 !== fixture.canonical_sha256
          || fixture.source_binding.cutoff_offset !== canonical.source_cutoff_offset
          || fixture.source_binding.cutoff_event_id !== canonical.last_source_event
          || deferred.event_id !== canonical.last_source_event
          || deferred.canonical_index !== canonical.chat_messages.length - 1
          || !isDeepStrictEqual(deferred.recorded_message, canonical.chat_messages.at(-1))) {
        throw new Error("Recorded cutoff/trigger correspondence differs");
      }
      const compiled = JSON.parse(execFileSync("python3", ["-B", "-I", "-c",
        "import json,sys; sys.path.insert(0,sys.argv[1]); from session_restore import recorded_native_payloads,compile_task_snapshot,completed_objective_state,active_objective_state,recorded_autopilot_request; value=json.load(sys.stdin); print(json.dumps([recorded_native_payloads(value['canonical']),compile_task_snapshot(value['snapshot']),completed_objective_state(value['completed']) if 'completed' in value else None,active_objective_state(value['active']) if 'active' in value else None,recorded_autopilot_request(value['request'],value['event'],value['trigger'],value['active']) if 'active' in value else None]))",
        dirname(fileURLToPath(import.meta.url))], {
        input: JSON.stringify({ canonical, snapshot: fixture.snapshot?.source,
          ...(completed ? { completed: completedStore } : {}),
          ...(active ? { active: activeStore, request: recordedRequest, event: sourceEvent, trigger: deferred } : {}) }),
        env: { PATH: process.env.PATH },
        stdio: ["pipe", "pipe", "pipe"], maxBuffer: 16 * 1024 * 1024,
      }));
      if (!isDeepStrictEqual(compiled[1], fixture.snapshot)) throw new Error("Recorded task compilation differs");
      if (fixture.correspondence.length !== compiled[0][1].length
          || fixture.correspondence.some((binding, index) =>
            binding.collection !== compiled[0][1][index].collection
            || binding.index !== compiled[0][1][index].index
            || !isDeepStrictEqual(binding.source_field_sha256, compiled[0][1][index].source_field_sha256))
          || !isDeepStrictEqual(fixture.excluded_fields, compiled[0][2])
          || fixture.root_skills.length !== canonical.invoked_skills.length) {
        throw new Error("Recorded canonical-index correspondence differs");
      }
      return { ...fixture, canonical, recorded_payloads: compiled[0][0],
        ...(completed ? { completed_objective_store: completedStore,
          completed_objective_native_state: compiled[2] } : {}),
        ...(active ? { active_objective_store: activeStore,
          active_objective_native_state: compiled[3], autopilot_send: compiled[4],
          limitations: [...fixture.limitations,
            "Single recorded native event replay only; automatic producer leases, repeated continuations and timers are not reproduced",
            "Native runtime regenerates transport current_datetime; the recorded datetime is not sent",
            "Pinned single-send forwarding omits billable; no billing-fidelity claim, actual accounting unchanged",
          ] } : {}) };
    }
    const keys = ["schema_version", "summary_event_id", "summary_sha256", "post_event_ids",
      "root_skills", "correspondence", "tool_call_ids", "snapshot", "required_tools", "limitations"];
    if (!fixture || !isDeepStrictEqual(Object.keys(fixture).sort(), keys.sort())
        || fixture.schema_version !== 2 || !Array.isArray(fixture.root_skills)
        || fixture.root_skills.length !== 7 || !Array.isArray(fixture.correspondence)
        || !fixture.correspondence.length || !Array.isArray(fixture.post_event_ids)
        || !fixture.post_event_ids.length || !Array.isArray(fixture.required_tools)
        || !isDeepStrictEqual([...fixture.required_tools].sort(),
          ["skill", "view", "sql", "manage_schedule", "bash", "apply_patch", "rg", "task", "task_complete"].sort())
        || !Array.isArray(fixture.limitations) || !fixture.limitations.length
        || !/^[0-9a-f-]{36}$/.test(fixture.summary_event_id)
        || !/^[0-9a-f]{64}$/.test(fixture.summary_sha256)
        || new Set(fixture.root_skills.map(item => item.native_event_id)).size !== 7) {
      throw new Error("Invalid historical context locator");
    }
    const compiled = JSON.parse(execFileSync("python3", ["-I", "-c",
      "import json,sys; sys.path.insert(0,sys.argv[1]); from session_restore import compile_task_snapshot; print(json.dumps(compile_task_snapshot(json.load(sys.stdin))))",
      dirname(fileURLToPath(import.meta.url))], {
      input: JSON.stringify(fixture.snapshot?.source), env: { PATH: process.env.PATH },
      stdio: ["pipe", "pipe", "pipe"], maxBuffer: 8 * 1024 * 1024,
    }));
    if (!isDeepStrictEqual(compiled, fixture.snapshot)) throw new Error("Historical snapshot compilation differs");
    return fixture;
  }
  if (!fixture || !isDeepStrictEqual(Object.keys(fixture).sort(),
    ["schema_version", "summary_event_id", "summary_sha256", "post_event_ids"].sort())
      || fixture.schema_version !== 1 || typeof fixture.summary_event_id !== "string"
      || !/^[0-9a-f-]{36}$/.test(fixture.summary_event_id)
      || !/^[0-9a-f]{64}$/.test(fixture.summary_sha256)
      || !Array.isArray(fixture.post_event_ids) || fixture.post_event_ids.length !== 2
      || fixture.post_event_ids.some(id => typeof id !== "string" || !/^[0-9a-f-]{36}$/.test(id))
      || new Set([fixture.summary_event_id, ...fixture.post_event_ids]).size !== 3) {
    throw new Error("Invalid fixed context locator");
  }
  return fixture;
}

function objectiveReadback(path, fixture, goal) {
  const nativeReadback = arguments.length === 3;
  const key = fixture.active_objective ? "active_objective" : "completed_objective";
  const label = fixture.active_objective ? "Active" : "Completed";
  requirePath(path, "file");
  const stat = lstatSync(path);
  if (stat.uid !== userInfo().uid || stat.nlink !== 1 || (stat.mode & 0o077)) {
    throw new Error(`${label} objective destination must be owned, owner-only and single-link`);
  }
  const bytes = readFileSync(path);
  const store = parseDataJson(bytes.toString("utf8"));
  if (!isDeepStrictEqual(store, fixture[`${key}_store`])
      || (nativeReadback && !isDeepStrictEqual(goal?.state, fixture[`${key}_native_state`]))) {
    throw new Error(`${label} objective persisted/native state differs from source`);
  }
  return { store, sha256: createHash("sha256").update(bytes).digest("hex"),
    source_sha256: fixture[key].sha256, persisted_store_correspondence: true,
    ...(nativeReadback ? { native_state_correspondence: true } : {}) };
}

export function validateRecordedNativeEvents(fixture, events) {
  if (!Array.isArray(fixture.recorded_payloads)
      || fixture.correspondence.length !== fixture.recorded_payloads.length) {
    throw new Error("Recorded event correspondence population differs");
  }
  const byId = new Map(events.map(event => [event.id, event]));
  const bound = new Set(fixture.correspondence.map(binding => binding.native_event_id));
  if (events.some(event => [
    "user.message", "assistant.message", "tool.execution_complete", "instruction.update",
    "system.message", "skill.invoked",
  ].includes(event.type) && !bound.has(event.id))) {
    throw new Error("Unbound recorded context event or duplicate trigger");
  }
  let last = -1;
  for (const [index, expected] of fixture.recorded_payloads.entries()) {
    const binding = fixture.correspondence[index];
    const event = byId.get(binding.native_event_id);
    const position = events.indexOf(event);
    if (!event || position <= last || event.type !== expected.type || event.type !== binding.native_type
        || event.agentId || event.data?.parentToolCallId) {
      throw new Error("Recorded event role/order differs");
    }
    const data = { ...event.data };
    if (event.type === "assistant.message") {
      if (typeof data.messageId !== "string" || !data.messageId) throw new Error("Missing recorded native message ID");
      delete data.messageId;
    }
    if (!isDeepStrictEqual(data, expected.data)) throw new Error("Recorded native body/tool/provider fields differ");
    last = position;
  }
  return {
    native_payload_correspondence: true,
    model_visible_correspondence: "Requires actual post-resume context readback, not event equality",
    authorization_history_equivalence: false,
  };
}

export function continuationEntry(config) {
  requirePath(config.continuation_file, "file");
  return JSON.parse(execFileSync("python3", ["-B", "-I", "-c",
    "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from native_workflow import continuation_entry;print(json.dumps(continuation_entry(Path(sys.argv[2]),json.loads(sys.argv[3]))))",
    dirname(fileURLToPath(import.meta.url)), config.continuation_file, JSON.stringify(config)],
  { encoding: "utf8", env: {
    PATH: process.env.PATH ?? "",
    ...(process.env.GITHUB_WORKFLOW_SHA ? { GITHUB_WORKFLOW_SHA: process.env.GITHUB_WORKFLOW_SHA } : {}),
    ...(process.env.GITHUB_WORKSPACE ? { GITHUB_WORKSPACE: process.env.GITHUB_WORKSPACE } : {}),
  } }));
}

function operationalEntry(config) {
  requirePath(config.operational_file, "file");
  return JSON.parse(execFileSync("python3", ["-B", "-I", "-c",
    "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from native_workflow import operational_input;print(json.dumps(operational_input(Path(sys.argv[2]),json.loads(sys.argv[3]))))",
    dirname(fileURLToPath(import.meta.url)), config.operational_file, JSON.stringify(config)],
  { encoding: "utf8", env: { PATH: process.env.PATH ?? "" } }));
}

export function continuationCorrespondence(before, after, events, messageId, raw, autopilotSend) {
  if (after.length < before.length || before.some((event, index) => !isDeepStrictEqual(event, after[index]))) {
    throw new Error("Historical continuation mutated its native journal prefix");
  }
  const root = event => !event.agentId && !event.data?.parentToolCallId;
  const users = after.slice(before.length).filter(event => root(event) && event.type === "user.message");
  const data = users[0]?.data;
  const wrapper = typeof data?.transformedContent === "string"
    ? data.transformedContent.match(/^<current_datetime>([0-9T:.+Z-]+)<\/current_datetime>\n\n/) : null;
  const autopilotMatches = autopilotSend
    && isDeepStrictEqual(autopilotSend, { prompt: raw, displayPrompt: "", requiredTool: "task_complete",
      source: "autopilot", agentMode: "autopilot" })
    && data?.content === "" && data.source === "autopilot" && data.agentMode === "autopilot"
    && wrapper && Number.isFinite(Date.parse(wrapper[1]))
    && data.transformedContent.slice(wrapper[0].length) === raw;
  if (users.length !== 1 || (autopilotSend ? !autopilotMatches
    : (users[0].data?.content !== raw || users[0].data?.isAutopilotContinuation || users[0].data?.source))
      || users[0].data?.messageId !== messageId || users[0].data?.attachments?.length
      || typeof users[0].data?.interactionId !== "string" || !users[0].data.interactionId) {
    throw new Error("Historical continuation requires exactly one unsubstituted root raw user event");
  }
  const primary = events.filter(event => root(event) && event.type === "system.message"
    && event.data?.interactionId === users[0].data.interactionId);
  if (!primary.length || primary.some(event => typeof event.data?.content !== "string"
      || !event.data.content.includes("You are the GitHub Copilot CLI, a terminal assistant built by GitHub.")
      || !event.data.content.includes("You are an interactive tool that helps users with software engineering tasks.")
      || event.data.content.includes("You are running in non-interactive mode"))) {
    throw new Error("Fresh correlated primary system prompt did not verify interactive CLI identity");
  }
  return { prefix_preserved: true, exactly_once: true, interactive_identity: true,
    ...(autopilotSend ? { recorded_autopilot_request: true } : {}),
    primary_system_messages: primary, interaction_id: users[0].data.interactionId };
}

export function continuationCompletion(events, messageId) {
  let interactionId;
  let assistant;
  let task;
  for (const event of events) {
    const data = event.data;
    if (event.agentId || data?.parentToolCallId) continue;
    if (event.type === "session.error") {
      return { error: new Error(data?.message ?? "Native root session error") };
    }
    if (event.type === "user.message") {
      interactionId = data?.messageId === messageId && typeof data.interactionId === "string"
        && data.interactionId ? data.interactionId : undefined;
      assistant = task = undefined;
    } else if (event.type === "assistant.message") {
      assistant = interactionId && typeof event.id === "string" && event.id && data?.originatingMessageId === messageId
        && data.interactionId === interactionId ? event : undefined;
      const requests = Array.isArray(assistant?.data.toolRequests)
        ? assistant.data.toolRequests.filter(request =>
          request?.name === "task_complete" && typeof request.toolCallId === "string" && request.toolCallId) : [];
      task = requests?.length === 1 && typeof data.turnId === "string" && data.turnId
        ? { request: requests[0], invalid: false } : undefined;
    } else if (task && event.type === "tool.execution_start" && data?.toolCallId === task.request.toolCallId) {
      task.invalid ||= typeof event.id !== "string" || !event.id || Boolean(task.start) || data.toolName !== "task_complete"
        || data.turnId !== assistant.data.turnId
        || !isDeepStrictEqual(data.arguments, task.request.arguments);
      task.start = event;
    } else if (task && event.type === "tool.execution_complete" && data?.toolCallId === task.request.toolCallId) {
      task.invalid ||= typeof event.id !== "string" || !event.id || !task.start || Boolean(task.completion) || data.success !== true
        || data.interactionId !== interactionId || data.turnId !== assistant.data.turnId
        || typeof data.result?.content !== "string" || !data.result.content.trim();
      task.completion = event;
    } else if (task?.completion && event.type === "assistant.turn_end") {
      task.turn_end = typeof event.id === "string" && event.id && data?.turnId === assistant.data.turnId ? event : undefined;
    } else if (event.type === "session.idle") {
      if (!data || typeof event.id !== "string" || !event.id || (data.aborted !== undefined && data.aborted !== false)) {
        return { error: new Error("Native session idle was aborted or malformed") };
      }
      if (assistant && typeof assistant.data.content === "string" && assistant.data.content.trim()
          && (assistant.data.toolRequests === undefined
            || (Array.isArray(assistant.data.toolRequests) && assistant.data.toolRequests.length === 0))) {
        return { kind: "assistant_final", message: assistant, idle: event };
      }
      if (task?.completion && task.turn_end && !task.invalid) {
        return { kind: "task_complete", message: assistant,
          task_complete: { request: task.request, start: task.start,
            completion: task.completion, turn_end: task.turn_end }, idle: event };
      }
      return { error: new Error("Native session idle lacked a matching root final response") };
    }
  }
}

export function validateConfig(op, config) {
  if (!["setup", "observe", "cleanup", "candidate", "preflight"].includes(op)) throw new Error("Unknown operation");
  if (continuationProfile(config) && !["candidate", "observe", "cleanup"].includes(op)) {
    throw new Error("Continuation cannot replace source setup or zero-send preflight");
  }
  const selected = config?.profile !== undefined;
  const keys = contextProfile(config) ? [...contextFields,
    ...(historicalProfile(config) ? ["candidate_permissions",
      ...(Object.hasOwn(config, "skill_directories") ? ["skill_directories"] : []),
      ...(Object.hasOwn(config, "operational_file") ? ["operational_file"] : []),
      ...(continuationProfile(config) ? ["continuation_file"] : [])] : [])] : selected ? [
    ...phaseFields, ...(Object.hasOwn(config, "candidate_permissions") ? ["candidate_permissions"] : []),
  ] : fields;
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
  if ((!contextProfile(config) && op !== "setup" && op !== "cleanup") || pathExists(goalPath)) requirePath(goalPath, "file");
  if (op === "setup" && pathExists(goalPath) && !contextProfile(config)) {
    throw new Error("Setup requires an absent native goal");
  }
  validateOutput(config);
  if (contextProfile(config)) {
    if (historicalProfile(config)) {
      if (op === "candidate" && !continuationProfile(config)) throw new Error("Historical setup forbids model sends");
      if (!continuationProfile(config)) permissionProfile(config);
    }
    const fixture = contextFixture(config);
    if (Object.hasOwn(config, "operational_file") && fixture.schema_version !== 3) {
      throw new Error("Operational input requires recorded schema3 input");
    }
    if (continuationProfile(config) && fixture.schema_version !== 3) {
      throw new Error("Continuation requires recorded schema3 input");
    }
    if (fixture.schema_version === 3 && (fixture.completed_objective || fixture.active_objective)
        && !(continuationProfile(config) && ["observe", "cleanup"].includes(op))) {
      objectiveReadback(goalPath, fixture);
    } else if (pathExists(goalPath) && !(continuationProfile(config) && ["observe", "cleanup"].includes(op))) {
      throw new Error(op === "setup" ? "Setup requires an absent native goal"
        : "Context calibration requires an absent native goal");
    }
    const roots = [config.home, config.os_home, config.cwd, config.plugin_path];
    requirePath(config.plugin_path, "directory");
    if (Object.hasOwn(config, "skill_directories")) {
      if (!Array.isArray(config.skill_directories) || config.skill_directories.length !== 1
          || config.skill_directories[0] !== join(dirname(config.cwd),
            config.operational_file ? "pinned-custom-skills" : "pinned-personal-skills")) {
        throw new Error("Expected the single owned personal skill discovery root");
      }
      requirePath(config.skill_directories[0], "directory");
      if (lstatSync(config.skill_directories[0]).uid !== userInfo().uid) {
        throw new Error("Personal skill discovery root must be owned");
      }
      roots.push(config.skill_directories[0]);
    }
    if (config.operational_file) {
      roots.push(...operationalEntry(config).installed_plugins.slice(1).map(item => item.path));
    }
    if (roots.some((root, i) => roots.some((other, j) => i !== j && within(root, other)))) {
      throw new Error("Context roots must be disjoint");
    }
    for (const key of ["prefix_file", "prompt_path"]) {
      requirePath(config[key], "file");
      const stat = lstatSync(config[key]);
      if ((stat.mode & 0o077) || stat.uid !== userInfo().uid || stat.nlink !== 1
          || roots.some(root => within(config[key], root))) {
        throw new Error("Context inputs must be owner-only outside candidate roots");
      }
    }
    for (const key of ["event_log", "output"]) {
      if (typeof config[key] !== "string" || !isAbsolute(config[key]) || resolve(config[key]) !== config[key]
          || roots.some(root => within(config[key], root))) throw new Error("Invalid context output path");
      requirePath(dirname(config[key]), "directory");
    }
    if (new Set(["prefix_file", "prompt_path", "context_fixture_file", "event_log", "output"]
      .map(key => config[key])).size !== 5 || typeof config.model !== "string" || !config.model.trim()
        || !["low", "medium", "high"].includes(config.effort)) throw new Error("Invalid context coordinates/model");
    return goalPath;
  }
  if (selected) {
    permissionProfile(config);
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
          requirePath(path, "file", op === "observe" || op === "cleanup");
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
  const permissions = permissionProfile(config);
  const writes = new Set(permissions.write_paths.map(path => resolve(config.cwd, path)));
  const targetPath = value => {
    if (typeof value !== "string" || !value) return null;
    const path = resolve(config.cwd, value);
    if (!within(path, config.cwd) || value !== (isAbsolute(value) ? path : relative(config.cwd, path))) return null;
    if (pathExists(path)) {
      requirePath(path, "file");
      const info = lstatSync(path);
      if (info.nlink !== 1 || info.uid !== userInfo().uid) return null;
    } else requirePath(dirname(path), "directory");
    return path;
  };
  return (request, invocation) => {
    const entry = { session_id: invocation?.sessionId, tool_call_id: request?.toolCallId, invocation, request };
    const decision = { kind: "reject" };
    try {
      if (invocation?.sessionId !== config.session_id || !request
          || typeof request.toolCallId !== "string" || !request.toolCallId
          || ["managedApprovalRequired", "requestSandboxBypass", "requestSandboxPermissive", "skipPermission"].some(key =>
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
      } else if (request.kind === "write" && writes.size) {
        if (Object.keys(request).some(key => ![
          "kind", "fileName", "diff", "intention", "canOfferSessionApproval", "fileEdits",
          "newFileContents", "resolvedPath", "toolCallId", "managedApprovalRequired",
          "requestSandboxBypass", "requestSandboxBypassReason", "sandboxPathGrant",
        ].includes(key)) || typeof request.diff !== "string" || typeof request.intention !== "string"
            || typeof request.canOfferSessionApproval !== "boolean"
            || (request.newFileContents !== undefined && typeof request.newFileContents !== "string")
            || (request.requestSandboxBypassReason !== undefined && typeof request.requestSandboxBypassReason !== "string")) return decision;
        const path = targetPath(request.fileName);
        if (!path || !writes.has(path) || (request.resolvedPath !== undefined && request.resolvedPath !== path)) return decision;
        if (request.fileEdits !== undefined && (!Array.isArray(request.fileEdits) || !request.fileEdits.length
            || request.fileEdits.some(edit => !edit || typeof edit !== "object" || Array.isArray(edit)
              || !Object.keys(edit).length || Object.keys(edit).some(key => !["before", "after"].includes(key))
              || Object.values(edit).some(side => !side || typeof side !== "object" || Array.isArray(side)
                || Object.keys(side).length !== 2 || typeof side.content !== "string"
                || typeof side.path !== "string" || !isAbsolute(side.path) || targetPath(side.path) !== path)))) return decision;
        decision.kind = "approve-once";
      } else if (request.kind === "shell" && permissions.shell_commands.length) {
        if (Object.keys(request).some(key => ![
          "kind", "intention", "commands", "commandSegments", "fullCommandText", "shellType", "canOfferSessionApproval",
          "hasWriteFileRedirection", "possiblePaths", "possibleUrls", "resolvedPaths", "resolvedWorkingDirectory",
          "managedApprovalRequired", "requestSandboxBypass", "requestSandboxBypassReason",
          "requestSandboxPermissive", "sandboxPathGrant", "toolCallId", "warning",
        ].includes(key)) || !permissions.shell_commands.includes(request.fullCommandText)
            || (request.shellType !== undefined && request.shellType !== "bash")
            || typeof request.intention !== "string" || typeof request.canOfferSessionApproval !== "boolean"
            || request.hasWriteFileRedirection !== false
            || !Array.isArray(request.commands) || !request.commands.length
            || request.commands.some(command => !command || Object.keys(command).length !== 2
              || typeof command.identifier !== "string" || !command.identifier || typeof command.readOnly !== "boolean")
            || !Array.isArray(request.possiblePaths) || request.possiblePaths.some(path => !targetPath(path))
            || !Array.isArray(request.possibleUrls) || request.possibleUrls.length
            || (request.resolvedWorkingDirectory !== undefined && request.resolvedWorkingDirectory !== config.cwd)
            || ["warning", "requestSandboxBypassReason"].some(key =>
              request[key] !== undefined && typeof request[key] !== "string")
            || (request.commandSegments !== undefined && (!Array.isArray(request.commandSegments)
              || !request.commandSegments.length || request.commandSegments.some(segment => !segment
                || Object.keys(segment).length !== 2 || typeof segment.fullCommandText !== "string"
                || typeof segment.identifier !== "string")))
            || (request.resolvedPaths !== undefined && (!request.resolvedPaths
              || typeof request.resolvedPaths !== "object" || Array.isArray(request.resolvedPaths)
              || Object.entries(request.resolvedPaths).some(([path, resolved]) =>
                !request.possiblePaths.includes(path) || targetPath(path) !== resolved)))) return decision;
        decision.kind = "approve-once";
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
  const continuation = continuationProfile(config);
  const historicalZeroSend = historicalProfile(config) && (op !== "candidate" || continuation);
  let entry;
  let operational;
  let operationalHashes;
  let resumedAt;
  let pendingOutcome;
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
          ...(historicalProfile(config) && contextFixture(config).schema_version === 3
            ? { COPILOT_STRIP_REASONING_ON_RESUME: "false" } : {}),
          ...(continuation ? {
            PATH: entry.executable_path, LANG: entry.locale, LC_ALL: entry.locale,
            ...(Object.hasOwn(entry, "skill_char_budget")
              ? { SKILL_CHAR_BUDGET: String(entry.skill_char_budget) } : {}),
            ...(process.env.COPILOT_GITHUB_TOKEN
              ? { COPILOT_GITHUB_TOKEN: process.env.COPILOT_GITHUB_TOKEN } : {}),
          } : {}),
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
    resumedAt = Date.now();
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
    if (operational) {
      const updated = await call("options.update:installedPlugins",
        { installedPlugins: operational.native_installed_plugins },
        () => session.rpc.options.update({ installedPlugins: operational.native_installed_plugins }));
      if (updated?.success !== true) throw new Error("Native installed-plugin configuration failed");
      await call("skills.reload:installedPlugins", undefined, () => session.rpc.skills.reload());
    }
    await call("tools.initializeAndValidate", undefined,
      () => session.rpc.tools.initializeAndValidate());
  };
  const checkSchedules = schedules => {
    if (!Array.isArray(schedules?.entries)) throw new Error("Unknown native scheduler reader");
    if (!operational) return schedules.entries.length === 0;
    const definitions = schedules.entries.map(entry => {
      const next = Date.parse(entry.nextRunAt);
      if (entry.cron != null || entry.tz != null || entry.at != null || entry.selfPaced
          || !Number.isFinite(next) || next <= Date.now() + 390000
          || next < resumedAt + entry.intervalMs - 1000
          || next > Date.now() + entry.intervalMs + 1000) {
        throw new Error("Source interval clock is unsafe for the bounded owning phase");
      }
      return Object.fromEntries(["id", "intervalMs", "prompt", "recurring"].map(key => [key, entry[key]]));
    }).sort((a, b) => a.id - b.id);
    return isDeepStrictEqual(definitions, operational.expected_schedules);
  };
  const zeroRows = async (query, description) => {
    const result = await execute("sql", { query, description });
    if (result.toolTelemetry?.metrics?.rowsReturned !== 0) {
      throw new Error(`${description}: mismatch or unavailable SQL row telemetry`);
    }
    return result;
  };
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
  const historicalSchema = async (snapshot, includeSourceTables) => {
    const tables = includeSourceTables ? Object.keys(snapshot.schemas) : ["todos", "todo_deps"];
    const normalize = value => value.toLowerCase().replace(/\s+/g, "");
    for (const table of tables) {
      await zeroRows(`SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name=${quoteSql(table)} AND lower(replace(replace(replace(replace(sql,' ',''),char(10),''),char(13),''),char(9),''))=${quoteSql(normalize(snapshot.schemas[table]))})`,
        `Verify source ${table} schema including keys and constraints`);
    }
    await zeroRows("SELECT 1 FROM pragma_foreign_keys WHERE foreign_keys <> 1",
      "Verify native foreign key enforcement");
  };
  const installHistoricalSnapshot = async () => {
    const fixture = contextFixture(config);
    const before = {
      goal: await call("autopilotObjective.getState", undefined, () => session.rpc.autopilotObjective.getState()),
      todos: await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos()),
      schedules: await call("schedule.list", undefined, () => session.rpc.schedule.list()),
    };
    report.before = before;
    if (fixture.completed_objective || fixture.active_objective) {
      before[fixture.active_objective ? "active_objective" : "completed_objective"]
        = objectiveReadback(report.goal_path, fixture, before.goal);
    }
    if ((!fixture.completed_objective && !fixture.active_objective && before.goal?.state !== null)
        || !Array.isArray(before.todos?.rows) || before.todos.rows.length
        || !checkSchedules(before.schedules)) {
      throw new Error("Historical snapshot requires an empty goal-free dormant namespace");
    }
    await historicalSchema(fixture.snapshot, false);
    await zeroRows("SELECT * FROM todo_deps", "Verify empty native dependencies");
    const customTables = Object.keys(fixture.snapshot.schemas).filter(table => !["todos", "todo_deps"].includes(table));
    for (const table of customTables) {
      await zeroRows(`SELECT name FROM sqlite_master WHERE name=${quoteSql(table)}`,
        `Verify absent source ${table} table`);
    }
    for (const table of customTables) {
      await execute("sql", { description: `Create source ${table} schema`,
        query: fixture.snapshot.source.schemas[table] });
    }
    await historicalSchema(fixture.snapshot, true);
    await execute("sql", { description: "Install explicit source task snapshot",
      query: fixture.snapshot.transaction });
    await call("mode.set", { mode: "autopilot" }, () => session.rpc.mode.set({ mode: "autopilot" }));
  };
  const observeHistorical = async () => {
    const fixture = contextFixture(config);
    const state = {
      goal: await call("autopilotObjective.getState", undefined, () => session.rpc.autopilotObjective.getState()),
      mode: await call("mode.get", undefined, () => session.rpc.mode.get()),
      todos: await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos()),
      schedules: await call("schedule.list", undefined, () => session.rpc.schedule.list()),
      context: {}, snapshot_checks: [], source_query_readbacks: [],
    };
    if (fixture.completed_objective || fixture.active_objective) {
      state[fixture.active_objective ? "active_objective" : "completed_objective"]
        = objectiveReadback(report.goal_path, fixture, state.goal);
    }
    if ((!fixture.completed_objective && !fixture.active_objective
        && (pathExists(report.goal_path) || state.goal?.state !== null))
        || state.mode !== "autopilot"
        || !Array.isArray(state.todos?.rows) || state.todos.rows.length !== fixture.snapshot.row_counts.todos
        || !checkSchedules(state.schedules)) {
      throw new Error("Historical mode/task/goal/scheduler readback differs");
    }
    await historicalSchema(fixture.snapshot, true);
    for (const query of fixture.snapshot.comparisons) {
      state.snapshot_checks.push(await zeroRows(query, "Compare explicit source rows and insertion order"));
    }
    await zeroRows("PRAGMA foreign_key_check", "Verify native snapshot foreign keys");
    for (const query of fixture.snapshot.queries) {
      const result = await execute("sql", { description: "Read exact source task query", query: query.query });
      state.source_query_readbacks.push(result);
      if (result.textResultForLlm !== query.expected_text
          || result.toolTelemetry?.metrics?.rowsReturned !== query.expected_rows) {
        throw new Error("Exact source task query content/row count differs");
      }
    }
    state.events = await call("session.getEvents", undefined, () => session.getEvents());
    const prefix = parseDataJson(readFileSync(config.prefix_file, "utf8"));
    const ids = new Set(prefix.map(event => event.id));
    const observed = state.events.filter(event => ids.has(event.id));
    if (!isDeepStrictEqual(observed, prefix)) throw new Error("Historical native root projection changed");
    if (operational) {
      const scheduleIds = new Set(operational.events.map(event => event.id));
      const originalEvents = state.events.filter(event => scheduleIds.has(event.id))
        .map(({ parentId, ...source }) => source);
      if (!isDeepStrictEqual(originalEvents, operational.events)
          || state.events.some(event => !ids.has(event.id)
            && /^(user|assistant)\./.test(event.type))) {
        throw new Error("Source schedule journal changed or an unrequested turn was delivered");
      }
      state.operational = { schedule_events_preserved: true, no_scheduled_turn: true,
        registration: "Selected installed transport metadata; not recovered registration",
        clock: "Current-time interval reset; nextId not exposed by schedule.list" };
    }
    const recorded = fixture.schema_version === 3;
    if (recorded) {
      state.recorded_context = validateRecordedNativeEvents(fixture, state.events);
      state.permission_mode = await call("permissions.getMode", {}, () => session.rpc.permissions.getMode({}));
      if (!["manual", "assisted"].includes(state.permission_mode?.mode)) {
        throw new Error("Recorded checked-policy proof requires a non-allow-all permission mode");
      }
      state.recorded_context.assisted_auto_approval = state.permission_mode.mode === "assisted";
      state.recorded_context.authority_evidence_required = state.recorded_context.assisted_auto_approval;
    } else {
      const summaryIndex = prefix.findIndex(event => event.id === fixture.summary_event_id);
      const summary = prefix[summaryIndex];
      if (summary?.type !== "session.compaction_complete" || summary.data?.success !== true
        || createHash("sha256").update(summary.data.summaryContent).digest("hex") !== fixture.summary_sha256
        || fixture.root_skills.slice(0, 6).some(item =>
          prefix.findIndex(event => event.id === item.native_event_id) >= summaryIndex)
        || prefix.findIndex(event => event.id === fixture.root_skills[6].native_event_id) <= summaryIndex) {
        throw new Error("Historical summary/root skill role/order differs");
      }
    }
    const checkInvoked = async label => {
      const invoked = await call(`skills.getInvoked:${label}`, undefined, () => session.rpc.skills.getInvoked());
      if (!Array.isArray(invoked?.skills) || invoked.skills.length !== (recorded ? fixture.root_skills.length : 7)
          || invoked.skills.some((skill, index) => {
            const expected = fixture.root_skills[index];
            return (recorded && !isDeepStrictEqual(skill, fixture.canonical.invoked_skills[index]))
              || skill.name !== expected.name || skill.path !== expected.native_path
              || typeof skill.content !== "string"
              || createHash("sha256").update(skill.content).digest("hex") !== expected.body_sha256;
          })) throw new Error("Historical loaded root skill body/order differs or reader shape is unsupported");
      return invoked;
    };
    state.invoked_before_reload = await checkInvoked("before-reload");
    state.ensure_loaded = await call("skills.ensureLoaded", undefined, () => session.rpc.skills.ensureLoaded());
    state.catalog = await call("skills.list", undefined, () => session.rpc.skills.list());
    if (!Array.isArray(state.catalog?.skills) || (recorded
      ? state.catalog.skills.some(skill => !skill || typeof skill.name !== "string" || !skill.name)
      : fixture.root_skills.some(expected =>
        !state.catalog.skills.some(skill => skill.name === expected.name)))) {
      throw new Error("Historical staged skill catalog is not visible");
    }
    if (recorded) {
      state.recorded_context.retained_names_not_currently_discovered = fixture.root_skills
        .filter(expected => !state.catalog.skills.some(skill => skill.name === expected.name))
        .map(expected => expected.name);
      state.recorded_context.full_available_collection_equivalence = false;
      state.recorded_context.behavioral_baseline_ready = false;
      state.recorded_context.discovery_limitations = [
        "Current discovery does not establish capture-time availability.",
        "Future skill lookup may return not found for retained names not currently discovered.",
        "Full available-collection equivalence remains UNPROVED and required for behavioral baseline qualification.",
      ];
    }
    state.reload = await call("skills.reload", undefined, () => session.rpc.skills.reload());
    state.invoked_after_reload = await checkInvoked("after-reload");
    state.tools = await call("tools.getCurrentMetadata", undefined, () => session.rpc.tools.getCurrentMetadata());
    state.tools_initialized = Array.isArray(state.tools?.tools);
    if (!state.tools_initialized && state.tools?.tools !== null) {
      throw new Error("Historical tool metadata reader shape is unsupported");
    }
    state.tools_match_required = state.tools_initialized ? isDeepStrictEqual(
      state.tools.tools.map(tool => tool.name).sort(), [...fixture.required_tools].sort()) : null;
    if (isCandidate && (!historicalZeroSend || state.tools_initialized)
        && state.tools_match_required !== true) {
      throw new Error("Historical root tools are unavailable under the selected runtime");
    }
    state.event_log = await readEvents();
    if (!isDeepStrictEqual(state.event_log.filter(event => ids.has(event.id)), prefix)) {
      throw new Error("Historical event log projection is incomplete or changed");
    }
    for (const name of ["getContextAttribution", "getContextHeaviestMessages", "activity", "isProcessing"]) {
      const args = name === "getContextHeaviestMessages" ? { limit: 20 } : undefined;
      state.context[name] = await call(`metadata.${name}`, args,
        () => session.rpc.metadata[name](...(args ? [args] : [])));
    }
    const attribution = state.context.getContextAttribution?.contextAttribution;
    state.context_initialized = attribution != null && typeof attribution === "object"
      && !Array.isArray(attribution);
    if (historicalZeroSend && ((attribution !== null && !state.context_initialized)
        || !Array.isArray(state.context.getContextHeaviestMessages?.messages)
        || !Number.isFinite(state.context.getContextHeaviestMessages?.totalTokens)
        || state.context.getContextHeaviestMessages.totalTokens < 0
        || state.context.activity?.abortable !== false
        || state.context.activity?.hasActiveWork !== false)) {
      throw new Error("Historical context reader is malformed or has active work");
    }
    if ((!historicalZeroSend && !state.context_initialized)
        || state.context.isProcessing?.processing !== false) {
      throw new Error("Historical context reader is uninitialized or processing");
    }
    return state;
  };
  const observe = async (nativeSql = true) => {
    if (historicalProfile(config)) return observeHistorical();
    if (contextProfile(config)) {
      const state = {
        goal: await call("autopilotObjective.getState", undefined, () => session.rpc.autopilotObjective.getState()),
        mode: await call("mode.get", undefined, () => session.rpc.mode.get()),
        todos: await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos()),
        schedules: await call("schedule.list", undefined, () => session.rpc.schedule.list()),
        context: {}, context_gaps: [],
      };
      state.dependencies = await execute("sql", {
        description: "Verify no owned context dependencies", query: "SELECT todo_id,depends_on FROM todo_deps",
      });
      state.dependencies_empty = state.dependencies.toolTelemetry?.metrics?.rowsReturned === 0;
      state.events = await call("session.getEvents", undefined, () => session.getEvents());
      const fixture = contextFixture(config);
      const summaryIndex = state.events.findIndex(event => event.id === fixture.summary_event_id);
      const summary = state.events[summaryIndex];
      const post = state.events.filter(event => fixture.post_event_ids.includes(event.id));
      if (summaryIndex < 0 || summary.type !== "session.compaction_complete" || summary.data?.success !== true
          || typeof summary.data.summaryContent !== "string"
          || createHash("sha256").update(summary.data.summaryContent).digest("hex") !== fixture.summary_sha256
          || !isDeepStrictEqual(post.map(event => event.id), fixture.post_event_ids)
          || post.some(event => state.events.indexOf(event) <= summaryIndex)) {
        throw new Error("Context summary identity/digest/order differs from owner locator");
      }
      for (const name of ["getContextAttribution", "getContextHeaviestMessages", "activity", "isProcessing"]) {
        try {
          const args = name === "getContextHeaviestMessages" ? { limit: 20 } : undefined;
          state.context[name] = await call(`metadata.${name}`, args,
            () => session.rpc.metadata[name](...(args ? [args] : [])));
        } catch (error) { state.context_gaps.push({ name, error: errorInfo(error) }); }
      }
      const attribution = state.context.getContextAttribution?.contextAttribution;
      state.context_initialized = attribution != null && typeof attribution === "object" && !Array.isArray(attribution);
      if (pathExists(report.goal_path) || state.goal?.state !== null || state.mode !== "interactive"
          || !Array.isArray(state.todos?.rows) || state.todos.rows.length
          || !Array.isArray(state.schedules?.entries) || state.schedules.entries.length
          || !state.dependencies_empty
          || state.context.isProcessing?.processing !== false) {
        throw new Error("Context calibration is not isolated idle goal-free interactive state");
      }
      return state;
    }
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
    if (continuation) {
      const state = report.final_state ?? await continuationState();
      const result = report.cleanup = { errors: [], residual_namespace_preserved: true,
        mutable_state_not_restored: true, final_state: state, stopped_schedule_ids: [] };
      for (const entry of state.schedules.entries) {
        if (!Number.isInteger(entry.id) || entry.id < 1) throw new Error("Invalid owned continuation schedule");
        await call("schedule.stop", { id: entry.id }, () => session.rpc.schedule.stop({ id: entry.id }));
        result.stopped_schedule_ids.push(entry.id);
      }
      result.after_schedules = await call("schedule.list", undefined, () => session.rpc.schedule.list());
      if (result.after_schedules.entries.length) throw new Error("Owned continuation timers remain active");
      return result;
    }
    if (contextProfile(config)) {
      const state = await observe(false);
      const stopped = [];
      if (operational) {
        for (const entry of state.schedules.entries) {
          await call("schedule.stop", { id: entry.id }, () => session.rpc.schedule.stop({ id: entry.id }));
          stopped.push(entry.id);
        }
        state.operational_schedules_before_cleanup = state.schedules;
        state.schedules = await call("schedule.list", undefined, () => session.rpc.schedule.list());
        if (state.schedules.entries.length) throw new Error("Owned operational timers remain active");
      }
      return report.cleanup = { errors: [], todos: state.todos, schedules: state.schedules,
        ...(operational ? { stopped_schedule_ids: stopped,
          operational_schedules_before_cleanup: state.operational_schedules_before_cleanup } : {}),
        dependencies_empty: state.dependencies_empty, goal: state.goal, mode: state.mode, context: state.context,
        ...(state.completed_objective ? { completed_objective: state.completed_objective } : {}),
        ...(state.active_objective ? { active_objective: state.active_objective } : {}),
        ...(historicalProfile(config) ? { residual_namespace_preserved: true } : {}) };
    }
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
  const continuationState = async () => ({
    goal: await call("autopilotObjective.getState", undefined, () => session.rpc.autopilotObjective.getState()),
    mode: await call("mode.get", undefined, () => session.rpc.mode.get()),
    permissions: await call("permissions.getMode", undefined, () => session.rpc.permissions.getMode()),
    todos: await call("plan.readSqlTodos", undefined, () => session.rpc.plan.readSqlTodos()),
    schedules: await call("schedule.list", undefined, () => session.rpc.schedule.list()),
    skills: await call("skills.getInvoked", undefined, () => session.rpc.skills.getInvoked()),
    model: await call("model.getCurrent", undefined, () => session.rpc.model.getCurrent()),
    tools: await call("tools.getCurrentMetadata", undefined, () => session.rpc.tools.getCurrentMetadata()),
    context: await call("metadata.getContextAttribution", undefined, () => session.rpc.metadata.getContextAttribution()),
    activity: await call("metadata.activity", undefined, () => session.rpc.metadata.activity()),
    processing: await call("metadata.isProcessing", undefined, () => session.rpc.metadata.isProcessing()),
    native_store: pathExists(report.goal_path) ? parseDataJson(readFileSync(report.goal_path, "utf8")) : null,
  });
  const candidate = async () => {
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
    if (continuation) {
      const fixture = contextFixture(config);
      const identityPath = join(dirname(config.context_fixture_file), "identities.json");
      requirePath(identityPath, "file");
      const stat = lstatSync(identityPath);
      const identity = parseDataJson(readFileSync(identityPath, "utf8"));
      if (stat.uid !== userInfo().uid || stat.nlink !== 1 || (stat.mode & 0o077)
          || identity.session_id !== config.session_id || fixture.source_binding.source_session_id === config.session_id
          || typeof fixture.source_binding.source_session_id !== "string") {
        throw new Error("Continuation namespace differs from the isolated setup writer");
      }
      report.before_continuation = await observe(false);
      report.bound_raw_trigger = fixture.autopilot_send?.prompt
        ?? parseDataJson(readFileSync(fixture.trigger_file, "utf8")).content;
      if (fixture.autopilot_send) {
        report.recorded_autopilot_send = fixture.autopilot_send;
        report.recorded_autopilot_contract = {
          send_surface: "session.rpc.send",
          source_references: [
            "1bc7ab074eb4b06e9375850053b1a8e9bb5b8497:src/sdk/nodejs/src/generated/rpc.ts:25750-25819,37192-37193",
            "1bc7ab074eb4b06e9375850053b1a8e9bb5b8497:src/runtime/src/session/session_send_dispatch.rs:155-168",
          ],
          limits: fixture.limitations.slice(-3),
        };
      }
      const deferred = parseDataJson(readFileSync(fixture.trigger_file, "utf8"));
      report.frozen_inputs = Object.fromEntries([
        config.context_fixture_file, config.prefix_file, config.prompt_path, identityPath, fixture.canonical_file,
        fixture.trigger_file, resolve(dirname(fixture.trigger_file), deferred.source_event_path),
        ...(fixture.completed_objective ? [fixture.completed_objective.path] : []),
        ...(fixture.active_objective ? [fixture.active_objective.path, fixture.recorded_autopilot_request.path] : []),
        ...(operational ? Object.keys(operationalHashes) : []),
        join(config.home, "copilot-instructions.md"),
        ...Object.keys(entry.binding.source).map(name => join(dirname(fileURLToPath(import.meta.url)), name)),
        ...entry.observed_package.files.map(file => join(entry.package_root, file.path)),
      ].map(path => [path, hash(readFileSync(path))]));
      if (readFileSync(report.prompt_path, "utf8") !== report.bound_raw_trigger) {
        throw new Error("Continuation prompt differs from the bound original raw event");
      }
      const updated = await call("options.update", {
        runningInInteractiveMode: true, sessionCapabilities: entry.session_capabilities,
      }, () => session.rpc.options.update({
        runningInInteractiveMode: true, sessionCapabilities: entry.session_capabilities,
      }));
      if (updated?.success !== true) throw new Error("Native interactive options update failed");
      const mode = await call("permissions.setMode", { mode: "allow-all" },
        () => session.rpc.permissions.setMode({ mode: "allow-all" }));
      const configured = await call("permissions.configure", { paths: { unrestricted: true }, urls: { unrestricted: true } },
        () => session.rpc.permissions.configure({ paths: { unrestricted: true }, urls: { unrestricted: true } }));
      const actual = await call("permissions.getMode", undefined, () => session.rpc.permissions.getMode());
      if (mode?.success !== true || mode.mode !== "allow-all" || configured?.success !== true || actual?.mode !== "allow-all") {
        throw new Error("Native permission policy did not admit normal allow-all configuration");
      }
      const model = await call("model.getCurrent", undefined, () => session.rpc.model.getCurrent());
      if (model?.modelId !== config.model || model.reasoningEffort !== config.effort) {
        throw new Error("Historical continuation changed selected model or effort");
      }
      if (entry.purpose === "setup-canary") {
        const path = resolve(config.cwd, entry.canary_checks.file.path);
        if (!within(path, config.cwd)) throw new Error("Canary file escaped the owned workdir");
        report.canary_file_before_sha256 = pathExists(path) ? hash(readFileSync(path)) : null;
        if (report.canary_file_before_sha256 === entry.canary_checks.file.sha256) {
          throw new Error("Canary file must demonstrate a new candidate effect");
        }
      }
    } else {
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
    const expectedTools = candidateTools(config).sort();
    if (!(historicalZeroSend && tools === null) && (!Array.isArray(tools) || tools.length !== expectedTools.length
        || !isDeepStrictEqual(tools.map(tool => tool.name).sort(), expectedTools)
        || tools.some(tool => typeof tool.description !== "string"
          || ["namespacedName", "mcpServerName", "mcpToolName"].some(key => tool[key] !== undefined)
          || (tool.input_schema !== undefined
            && !(tool.name === "apply_patch" && tool.input_schema === null) && (!tool.input_schema
            || typeof tool.input_schema !== "object" || Array.isArray(tool.input_schema)))))) {
      throw new Error("Effective native tool metadata does not match the selected grants");
    }
    report.checks.effective_tools = tools === null ? null : true;
    report.model_configuration = await call("model.getCurrent", undefined, () => session.rpc.model.getCurrent());
    if (report.model_configuration?.modelId !== (selected ? config.model : "gpt-5.6-sol-fast")
        || report.model_configuration.reasoningEffort !== (selected ? config.effort : "high")) {
      throw new Error("Native model configuration mismatch");
    }
    if (contextProfile(config)) {
      Object.assign(report, await observe(false));
      if (!historicalZeroSend && !report.context_initialized) throw new Error("Native context remains uninitialized");
      report.checks.cold_state = true;
      if (historicalProfile(config) && contextFixture(config).schema_version === 3) {
        report.checks.recorded_payload_correspondence = report.recorded_context.native_payload_correspondence;
      } else report.checks.context_summary_order = true;
    } else {
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
    }
    report.preflight = [];
    try {
      for (const [name, path] of [
        ...(contextProfile(config) ? [] : selected ? config.evidence_paths.map((path, index) => [`evidence-${index}`, path])
          : [["plan", join(config.cwd, "plan.md")]]),
        ...(!contextProfile(config) ? [["goal", report.goal_path]] : []),
        ["sibling", contextProfile(config) ? config.context_fixture_file
          : selected ? config.denied_path : join(dirname(config.cwd), "synthetic-denied-sibling.txt")],
      ]) {
        requirePath(path, "file");
        const toolCallId = `native-probe-${name}-${randomUUID()}`;
        const arguments_ = { path, ...(selected && op === "preflight" ? { forceReadLargeFiles: true } : {}) };
        const result = await call("tools.execute:view", { name: "view", arguments: arguments_, toolCallId },
          () => session.rpc.tools.execute({ name: "view", arguments: arguments_, toolCallId }));
        report.preflight.push({ name, path, tool_call_id: toolCallId, result });
      }
      if (op === "preflight" && config.candidate_permissions?.write_paths.length
          && config.candidate_permissions?.shell_commands.length) {
        if (!isDeepStrictEqual(config.candidate_permissions,
          { write_paths: ["target.txt"], shell_commands: ["python3 -I check.py"] })) {
          throw new Error("Editable setup preflight requires its declared data-only fixture");
        }
        const target = join(config.cwd, "target.txt");
        const checker = join(config.cwd, "check.py");
        requirePath(target, "file");
        requirePath(checker, "file");
        const original = readFileSync(target);
        const originalCheck = readFileSync(checker);
        const originalModes = [target, checker].map(path => lstatSync(path).mode & 0o777);
        if (original.toString("utf8") !== "pending\n" || originalCheck.toString("utf8") !== editableFixtureCheck) {
          throw new Error("Editable setup files do not match the declared frozen fixture");
        }
        report.editable_preflight = [];
        let patchSchema;
        if (historicalZeroSend && tools === null) {
          report.argument_descriptors = await call("tools.getBuiltinDescriptors", {},
            () => session.rpc.tools.getBuiltinDescriptors({}));
          const descriptors = report.argument_descriptors?.tools;
          const patches = Array.isArray(descriptors)
            ? descriptors.filter(tool => tool?.name === "apply_patch") : [];
          if (patches.length !== 1 || !Object.hasOwn(patches[0], "inputSchema")
              || (patches[0].inputSchema !== null
                && (patches[0].inputSchema?.type !== "object"
                  || Array.isArray(patches[0].inputSchema)))) {
            throw new Error("Unsupported historical apply_patch argument descriptor");
          }
          patchSchema = patches[0].inputSchema;
        } else {
          patchSchema = tools.find(tool => tool.name === "apply_patch").input_schema;
        }
        report.editable_interpreter = execFileSync("python3", ["-I", "-c",
          "import sys; print(sys.executable); print(sys.version)"], {
          cwd: config.cwd, env: { PATH: process.env.PATH }, encoding: "utf8",
        }).trim();
        const invoke = async (name, arguments_, kind, expected, expectedCheckFailure = false) => {
          const toolCallId = `native-probe-editable-${randomUUID()}`;
          const result = await call(`tools.execute:${name}`, { name, arguments: arguments_, toolCallId },
            () => session.rpc.tools.execute({ name, arguments: arguments_, toolCallId }));
          report.editable_preflight.push({ name, tool_call_id: toolCallId, expected, result });
          const requests = report.permissions.filter(entry => entry.tool_call_id === toolCallId
            && entry.session_id === config.session_id && entry.request?.kind === kind);
          if (!requests.length || requests.some(entry => entry.error || entry.decision.kind !== expected)
              || (expected === "reject"
                ? !["denied", "rejected"].includes(result?.resultType)
                : result?.resultType !== "success"
                  && !(expectedCheckFailure && result?.resultType === "failure"))) {
            throw new Error(`Editable native permission traversal failed for ${name}`);
          }
          return result;
        };
        const patch = (path, before, after) => {
          const text = "*** Begin Patch\n*** Update File: " + path + "\n@@\n"
            + before.trimEnd().split("\n").map(line => "-" + line).join("\n") + "\n"
            + after.trimEnd().split("\n").map(line => "+" + line).join("\n") + "\n*** End Patch\n";
          const schema = patchSchema;
          if (schema?.type === "object") {
            const keys = (schema.required ?? []).filter(key =>
              ["input", "patch"].includes(key) && schema.properties?.[key]?.type === "string");
            if (keys.length !== 1 || schema.required.some(key => key !== keys[0])) {
              throw new Error("Unsupported native apply_patch argument schema");
            }
            return { [keys[0]]: text };
          }
          return text;
        };
        const check = async (expectedExit, expectedOutput) => {
          const result = await invoke("bash", {
            command: "python3 -I check.py", description: "Check owned fixture data",
          }, "shell", "approve-once", expectedExit === 1);
          const structured = result.structuredContent;
          const text = result.textResultForLlm ?? "";
          const exit = structured?.exitCode ?? structured?.exit_code
            ?? Number(text.match(/completed with exit code (-?\d+)>/)?.[1] ?? NaN);
          const output = structured?.stdout ?? text.replace(/<shellId:[^\n]*>\s*$/, "").trim();
          if (exit !== expectedExit || output.trim() !== expectedOutput
              || (structured?.stderr !== undefined && structured.stderr !== "")
              || text.includes("EXECUTED-MUTABLE-FIXTURE")) {
            throw new Error("Native check does not provide the declared exit/output witness");
          }
        };
        try {
          await invoke("apply_patch", patch(target, "pending\n", "ready\n"), "write", "approve-once");
          if (readFileSync(target, "utf8") !== "ready\n") throw new Error("Native patch effect is missing");
          await check(0, "PASS fixture data");
          await invoke("apply_patch", patch(target, "ready\n", "print('EXECUTED-MUTABLE-FIXTURE')\n"),
            "write", "approve-once");
          await check(1, "invalid fixture data");
          await invoke("apply_patch", patch(checker, editableFixtureCheck, "forbidden fixture mutation\n"),
            "write", "reject");
          if (!readFileSync(checker).equals(originalCheck)) throw new Error("Forbidden checker write occurred");
          await invoke("bash", { command: "python3 -V", description: "Refusal-only fixture check" },
            "shell", "reject");
          report.checks.editable_permission_traversal = true;
        } finally {
          if (!pathExists(target) || !readFileSync(target).equals(original)) writeFileSync(target, original);
          if (!pathExists(checker) || !readFileSync(checker).equals(originalCheck)) writeFileSync(checker, originalCheck);
          report.editable_restored = readFileSync(target).equals(original)
            && readFileSync(checker).equals(originalCheck)
            && isDeepStrictEqual([target, checker].map(path => lstatSync(path).mode & 0o777), originalModes);
        }
        if (!report.editable_restored) throw new Error("Editable preflight was not restored");
        const after = await observe(false);
        if (!historicalProfile(config)
            && (!matchesProfileState(after, projection, scheduleMapping) || after.dependencies_match !== true)) {
          throw new Error("Editable preflight changed native state");
        }
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
        || [...report.preflight, ...(report.editable_preflight ?? [])].some(item => item.result?.newMessages?.length)) {
      throw new Error("Owner preflight added or changed imported conversation content");
    }
    report.checks.prefix_preserved = true;
    if (historicalZeroSend) {
      report.checks.prefix_preservation_scope = "preflight_snapshot";
      report.checks.terminal_prefix_preserved = null;
    }
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
    }
    if (typeof (report.recorded_autopilot_send ? session.rpc?.send : session.send) !== "function"
        || typeof session.abort !== "function") {
      throw new Error("Missing public SDK send or abort surface");
    }
    const renderedPrompt = readFileSync(report.prompt_path, "utf8");
    if (continuation && report.pending_input?.length) throw new Error("Native input request preceded original submission");
    report.prompt_sha256 = hash(renderedPrompt);
    report.timeout_ms = Math.max(0, Math.floor(Math.min(report.max_timeout_ms, 330000 - (performance.now() - started))));
    if (!report.timeout_ms) throw new Error("Owned helper budget exhausted before model dispatch");
    const buffered = [];
    let messageId;
    let matchingMessage;
    const completionEvents = [];
    let active = true;
    let resolveOutcome;
    const outcome = new Promise(resolve => { resolveOutcome = resolve; });
    if (continuation) pendingOutcome = () => {
      if (messageId !== undefined) resolveOutcome({ pending: true });
    };
    const consume = event => {
      if (!active || event.agentId || event.data?.parentToolCallId) return;
      if (event.type === "session.error") {
        resolveOutcome({ error: new Error(event.data?.message ?? "Native root session error") });
      } else if (event.type === "session.idle" && event.data?.aborted === true) {
        resolveOutcome({ error: new Error("Native session idle was aborted") });
      } else if (messageId === undefined) {
        buffered.push(event);
      } else if (continuation) {
        completionEvents.push(event);
        const terminal = event.type === "session.idle"
          ? continuationCompletion(completionEvents, messageId) : undefined;
        if (terminal) resolveOutcome(terminal);
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
    if (contextProfile(config)) report.model_event_start_index = candidateEvents.length;
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
        const sendRequest = report.recorded_autopilot_send
          ? { ...report.recorded_autopilot_send, mode: "immediate", wait: false }
          : { prompt: renderedPrompt, mode: "immediate" };
        void call(report.recorded_autopilot_send ? "session.rpc.send" : "session.send", sendRequest, async () => {
          report.model_send_calls = 1;
          if (report.recorded_autopilot_send) return (await session.rpc.send(sendRequest))?.messageId;
          return session.send(sendRequest);
        }).then(id => {
          if (typeof id !== "string" || !id) throw new Error("SDK send returned no message ID");
          report.model_message_id = id;
          if (!active) return;
          messageId = id;
          if (continuation && report.pending_input?.length) resolveOutcome({ pending: true });
          for (const event of buffered) consume(event);
          buffered.length = 0;
        }).catch(error => resolveOutcome({ error }));
        const terminal = await Promise.race([outcome, deadline]);
        if (terminal.error) throw terminal.error;
        report.model_result = terminal.message;
        report.model_completion_event = terminal.idle;
        if (continuation && !terminal.pending) {
          report.model_completion_kind = terminal.kind;
          if (terminal.task_complete) report.model_task_completion = terminal.task_complete;
        }
        if (terminal.pending) {
          report.pending_input_observed = true;
          await call("session.abort", undefined, () => session.abort());
        }
      } catch (error) {
        fail(error);
        throw error;
      } finally {
        active = false;
        pendingOutcome = undefined;
        clearTimeout(deadlineTimer);
        try { stopCompletion(); } catch (error) { fail(error); }
        report.model_completed_at = new Date().toISOString();
        report.model_elapsed_seconds = (performance.now() - modelStarted) / 1000;
      }
      if (report.error) throw new Error("Candidate event capture failed");
      if (continuation) {
        for (const [path, expected] of Object.entries(report.frozen_inputs)) {
          requirePath(path, "file");
          if (hash(readFileSync(path)) !== expected) throw new Error("Frozen continuation source input changed");
        }
        const observedEntry = continuationEntry(config);
        if (observedEntry.observed_package.sha256 !== entry.observed_package.sha256) {
          throw new Error("Frozen continuation input package changed");
        }
        if (observedEntry.configuration_sha256 !== entry.configuration_sha256
            || !isDeepStrictEqual(observedEntry.binding, entry.binding)) {
          throw new Error("Frozen continuation configuration changed");
        }
        report.prefix_after = await readEvents();
        const correspondence = continuationCorrespondence(
          report.prefix_before, report.prefix_after, candidateEvents.slice(report.model_event_start_index),
          report.model_message_id, report.bound_raw_trigger, report.recorded_autopilot_send);
        Object.assign(report.checks, correspondence);
        report.primary_system_messages = correspondence.primary_system_messages;
        delete report.checks.primary_system_messages;
        report.final_state = await continuationState();
        report.tool_effects = candidateEvents.slice(report.model_event_start_index)
          .filter(event => /^tool\./.test(event.type));
        if (entry.purpose === "setup-canary" && !report.pending_input_observed) {
          const events = candidateEvents.slice(report.model_event_start_index);
          const witness = (name, key, value) => {
            const starts = events.filter(event => event.type === "tool.execution_start"
              && !event.agentId && event.data?.toolName === name && event.data?.arguments?.[key] === value);
            return events.find(event => event.type === "tool.execution_complete" && !event.agentId
              && event.data?.success === true && starts.some(start => start.data.toolCallId === event.data.toolCallId));
          };
          const shell = witness("bash", "command", entry.canary_checks.shell.command);
          const sql = witness("sql", "query", entry.canary_checks.sql.query);
          const file = resolve(config.cwd, entry.canary_checks.file.path);
          requirePath(file, "file");
          report.checks.operation_witnesses = hash(readFileSync(file)) === entry.canary_checks.file.sha256
            && shell?.data?.shellExecution?.exitCode === 0
            && typeof sql?.data?.result?.content === "string" && sql.data.result.content.length > 0
            && sql?.data?.toolTelemetry?.metrics?.rowsReturned > 0;
          if (!report.checks.operation_witnesses) throw new Error("Canary lacks actual file, shell exit or SQL result witnesses");
        }
      }
      report.status = report.pending_input_observed ? "HUMAN_INPUT_PENDING" : "CANDIDATE_OBSERVED";
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
      if (historicalProfile(config)) {
        report.provenance = "source-bound-historical";
        report.limits = contextFixture(config).limitations;
      }
    }
    validateOutput(config);
    receipt = openSync(config.output, "wx", 0o600);
    report.goal_path = validateConfig(op, config);
    if (config.operational_file) {
      operational = operationalEntry(config);
      operationalHashes = Object.fromEntries([
        config.operational_file,
        resolve(dirname(config.operational_file), operational.schedule_events.path),
      ].map(path => [path, hash(readFileSync(path))]));
      report.operational_input = { binding: operational.binding, limits: operational.limits };
    }
    if (continuation) {
      entry = continuationEntry(config);
      report.continuation_entry = entry;
      report.max_timeout_ms = entry.timeout_ms;
    }
    if (historicalProfile(config) && op === "setup"
        && (config.candidate_permissions.write_paths.length || config.candidate_permissions.shell_commands.length)) {
      if (!isDeepStrictEqual(config.candidate_permissions,
        { write_paths: ["target.txt"], shell_commands: ["python3 -I check.py"] })) {
        throw new Error("Historical editable setup requires the canonical data-only grants");
      }
      const files = [["target.txt", "pending\n"], ["check.py", editableFixtureCheck]];
      if (files.some(([name]) => pathExists(join(config.cwd, name)))) {
        throw new Error("Historical editable fixture paths must be absent");
      }
      report.editable_setup = { provenance: "evaluation-operation-data-only", files: [] };
      for (const [name, content] of files) {
        const path = join(config.cwd, name);
        writeFileSync(path, content, { flag: "wx", mode: 0o600 });
        report.editable_setup.files.push({
          path, sha256: createHash("sha256").update(content).digest("hex"), mode: lstatSync(path).mode & 0o777,
        });
      }
    }
    if (selected && !contextProfile(config)) {
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
    if (contextProfile(config)) {
      report.profile = config.profile;
      report.provenance = historicalProfile(config) ? "source-bound-historical" : "synthetic-calibration";
      delete report.modern_defaults;
      report.limits = historicalProfile(config) ? contextFixture(config).limitations : [
        "Synthetic source capability only, not historical replay or full summary/authority equivalence",
        "Context metadata has no full text; sentinel recall tests only specific information availability",
        "Pre-summary retention is diagnostic without an evidenced deletion rule",
      ];
    }
    if (continuation) {
      report.full_available_collection_equivalence = false;
      report.behavioral_baseline_ready = false;
      if (entry.purpose === "setup-canary") report.provenance = "synthetic-continuation-canary";
      report.limits.push(
        "Primary prompt observation is passive, not a pre-provider barrier",
        "Remaining CLI defaults and full available collection equivalence remain unproved",
        "Owner verifies exact workflow source after execution; selected commit is bound here",
        "Normal native allow-all preserves managed policy; package checks are not a filesystem sandbox");
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
        availableTools: candidateTools(config),
        pluginDirectories: [report.plugin_path], disabledMcpServers: ["github-mcp-server", "playwright"],
        ...(config.skill_directories ? { skillDirectories: config.skill_directories } : {}),
        skipCustomInstructions: false, instructionDirectories: [], organizationCustomInstructions: "",
        onPermissionRequest(request, invocation) {
          const decision = permissionHandler(request, invocation);
          const error = report.permissions.at(-1)?.error;
          if (error) fail(error);
          return decision;
        },
      };
      if (continuation) {
        const recordPending = (kind, request) => {
          (report.pending_input ??= []).push({ kind, request });
          pendingOutcome?.();
          return new Promise(() => {});
        };
        candidateOptions = {
          ...options, model: config.model, reasoningEffort: config.effort,
          enableManagedSettings: true, enableFileChangeTracking: true,
          enableOnDemandInstructionDiscovery: true,
          pluginDirectories: [report.plugin_path],
          disabledMcpServers: ["github-mcp-server", "playwright"],
          skipCustomInstructions: false, instructionDirectories: [], organizationCustomInstructions: "",
          ...(config.skill_directories ? { skillDirectories: config.skill_directories } : {}),
          systemMessage: { mode: "customize", sections: {
            preamble: { action: "replace", content: entry.cli_preamble },
          } },
          onUserInputRequest: request => recordPending("user-input", request),
          onElicitationRequest: request => recordPending("elicitation", request),
        };
        delete candidateOptions.availableTools;
      }
      report.connection.mode = "copilot-cli";
      report.connection.workingDirectory = config.cwd;
      report.connection.baseDirectory = config.home;
    }
    if (contextProfile(config) && !isCandidate) candidateOptions = {
      ...options, availableTools: candidateTools(config), model: config.model, reasoningEffort: config.effort,
      pluginDirectories: [config.plugin_path], disabledMcpServers: ["github-mcp-server", "playwright"],
      ...(config.skill_directories ? { skillDirectories: config.skill_directories } : {}),
      skipCustomInstructions: false, instructionDirectories: [], organizationCustomInstructions: "",
      onPermissionRequest: candidatePermissionHandler(config, report.goal_path, config.plugin_path, []),
    };
    if (operational) candidateOptions = {
      ...candidateOptions, pluginDirectories: [], enableConfigDiscovery: true, requestExtensions: false,
    };
    sdk = await import(pathToFileURL(config.sdk).href);
    await connect();
    if (continuation && !isCandidate) {
      if (op === "cleanup") {
        await cleanup();
        report.status = "CLEANED";
      } else {
        report.final_state = await continuationState();
        report.status = "OBSERVED";
      }
    } else if (contextProfile(config) && !isCandidate) {
      if (op === "setup") {
        if (historicalProfile(config)) {
          await installHistoricalSnapshot();
          report.warm = await observe(false);
        } else {
          await call("mode.set", { mode: "interactive" }, () => session.rpc.mode.set({ mode: "interactive" }));
          report.before = await observe(false);
        }
        await stop();
        if (report.error) throw new Error("Context warm producer shutdown failed");
        await connect();
      }
      if (op === "cleanup") {
        await cleanup();
        report.status = "CLEANED";
      } else {
        Object.assign(report, await observe(false));
        report.status = op === "setup" ? "SETUP_OBSERVED" : "OBSERVED";
      }
    } else if (isCandidate) {
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
        if (selected && isDeepStrictEqual(config.candidate_permissions,
          { write_paths: ["target.txt"], shell_commands: ["python3 -I check.py"] })) {
          const target = join(config.cwd, "target.txt");
          report.editable_fixture = { path: "target.txt", exists: pathExists(target) };
          if (report.editable_fixture.exists) {
            requirePath(target, "file");
            const content = readFileSync(target);
            Object.assign(report.editable_fixture, {
              mode: lstatSync(target).mode & 0o777,
              sha256: createHash("sha256").update(content).digest("hex"),
              content_base64: content.toString("base64"),
            });
          }
          const checker = join(config.cwd, "check.py");
          report.editable_checker = {
            path: "check.py", exists: pathExists(checker),
            expected_sha256: createHash("sha256").update(editableFixtureCheck).digest("hex"),
            matches_frozen_fixture: false,
          };
          if (report.editable_checker.exists) {
            requirePath(checker, "file");
            const content = readFileSync(checker);
            Object.assign(report.editable_checker, {
              mode: lstatSync(checker).mode & 0o777,
              sha256: createHash("sha256").update(content).digest("hex"),
              matches_frozen_fixture: content.equals(Buffer.from(editableFixtureCheck)),
            });
          }
          if (!report.editable_checker.matches_frozen_fixture) {
            throw new Error("Fixed fixture checker changed or is missing");
          }
        }
        report.status = "OBSERVED";
      }
    }
    if (operational && (!isDeepStrictEqual(operationalEntry(config), operational)
        || Object.entries(operationalHashes).some(([path, expected]) => hash(readFileSync(path)) !== expected))) {
      throw new Error("Frozen operational configuration changed");
    }
  } catch (error) {
    fail(error);
  } finally {
    if (continuation && isCandidate && report.model_send_calls && session) {
      try {
        report.final_state ??= await continuationState();
        await cleanup();
      } catch (error) { fail(error); }
    }
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
      if (contextProfile(config)) report.candidate_events = candidateEvents;
      try { unsubscribe?.(); } catch (error) { fail(error); }
      try { if (eventFile !== undefined) closeSync(eventFile); } catch (error) { fail(error); }
      if (report.error) report.status = report.model_send_calls ? "FAILED" : "PREMODEL_BLOCKED";
      report.firsterror = report.error?.message ?? null;
      if (continuation && entry?.purpose === "setup-canary" && report.status === "CANDIDATE_OBSERVED"
          && report.shutdown_errors.length === 0) {
        report.continuation_receipt = {
          status: "CONTINUATION_CANARY_OBSERVED", configuration_sha256: entry.configuration_sha256,
          interactive_identity: report.checks.interactive_identity,
          operation_witnesses: report.checks.operation_witnesses,
          exactly_once: report.checks.exactly_once, shutdown_errors: [],
        };
      }
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
