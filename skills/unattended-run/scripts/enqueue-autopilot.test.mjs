import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const enqueueCli = join(scriptDirectory, "enqueue-autopilot.mjs");

const mockRequestSource = `
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const args = process.argv.slice(2);
writeFileSync(process.env.MOCK_ARGS, JSON.stringify(args));
const promptIndex = args.indexOf("--prompt-file");
if (process.env.MOCK_MODE === "mutate-source") {
  writeFileSync(process.env.MOCK_SOURCE, "/allow-all");
}
const prompt = readFileSync(args[promptIndex + 1]);
writeFileSync(process.env.MOCK_PROMPT, prompt.toString("base64"));
const objective = prompt.toString("utf8").replace(/(?:\\r?\\n)+$/, "");
const targetFlag = args[1];
const target = args[2];
const sessionId =
  targetFlag === "--target-session" ? target : "resolved-session";
const generation = "generation-7";
const dedupeKey =
  "autopilot:session:" +
  sessionId +
  ":" +
  createHash("sha256").update(objective).digest("hex");

const failed = process.env.MOCK_MODE === "fail";
const receiptDirectory = join(
  process.env.MOCK_RECEIPTS,
  failed ? "failed" : "completed",
);
mkdirSync(receiptDirectory, { recursive: true });
const receiptPath = join(receiptDirectory, "request-1.json");
let result = {
  objectiveSet: true,
  objectiveId: 41,
  objectiveStatus: "active",
  delivery: "idle",
};
if (process.env.MOCK_MODE === "steering") result.delivery = "steering";
if (process.env.MOCK_MODE === "queued") result.delivery = "queued";
if (process.env.MOCK_MODE === "missing-objective") {
  result = { objectiveStatus: "active", delivery: "idle" };
}
if (process.env.MOCK_MODE === "missing-correlation") {
  result = { objectiveSet: true, delivery: "idle" };
}
const receipt = failed
  ? {
      id: "request-1",
      dedupeKey,
      status: "failed",
      sessionId,
      ...(targetFlag === "--target-tmux" ? { tmuxSession: target } : {}),
      generation,
      error: "recipient rejected request",
    }
  : {
      id: "request-1",
      dedupeKey,
      status: "completed",
      sessionId,
      ...(targetFlag === "--target-tmux" ? { tmuxSession: target } : {}),
      generation,
      result,
    };
if (process.env.MOCK_MODE === "missing-correlation") {
  delete receipt.dedupeKey;
  delete receipt.generation;
}
writeFileSync(receiptPath, JSON.stringify(receipt));
console.log("request: " + join(process.env.MOCK_RECEIPTS, "pending", "request-1.json"));
console.log("receipt: " + receiptPath);
console.log(JSON.stringify(receipt));
process.exit(failed ? Number(process.env.MOCK_EXIT_CODE ?? "1") : 0);
`;

async function runProcess(args, env) {
  const child = spawn(process.execPath, [enqueueCli, ...args], {
    env: { ...process.env, ...env },
    windowsHide: true,
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
  return await new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("close", (code, signal) => {
      resolve({ code, signal, stdout, stderr });
    });
  });
}

