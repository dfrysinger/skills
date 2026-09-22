import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const sourceExtension = join(
  dirname(fileURLToPath(import.meta.url)),
  "extension.mjs",
);

const goodBrief =
  "Keep: active baton\n\nDrop: resolved detail\n\nAfter compaction: continue; do not compact again.";

async function stageExtension() {
  const root = await mkdtemp(join(tmpdir(), "self compact extension "));
  const extensionDirectory = join(root, "extensions", "self-compact");
  const sdkDirectory = join(root, "node_modules", "@github", "copilot-sdk");
  await mkdir(extensionDirectory, { recursive: true });
  await mkdir(sdkDirectory, { recursive: true });
  await cp(sourceExtension, join(extensionDirectory, "extension.mjs"));
  await writeFile(
    join(sdkDirectory, "package.json"),
    `${JSON.stringify({
      name: "@github/copilot-sdk",
      type: "module",
      exports: { "./extension": "./extension.mjs" },
    })}\n`,
  );
  await writeFile(
    join(sdkDirectory, "extension.mjs"),
    `import {readFileSync} from "node:fs";
let objective = process.env.MOCK_OBJECTIVE
  ? {
      objective: process.env.MOCK_OBJECTIVE,
      status: process.env.MOCK_OBJECTIVE_STATUS ?? "active",
    }
  : null;
const commands = [];
const session = {
  rpc: {
    workspaces: {
      async readAutopilotObjective() {
        return {
          content: objective
            ? JSON.stringify({current: objective})
            : null,
        };
      },
    },
    commands: {
      async invoke({name, input}) {
        commands.push({name, input});
        if (input === "") {
          objective = objective ? {...objective, status: "paused"} : objective;
          return {kind: "completed"};
        } else {
          objective = {objective: input, status: "active"};
        }
        return {kind: "text"};
      },
    },
  },
  async send() {
    return "message-id";
  },
};
export async function joinSession({tools}) {
  const compact = tools.find(({name}) => name === "self_compact");
  setImmediate(async () => {
    const invocation = {
      sessionId: "session-123",
      toolCallId: "call-456",
      toolName: "self_compact",
    };
    const prepareResult = process.env.MOCK_PREPARE_FIRST === "true"
      ? await compact.handler({action: "prepare"}, invocation)
      : null;
    const result = await compact.handler(
      process.env.MOCK_ACTION
        ? {
            action: process.env.MOCK_ACTION,
            operationId: process.env.MOCK_OPERATION_ID,
          }
        : {brief: readFileSync(process.env.MOCK_INPUT, "utf8")},
      invocation,
    );
    process.stdout.write(JSON.stringify({
      result,
      prepareResult,
      schema: compact.parameters,
      defer: compact.defer,
      commands,
    }));
  });
  return session;
}
`,
  );
  return { root, extensionPath: join(extensionDirectory, "extension.mjs") };
}