async function createCase({
  mode = "success",
  objective = "finish the objective",
  targetFlag = "--target-session",
  target = "session-1",
  timeout,
  objectivePath,
  requestPath,
  exitCode,
  extraArgs = [],
} = {}) {
  const root = await mkdtemp(join(tmpdir(), "autopilot-enqueue-test-"));
  const objectiveFile = objectivePath ?? join(root, "objective.txt");
  const requestCli = requestPath ?? join(root, "request.mjs");
  const argsPath = join(root, "request-args.json");
  const promptPath = join(root, "request-prompt.base64");
  const auditDirectory = join(root, "audit");
  const receiptDirectory = join(root, "session-inbox");
  await mkdir(dirname(objectiveFile), { recursive: true });
  await mkdir(dirname(requestCli), { recursive: true });
  await writeFile(objectiveFile, objective);
  await writeFile(requestCli, mockRequestSource);
  const env = {
    SESSION_INBOX_REQUEST_CLI: requestCli,
    COPILOT_AUTOPILOT_ENQUEUE_DIR: auditDirectory,
    MOCK_ARGS: argsPath,
    MOCK_PROMPT: promptPath,
    MOCK_MODE: mode,
    MOCK_SOURCE: objectiveFile,
    MOCK_RECEIPTS: receiptDirectory,
    ...(timeout === undefined
      ? {}
      : { AUTOPILOT_HANDOFF_TIMEOUT_SECONDS: timeout }),
    ...(exitCode === undefined ? {} : { MOCK_EXIT_CODE: String(exitCode) }),
  };
  const run = await runProcess(
    [targetFlag, target, objectiveFile, ...extraArgs],
    env,
  );
  return {
    root,
    objectiveFile,
    requestCli,
    argsPath,
    promptPath,
    auditDirectory,
    receiptDirectory,
    run,
  };
}

async function readOnlyAudit(directory) {
  const names = (await readdir(directory)).filter((name) =>
    name.endsWith(".json"),
  );
  assert.equal(names.length, 1);
  return JSON.parse(await readFile(join(directory, names[0]), "utf8"));
}