async function runExtension(
  brief,
  {
    withSubmitter = true,
    objective,
    objectiveStatus,
    prepareFirst = false,
    submitterFailure = false,
    readiness = "one",
    action,
    operationId,
    terminalStatus,
    preparedObjective,
  } = {},
) {
  const { root, extensionPath } = await stageExtension();
  const submitter = join(root, "mock-submitter.mjs");
  const capture = join(root, "capture.json");
  const input = join(root, "input.txt");
  const inboxRoot = join(root, "session-inbox");
  const instances = join(inboxRoot, "instances");
  await mkdir(instances, { recursive: true });
  if (readiness !== "zero") {
    await writeFile(
      join(instances, "session-123-gen-a.json"),
      `${JSON.stringify({
        sessionId: "session-123",
        generation: "gen-a",
        updatedAt: new Date(
          Date.now() - (readiness === "stale" ? 60_000 : 0),
        ).toISOString(),
      })}\n`,
    );
  }
  if (readiness === "multiple") {
    await writeFile(
      join(instances, "session-123-gen-b.json"),
      `${JSON.stringify({
        sessionId: "session-123",
        generation: "gen-b",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
  }
  if (terminalStatus) {
    const filesDir = join(root, "session-123", "files");
    await mkdir(filesDir, { recursive: true });
    await writeFile(
      join(filesDir, `self-compact-${terminalStatus.operationId}.status.json`),
      `${JSON.stringify({
        version: 1,
        runId: "terminal-run",
        observedRootEventId: null,
        attempt: 1,
        updatedAt: new Date().toISOString(),
        ...terminalStatus,
      })}\n`,
    );
  }
  if (preparedObjective) {
    const filesDir = join(root, "session-123", "files");
    await mkdir(filesDir, { recursive: true });
    await writeFile(
      join(filesDir, "self-compact.autopilot-objective.json"),
      `${JSON.stringify({
        version: 1,
        sessionId: "session-123",
        objective: preparedObjective,
        preparedAt: new Date().toISOString(),
      })}\n`,
    );
  }
  await writeFile(input, brief);
  await writeFile(
    submitter,
    `import {writeFileSync} from "node:fs";
writeFileSync(process.env.MOCK_CAPTURE, JSON.stringify({
  args: process.argv.slice(2),
  script: process.argv[1],
  runtime: process.execPath,
  session: process.env.COPILOT_AGENT_SESSION_ID,
  objectiveBase64: process.env.SELF_COMPACT_AUTOPILOT_OBJECTIVE_BASE64 ?? null,
}));
if (process.env.MOCK_SUBMITTER_FAILURE === "true") {
  process.stderr.write("forced submitter failure\\n");
  process.exit(1);
}
process.stdout.write("self-compact handoff receipt: proof-token\\nwatcher log: run.log\\n");
`,
  );

  const child = spawn(process.execPath, [extensionPath], {
    env: {
      ...process.env,
      MOCK_INPUT: input,
      MOCK_CAPTURE: capture,
      ...(objective ? { MOCK_OBJECTIVE: objective } : {}),
      ...(objectiveStatus ? { MOCK_OBJECTIVE_STATUS: objectiveStatus } : {}),
      ...(prepareFirst ? { MOCK_PREPARE_FIRST: "true" } : {}),
      ...(submitterFailure ? { MOCK_SUBMITTER_FAILURE: "true" } : {}),
      ...(action ? { MOCK_ACTION: action } : {}),
      ...(operationId ? { MOCK_OPERATION_ID: operationId } : {}),
      SELF_COMPACT_SESSION_STATE_DIR: root,
      COPILOT_SESSION_INBOX_DIR: inboxRoot,
      ...(withSubmitter ? { SELF_COMPACT_SUBMITTER: submitter } : {}),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const exit = await new Promise((resolve) => {
    child.on("exit", (code, signal) => resolve({ code, signal }));
  });
  const invocation = await readFile(capture, "utf8").then(
    JSON.parse,
    () => null,
  );
  await rm(root, { recursive: true, force: true });
  return { ...exit, stdout, stderr, invocation, submitter };
}

test("arms the portable submitter through the current Node runtime", async () => {
  const outcome = await runExtension(goodBrief);
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(
    registered.result,
    "self-compact handoff receipt: proof-token\nwatcher log: run.log",
  );
  assert.equal(registered.defer, "never");
  assert.equal(registered.schema.required, undefined);
  assert.equal(registered.schema.additionalProperties, false);
  assert.deepEqual(Object.keys(registered.schema.properties), [
    "action",
    "brief",
    "operationId",
  ]);
  assert.notEqual(outcome.invocation, null, "submitter was never launched");
  assert.deepEqual(outcome.invocation.args, ["--tool-call-id", "call-456"]);
  assert.equal(outcome.invocation.session, "session-123");
  assert.equal(outcome.invocation.runtime, process.execPath);
  assert.equal(outcome.invocation.script, outcome.submitter);
});

test("rejects malformed briefs before launching the submitter", async () => {
  const outcome = await runExtension(
    "Keep:\n\nDrop: detail\n\nAfter compaction: continue.",
  );
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result.resultType, "failure");
  assert.match(registered.result.textResultForLlm, /brief must be/);
  assert.equal(outcome.invocation, null);
});

test("defaults to the Node submitter rather than a shell script", async () => {
  const outcome = await runExtension(goodBrief, { withSubmitter: false });
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result.resultType, "failure");
  const detail = registered.result.textResultForLlm;
  assert.match(detail, /submit-compact\.mjs/);
  assert.doesNotMatch(detail, /submit-compact\.sh/);
  assert.doesNotMatch(detail, /EFTYPE/);
});

test("pauses an active objective and privately binds its exact text", async () => {
  const objective = "Finish the active objective exactly.";
  const outcome = await runExtension(goodBrief, { objective, prepareFirst: true });
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result, "self-compact handoff receipt: proof-token\nwatcher log: run.log");
  assert.match(registered.prepareResult, /exact objective is staged/);
  assert.deepEqual(registered.commands, [{ name: "autopilot", input: "" }]);
  assert.equal(
    Buffer.from(outcome.invocation.objectiveBase64, "base64").toString("utf8"),
    objective,
  );
});

test("restores a paused objective when arming fails", async () => {
  const objective = "Resume after a failed compact arm.";
  const outcome = await runExtension(goodBrief, {
    objective,
    prepareFirst: true,
    submitterFailure: true,
  });

  test("refuses a final self_compact call while autopilot is still active", async () => {
    const outcome = await runExtension(goodBrief, {
      objective: "Active objective that was not prepared.",
    });
    assert.equal(outcome.code, 0, outcome.stderr);
    const registered = JSON.parse(outcome.stdout);
    assert.equal(registered.result.resultType, "failure");
    assert.match(registered.result.textResultForLlm, /self_compact_prepare first/);
    assert.deepEqual(registered.commands, []);
    assert.equal(outcome.invocation, null);
  });
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result.resultType, "failure");
  assert.match(registered.result.textResultForLlm, /forced submitter failure/);
  assert.deepEqual(registered.commands, [
    { name: "autopilot", input: "" },
    { name: "autopilot", input: objective },
  ]);
});

test("does not treat the embedded extension host as the Node child runtime", async () => {
  const source = await readFile(sourceExtension, "utf8");
  assert.match(
    source,
    /const nodeBin = process\.env\.SELF_COMPACT_NODE_BIN \?\? "node";/,
  );
  assert.doesNotMatch(source, /execFileAsync\(\s*process\.execPath,/);
});

for (const readiness of ["zero", "stale", "multiple"]) {
  test(`${readiness} readiness fails before direct compact arming`, async () => {
    const outcome = await runExtension(goodBrief, { readiness });
    assert.equal(outcome.code, 0, outcome.stderr);
    const registered = JSON.parse(outcome.stdout);
    assert.equal(registered.result.resultType, "failure");
    assert.match(
      registered.result.textResultForLlm,
      readiness === "multiple" ? /multiple fresh/ : /no fresh/,
    );
    assert.equal(outcome.invocation, null);
  });

  test(`${readiness} readiness fails before autopilot preparation`, async () => {
    const outcome = await runExtension(goodBrief, {
      readiness,
      objective: "Objective remains active.",
      prepareFirst: true,
    });
    assert.equal(outcome.code, 0, outcome.stderr);
    const registered = JSON.parse(outcome.stdout);
    assert.equal(registered.prepareResult.resultType, "failure");
    assert.deepEqual(registered.commands, []);
  });
}

test("healthy inactive preparation does not pause autopilot", async () => {
  const outcome = await runExtension(goodBrief, { prepareFirst: true });
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.match(registered.prepareResult, /No active native autopilot objective/);
  assert.deepEqual(registered.commands, []);
});

test("the next tool entry synchronously surfaces an unread terminal status", async () => {
  const outcome = await runExtension(goodBrief, {
    terminalStatus: {
      operationId: "89abcdef",
      state: "terminal-failure",
      reason: "generated terminal notice could not be delivered",
    },
  });
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result.resultType, "failure");
  assert.match(registered.result.textResultForLlm, /89abcdef/);
  assert.match(registered.result.textResultForLlm, /terminal-failure/);
  assert.match(registered.result.textResultForLlm, /could not be delivered/);
  assert.equal(outcome.invocation, null);
});

test("a readiness loss after preparation restores the staged objective", async () => {
  const objective = "Restore after readiness disappears.";
  const outcome = await runExtension(goodBrief, {
    readiness: "stale",
    objective,
    objectiveStatus: "paused",
    preparedObjective: objective,
  });
  assert.equal(outcome.code, 0, outcome.stderr);
  const registered = JSON.parse(outcome.stdout);
  assert.equal(registered.result.resultType, "failure");
  assert.match(registered.result.textResultForLlm, /no fresh/);
  assert.deepEqual(registered.commands, [
    { name: "autopilot", input: objective },
  ]);
  assert.equal(outcome.invocation, null);
});