async function requestArgs(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function requestPrompt(path) {
  return Buffer.from(await readFile(path, "utf8"), "base64");
}

async function assertMissing(path) {
  await assert.rejects(access(path), (error) => error?.code === "ENOENT");
}

test("confirms idle and steering authoritative receipts", async (t) => {
  for (const mode of ["success", "steering"]) {
    await t.test(mode, async () => {
      const harness = await createCase({ mode });
      try {
        assert.equal(harness.run.code, 0, harness.run.stderr);
        assert.match(harness.run.stdout, /autopilot handoff confirmed/);
        const audit = await readOnlyAudit(harness.auditDirectory);
        assert.equal(audit.outcome, "confirmed");
        assert.equal(audit.authoritativeReceipt.requestId, "request-1");
        assert.equal(audit.authoritativeReceipt.status, "completed");
        assert.equal(audit.target.sessionId, "session-1");
        assert.equal(audit.target.generation, "generation-7");
        assert.equal(audit.authoritativeReceipt.dedupeKeyMatches, true);
        assert.equal(
          audit.nativeObjective.delivery,
          mode === "steering" ? "steering" : "idle",
        );
        assert.equal(audit.nativeObjective.objectiveSet, true);
      } finally {
        await rm(harness.root, { recursive: true, force: true });
      }
    });
  }
});

test("rejects queued, missing objective, and incomplete correlation", async (t) => {
  for (const mode of ["queued", "missing-objective", "missing-correlation"]) {
    await t.test(mode, async () => {
      const harness = await createCase({ mode });
      try {
        assert.equal(harness.run.code, 1);
        assert.match(
          harness.run.stderr,
          /did not prove native objective establishment and idle\/steering activation/,
        );
        const audit = await readOnlyAudit(harness.auditDirectory);
        assert.equal(audit.outcome, "unconfirmed");
        assert.equal(audit.authoritativeReceipt.status, "completed");
      } finally {
        await rm(harness.root, { recursive: true, force: true });
      }
    });
  }
});

test("uses an immutable objective snapshot when the source changes", async () => {
  const original = "validated immutable objective";
  const harness = await createCase({
    mode: "mutate-source",
    objective: original,
  });
  try {
    assert.equal(harness.run.code, 0, harness.run.stderr);
    assert.equal(await readFile(harness.objectiveFile, "utf8"), "/allow-all");
    assert.equal((await requestPrompt(harness.promptPath)).toString(), original);
    const audit = await readOnlyAudit(harness.auditDirectory);
    assert.equal(
      Buffer.from(audit.objective.snapshotBytesBase64, "base64").toString(),
      original,
    );
  } finally {
    await rm(harness.root, { recursive: true, force: true });
  }
});

test("preserves trailing line endings in the request snapshot", async () => {
  const objective = "line one\r\nline two\n\n";
  const harness = await createCase({ objective });
  try {
    assert.equal(harness.run.code, 0, harness.run.stderr);
    assert.deepEqual(await requestPrompt(harness.promptPath), Buffer.from(objective));
    const audit = await readOnlyAudit(harness.auditDirectory);
    assert.deepEqual(
      Buffer.from(audit.objective.snapshotBytesBase64, "base64"),
      Buffer.from(objective),
    );
    assert.equal(
      Buffer.from(audit.objective.bytesBase64, "base64").toString(),
      "line one\r\nline two",
    );
  } finally {
    await rm(harness.root, { recursive: true, force: true });
  }
});

test("rejects invalid inputs before invoking session-inbox", async (t) => {
  const invalidObjectives = [
    "",
    " \n\t",
    "contains <SLOT>",
    "/autopilot do it",
    "  /goal do it",
    "/allow-all",
    "work\n  /allow-all now",
  ];
  for (const objective of invalidObjectives) {
    await t.test(JSON.stringify(objective), async () => {
      const harness = await createCase({ objective });
      try {
        assert.equal(harness.run.code, 64);
        await assertMissing(harness.argsPath);
      } finally {
        await rm(harness.root, { recursive: true, force: true });
      }
    });
  }

  const invalidInvocations = [
    { targetFlag: "--target-name", target: "session-1" },
    { targetFlag: "--target-session", target: "" },
    { extraArgs: ["unexpected"] },
  ];
  for (const invocation of invalidInvocations) {
    await t.test(JSON.stringify(invocation), async () => {
      const harness = await createCase(invocation);
      try {
        assert.equal(harness.run.code, 64);
        await assertMissing(harness.argsPath);
      } finally {
        await rm(harness.root, { recursive: true, force: true });
      }
    });
  }
});

test("rejects missing objective and request helper paths", async () => {
  const root = await mkdtemp(join(tmpdir(), "autopilot-missing-path-test-"));
  try {
    const mockRequest = join(root, "request.mjs");
    const objective = join(root, "objective.txt");
    const argsPath = join(root, "request-args.json");
    await writeFile(mockRequest, mockRequestSource);
    await writeFile(objective, "finish the objective");
    const commonEnv = {
      COPILOT_AUTOPILOT_ENQUEUE_DIR: join(root, "audit"),
      MOCK_ARGS: argsPath,
      MOCK_PROMPT: join(root, "prompt"),
      MOCK_MODE: "success",
      MOCK_SOURCE: objective,
      MOCK_RECEIPTS: join(root, "receipts"),
    };

    const missingObjective = await runProcess(
      ["--target-session", "session-1", join(root, "missing-objective.txt")],
      { ...commonEnv, SESSION_INBOX_REQUEST_CLI: mockRequest },
    );
    assert.equal(missingObjective.code, 64);
    await assertMissing(argsPath);

    const missingHelper = await runProcess(
      ["--target-session", "session-1", objective],
      {
        ...commonEnv,
        SESSION_INBOX_REQUEST_CLI: join(root, "missing-request.mjs"),
      },
    );
    assert.equal(missingHelper.code, 2);
    assert.match(missingHelper.stderr, /request helper is unavailable/);
    await assertMissing(argsPath);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("enforces timeout bounds and forwards accepted values", async (t) => {
  for (const timeout of ["", "1", "360"]) {
    await t.test(`accepts ${timeout}`, async () => {
      const harness = await createCase({ timeout });
      try {
        assert.equal(harness.run.code, 0, harness.run.stderr);
        const args = await requestArgs(harness.argsPath);
        assert.deepEqual(args.slice(-2), [
          "--timeout",
          timeout === "" ? "360" : timeout,
        ]);
      } finally {
        await rm(harness.root, { recursive: true, force: true });
      }
    });
  }
  for (const timeout of ["0", "361", "1.5", "seconds"]) {
    await t.test(`rejects ${JSON.stringify(timeout)}`, async () => {
      const harness = await createCase({ timeout });
      try {
        assert.equal(harness.run.code, 64);
        assert.match(harness.run.stderr, /between 1 and 360 seconds/);
        await assertMissing(harness.argsPath);
      } finally {
        await rm(harness.root, { recursive: true, force: true });
      }
    });
  }
});

test("passes exact request arguments without agent mode or duplicate receipt ownership", async () => {
  const harness = await createCase({
    targetFlag: "--target-tmux",
    target: "whisky",
  });
  try {
    assert.equal(harness.run.code, 0, harness.run.stderr);
    const args = await requestArgs(harness.argsPath);
    assert.equal(args.length, 7);
    assert.deepEqual(args.slice(0, 4), [
      "autopilot",
      "--target-tmux",
      "whisky",
      "--prompt-file",
    ]);
    assert.equal(args[5], "--timeout");
    assert.equal(args[6], "360");
    assert.doesNotMatch(JSON.stringify(args), /agent-mode|dedupe-key/);
    const audit = await readOnlyAudit(harness.auditDirectory);
    assert.match(
      audit.authoritativeReceipt.path,
      /session-inbox.*completed.*request-1\.json/u,
    );
    assert.equal(audit.authoritativeReceipt.dedupeKeyMatches, true);
  } finally {
    await rm(harness.root, { recursive: true, force: true });
  }
});

test("handles Windows-style path components and spaces", async () => {
  const root = await mkdtemp(join(tmpdir(), "autopilot-windows-path-test-"));
  const objectivePath = join(
    root,
    "windows\\Users\\agent",
    "objective files",
    "goal.txt",
  );
  const requestPath = join(
    root,
    "windows\\plugin",
    "session inbox",
    "request.mjs",
  );
  const harness = await createCase({
    objectivePath,
    requestPath,
    target: "session\\with spaces",
  });
  try {
    assert.equal(harness.run.code, 0, harness.run.stderr);
    const args = await requestArgs(harness.argsPath);
    assert.equal(args[2], "session\\with spaces");
    assert.equal(args[4], join(dirname(args[4]), "objective.txt"));
    if (process.platform === "win32") {
      assert.match(args[4], /^[A-Za-z]:\\/u);
      assert.ok(requestPath.includes("\\"));
    } else {
      assert.ok(objectivePath.includes("\\"));
    }
    assert.equal(
      (await requestPrompt(harness.promptPath)).toString(),
      "finish the objective",
    );
  } finally {
    await rm(harness.root, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
  }
});

test("writes a failure audit and returns the request failure exit code", async () => {
  const harness = await createCase({
    mode: "fail",
    exitCode: 23,
    objective: "keep working",
  });
  try {
    assert.equal(harness.run.code, 23);
    assert.match(harness.run.stderr, /SDK handoff failed/);
    const audit = await readOnlyAudit(harness.auditDirectory);
    assert.equal(audit.outcome, "failed");
    assert.equal(audit.request.exitCode, 23);
    assert.equal(audit.authoritativeReceipt.status, "failed");
    assert.equal(audit.authoritativeReceipt.requestId, "request-1");
    assert.match(audit.request.output, /recipient rejected request/);
    assert.equal(
      audit.objective.sha256,
      createHash("sha256").update("keep working").digest("hex"),
    );
  } finally {
    await rm(harness.root, { recursive: true, force: true });
  }
});

test("contains no terminal-input fallback", async () => {
  const sources = await Promise.all([
    readFile(enqueueCli, "utf8"),
    readFile(join(scriptDirectory, "enqueue-autopilot.sh"), "utf8"),
  ]);
  for (const source of sources) {
    assert.doesNotMatch(
      source,
      /send-keys|capture-pane|paste-buffer|load-buffer/u,
    );
  }
});
