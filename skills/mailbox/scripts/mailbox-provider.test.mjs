// Provider-native mailbox contract guards. These tests describe the behavior
// required by design/provider-native-cross-client-mailbox.md. Cases that cover
// provider behavior fail until the production code supports it; cases named
// "legacy" pass today and must keep passing.
//
// Production seams assumed beyond today's exports (smallest intended names):
//   canonicalizeMailboxAddress(address) -> { address, provider, name, machine? }
//   mailboxPathKey(address)             -> "/"-separated relative path key
//   createMailbox({ wakeupAdapters: { <provider>: { wake(request) } } })
//     request: { address, provider, name, envelopeId, attemptId, prompt }
//     result:  { outcome: verified|submitted|held|refused|deferred|ambiguous,
//                detail?: string, releaseWatcher?: true }
//   mailbox.watch(address, { generation }) with generation-aware watcher locks
//   MAILBOX_SELF_ADDRESS honored by the mailbox.mjs CLI.
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import * as mailboxCore from "./mailbox-core.mjs";

const { createMailbox, parseMailboxAddress } = mailboxCore;
const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const cliPath = join(scriptDirectory, "mailbox.mjs");
const POSITIVE_PROMPT = /^check mailbox; skip if empty \[mb:[^\]]+\]$/;
const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

async function sandbox(prefix, body) {
  const root = await mkdtemp(join(tmpdir(), `mailbox-provider-${prefix}-`));
  try {
    await body(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

async function listFiles(root, prefix = "") {
  let entries;
  try {
    entries = await readdir(join(root, prefix), { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
  const files = [];
  for (const entry of entries) {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) files.push(...(await listFiles(root, relative)));
    else files.push(relative);
  }
  return files.sort();
}

async function exists(path) {
  try {
    await readFile(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function waitFor(description, probe, timeoutMs = 4_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await probe();
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${description}`);
    await sleep(25);
  }
}

function trackSettled(promise) {
  const state = { settled: false, error: undefined };
  state.promise = promise.then(
    () => {
      state.settled = true;
    },
    (error) => {
      state.settled = true;
      state.error = error;
    },
  );
  return state;
}

function envelopeFor(id, to, extra = {}) {
  return {
    id,
    from: { name: "whisky" },
    to,
    summary: `summary-${id}`,
    message: `message-${id}`,
    attachments: [],
    sent_at: "2026-11-03T00:00:00Z",
    ...extra,
  };
}

async function writeEnvelopeFile(mailboxRoot, key, state, envelope) {
  const directory = join(mailboxRoot, ...key.split("/"), state);
  await mkdir(directory, { recursive: true });
  await writeFile(
    join(directory, `${envelope.id}.json`),
    `${JSON.stringify(envelope, null, 2)}\n`,
  );
}

function providerTo(provider, name, machine) {
  return {
    address: `${provider}:${name}${machine ? `@${machine}` : ""}`,
    provider,
    name,
    ...(machine ? { machine } : {}),
  };
}

// The request CLI is Copilot-only. Providers other than Copilot must never
// reach it, so every Copilot-compat case records its calls.
async function writeRequestMock(root, { stdout, stateRoot } = {}) {
  const script = join(root, "mock-request.mjs");
  const callLog = join(root, "request-calls.jsonl");
  const snapshot = join(root, "request-state-snapshot.json");
  await writeFile(
    script,
    `import { appendFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
appendFileSync(${JSON.stringify(callLog)}, JSON.stringify(process.argv.slice(2)) + "\\n");
function walk(root, prefix = "") {
  let entries = [];
  try { entries = readdirSync(join(root, prefix), { withFileTypes: true }); } catch { return []; }
  return entries.flatMap((entry) => {
    const relative = prefix ? prefix + "/" + entry.name : entry.name;
    return entry.isDirectory() ? walk(root, relative) : [relative];
  });
}
${stateRoot ? `writeFileSync(${JSON.stringify(snapshot)}, JSON.stringify(walk(${JSON.stringify(stateRoot)})));` : ""}
console.log(${JSON.stringify(
      stdout ?? '{"status":"completed","result":{"delivery":"idle"}}',
    )});
`,
  );
  return {
    script,
    async calls() {
      try {
        return (await readFile(callLog, "utf8"))
          .trim()
          .split("\n")
          .map((line) => JSON.parse(line));
      } catch (error) {
        if (error?.code === "ENOENT") return [];
        throw error;
      }
    },
    async snapshot() {
      return JSON.parse(await readFile(snapshot, "utf8"));
    },
  };
}

function recordingAdapter(results) {
  const calls = [];
  const queue = Array.isArray(results) ? [...results] : undefined;
  return {
    calls,
    async wake(request) {
      calls.push(request);
      if (queue) return queue.length > 1 ? queue.shift() : queue[0];
      return typeof results === "function"
        ? await results(request, calls.length)
        : results;
    },
  };
}

function providerMailbox(root, adapters, options = {}) {
  return createMailbox({
    mailboxRoot: join(root, "mailbox"),
    stateRoot: join(root, "state"),
    remoteMailboxRoot: null,
    machineName: null,
    terminalPokeCli: null,
    requestCli: options.requestCli ?? join(root, "unused-request.mjs"),
    wakeupAdapters: adapters,
    ...options.extra,
  });
}

function notificationFile(root, key, id, extension) {
  return join(root, "state", "notified", ...key.split("/"), `${id}.${extension}`);
}

// ---------------------------------------------------------------------------
// (1) Address parsing and canonicalization
// ---------------------------------------------------------------------------

test("canonical addresses map bare Copilot and every provider form exactly", () => {
  assert.equal(typeof mailboxCore.canonicalizeMailboxAddress, "function");
  const cases = [
    ["alpha", { address: "copilot:alpha", provider: "copilot", name: "alpha" }],
    ["copilot:alpha", { address: "copilot:alpha", provider: "copilot", name: "alpha" }],
    ["claude:alpha", { address: "claude:alpha", provider: "claude", name: "alpha" }],
    ["codex:alpha", { address: "codex:alpha", provider: "codex", name: "alpha" }],
    [
      "alpha@surface-pro",
      {
        address: "copilot:alpha@surface-pro",
        provider: "copilot",
        name: "alpha",
        machine: "surface-pro",
      },
    ],
    [
      "claude:alpha@surface-pro",
      {
        address: "claude:alpha@surface-pro",
        provider: "claude",
        name: "alpha",
        machine: "surface-pro",
      },
    ],
    [
      "codex:alpha.v2_x-1@Surface-Pro",
      {
        address: "codex:alpha.v2_x-1@Surface-Pro",
        provider: "codex",
        name: "alpha.v2_x-1",
        machine: "Surface-Pro",
      },
    ],
  ];
  for (const [input, expected] of cases) {
    assert.deepEqual(mailboxCore.canonicalizeMailboxAddress(input), expected, input);
  }
});

test("provider-qualified addresses parse through the shared mailbox parser", () => {
  assert.deepEqual(parseMailboxAddress("claude:alpha"), {
    address: "claude:alpha",
    provider: "claude",
    name: "alpha",
  });
  assert.deepEqual(parseMailboxAddress("codex:alpha@surface-pro"), {
    address: "codex:alpha@surface-pro",
    provider: "codex",
    name: "alpha",
    machine: "surface-pro",
  });
});

test("malformed provider and machine forms are rejected by parser and canonicalizer", () => {
  const malformed = [
    "gemini:alpha",
    "Claude:alpha",
    "CODEX:alpha",
    "copilot :alpha",
    " claude:alpha",
    "claude:alpha ",
    "claude: alpha",
    "claude:alpha\n",
    "claude:",
    ":alpha",
    "codex:",
    "copilot:",
    "claude::alpha",
    "claude:alpha:beta",
    "claude:alpha@",
    "claude:@surface-pro",
    "claude:alpha@surface@pro",
    "claude:alpha@surface pro",
    "claude:alpha@surface/pro",
    "claude:alpha@surface\\pro",
    "claude:alpha@surface:pro",
    "@claude:alpha",
    "claude@alpha:beta",
    "claude:../alpha",
    "claude:alpha/beta",
    "codex:alpha\\beta",
    "claude:_alpha",
    "claude:.alpha",
    "_providers/claude/alpha",
    "claude:" + "a".repeat(129),
    "",
    undefined,
    null,
    42,
    {},
  ];
  assert.equal(typeof mailboxCore.canonicalizeMailboxAddress, "function");
  for (const address of malformed) {
    assert.throws(() => parseMailboxAddress(address), undefined, String(address));
    assert.throws(
      () => mailboxCore.canonicalizeMailboxAddress(address),
      undefined,
      String(address),
    );
  }
});

// ---------------------------------------------------------------------------
// (2) Windows-safe path keys for mailbox directories and state paths
// ---------------------------------------------------------------------------

test("path keys preserve bare Copilot and isolate providers under _providers", () => {
  assert.equal(typeof mailboxCore.mailboxPathKey, "function");
  const normalize = (key) => key.replaceAll("\\", "/");
  const expected = {
    alpha: "alpha",
    "copilot:alpha": "alpha",
    "alpha@surface": "alpha@surface",
    "copilot:alpha@surface": "alpha@surface",
    "claude:alpha": "_providers/claude/alpha",
    "claude:alpha@surface": "_providers/claude/alpha@surface",
    "codex:alpha": "_providers/codex/alpha",
    "codex:alpha@surface": "_providers/codex/alpha@surface",
  };
  for (const [address, key] of Object.entries(expected)) {
    assert.equal(normalize(mailboxCore.mailboxPathKey(address)), key, address);
  }
  const keys = Object.values(expected).map(normalize);
  for (const key of keys) {
    for (const segment of key.split("/")) {
      assert.match(segment, /^[A-Za-z0-9_][A-Za-z0-9._@-]*$/, key);
      assert.doesNotMatch(segment, /[<>:"|?*\\/]/, key);
      assert.doesNotMatch(segment, /[. ]$/, key);
    }
  }
});

test("mailbox directories use path keys and never create colon paths", async () => {
  await sandbox("directories", async (root) => {
    const mailbox = providerMailbox(root, {});
    const sent = {};
    for (const recipient of ["alpha", "copilot:alpha", "claude:alpha", "codex:alpha"]) {
      sent[recipient] = await mailbox.send({
        recipient,
        sender: "whisky",
        summary: `to ${recipient}`,
        message: `body for ${recipient}`,
        wake: false,
      });
    }
    const files = await listFiles(join(root, "mailbox"));
    const pendingFor = (key) =>
      files.filter((path) => path.startsWith(`${key}/pending/`) && path.endsWith(".json"));

    assert.equal(pendingFor("alpha").length, 2, "bare and copilot: share the legacy directory");
    assert.equal(pendingFor("_providers/claude/alpha").length, 1);
    assert.equal(pendingFor("_providers/codex/alpha").length, 1);
    assert.ok(files.every((path) => !path.includes(":")), files.join("\n"));

    assert.equal((await mailbox.check("alpha")).length, 2);
    assert.equal((await mailbox.check("copilot:alpha")).length, 2);
    assert.deepEqual(
      (await mailbox.check("claude:alpha")).map(({ envelope }) => envelope.id),
      [sent["claude:alpha"].envelope.id],
    );
    assert.deepEqual(
      (await mailbox.check("codex:alpha")).map(({ envelope }) => envelope.id),
      [sent["codex:alpha"].envelope.id],
    );
    assert.deepEqual(sent["claude:alpha"].envelope.to, providerTo("claude", "alpha"));
    assert.deepEqual(sent["codex:alpha"].envelope.to, providerTo("codex", "alpha"));
    assert.ok(
      (await mailbox.list()).every(({ name }) => name !== "_providers"),
      "the provider container directory is not a mailbox",
    );
  });
});

test("every provider-qualified state path uses the shared path key", async () => {
  await sandbox("state-paths", async (root) => {
    const stateRoot = join(root, "state");
    const requestMock = await writeRequestMock(root, { stateRoot });
    let during;
    const claude = recordingAdapter(async () => {
      during = await listFiles(stateRoot);
      return { outcome: "submitted", detail: "socket accepted" };
    });
    const mailbox = providerMailbox(root, { claude }, { requestCli: requestMock.script });
    const bare = await mailbox.send({
      recipient: "alpha",
      sender: "whisky",
      summary: "bare Copilot twin",
      message: "must stay untouched",
      wake: false,
    });
    const sent = await mailbox.send({
      recipient: "claude:alpha",
      sender: "whisky",
      summary: "claude mail",
      message: "claude only",
      wake: false,
    });
    const id = sent.envelope.id;
    const key = "_providers/claude/alpha";
    await mkdir(join(stateRoot, "watermarks", "_providers", "claude"), { recursive: true });
    await writeFile(join(stateRoot, "watermarks", "alpha.txt"), `${id}\n`);

    await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });

    assert.equal(claude.calls.length, 1, "bare watermark must not suppress the provider mailbox");
    for (const path of [
      `watchers/${key}.lock`,
      `notifying/${key}.lock`,
      `notified/${key}/${id}.attempt`,
    ]) {
      assert.ok(during.includes(path), `${path} missing from ${during.join(", ")}`);
    }
    const after = await listFiles(stateRoot);
    assert.ok(after.includes(`notified/${key}/${id}.unverified`), after.join(", "));
    const durable = after.filter((path) => !/^(logs|tmp)\//.test(path));
    for (const path of [...durable, ...during]) {
      assert.doesNotMatch(path, /:/);
      assert.doesNotMatch(path, /^(watchers|notifying|notified)\/(claude|codex|copilot)/);
    }
    assert.ok(!during.some((path) => /^(watchers|notifying)\/alpha\.lock$/.test(path)));
    assert.ok(!after.some((path) => path.startsWith("notified/alpha/")));
    assert.deepEqual(await requestMock.calls(), [], "Claude never reaches session-control");
    assert.equal((await mailbox.check("alpha")).length, 1);
    assert.equal((await mailbox.check("alpha"))[0].envelope.id, bare.envelope.id);

    // A legacy-style watermark under the provider key suppresses only that provider.
    const second = await mailbox.send({
      recipient: "claude:alpha",
      sender: "whisky",
      summary: "watermarked",
      message: "already seen",
      wake: false,
    });
    await mkdir(join(stateRoot, "watermarks", "_providers", "claude"), { recursive: true });
    await writeFile(
      join(stateRoot, "watermarks", "_providers", "claude", "alpha.txt"),
      `${second.envelope.id}\n`,
    );
    const before = claude.calls.length;
    await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
    assert.equal(claude.calls.length, before, "watermark under the provider key is honored");
  });
});

test("legacy bare Copilot keeps its original mailbox and state paths", async () => {
  await sandbox("legacy-paths", async (root) => {
    const stateRoot = join(root, "state");
    const requestMock = await writeRequestMock(root, { stateRoot });
    const mailbox = providerMailbox(root, {}, { requestCli: requestMock.script });
    const sent = await mailbox.send({
      recipient: "alpha",
      sender: "whisky",
      summary: "legacy",
      message: "legacy body",
      wake: false,
    });
    await mailbox.watch("alpha", { once: true, intervalMs: 100 });

    const during = await requestMock.snapshot();
    for (const path of [
      "watchers/alpha.lock",
      "notifying/alpha.lock",
      `notified/alpha/${sent.envelope.id}.attempt`,
    ]) {
      assert.ok(during.includes(path), `${path} missing from ${during.join(", ")}`);
    }
    assert.match(
      await readFile(notificationFile(root, "alpha", sent.envelope.id, "notified"), "utf8"),
      /^\d{4}-\d{2}-\d{2}T.*Z\n$/,
    );
    assert.ok(
      (await listFiles(join(root, "mailbox"))).includes(
        `alpha/pending/${sent.envelope.id}.json`,
      ),
    );
  });
});

test("explicit copilot: address wakes through session-control with legacy state paths", async () => {
  await sandbox("copilot-explicit", async (root) => {
    const requestMock = await writeRequestMock(root);
    const mailbox = providerMailbox(root, {}, { requestCli: requestMock.script });
    const sent = await mailbox.send({
      recipient: "copilot:alpha",
      sender: "whisky",
      summary: "explicit copilot",
      message: "same mailbox as bare alpha",
      wake: false,
    });
    const result = await mailbox.poke("copilot:alpha");
    assert.equal(result.status, "delivered");
    const calls = await requestMock.calls();
    assert.equal(calls.length, 1);
    assert.equal(calls[0][calls[0].indexOf("--target-name") + 1], "alpha");
    assert.match(
      await readFile(notificationFile(root, "alpha", sent.envelope.id, "notified"), "utf8"),
      /^\d{4}-\d{2}-\d{2}T/,
    );
    assert.equal((await mailbox.check("alpha")).length, 1);
  });
});

// ---------------------------------------------------------------------------
// (3) MAILBOX_SELF_ADDRESS through the mailbox CLI
// ---------------------------------------------------------------------------

function cliEnvironment(root, extra) {
  const env = {};
  for (const [name, value] of Object.entries(process.env)) {
    if (/^(MAILBOX_|COPILOT_AGENT_|COPILOT_MAILBOX_|COPILOT_SESSION_INBOX|CLAUDE_CODE_|TMUX)/i.test(name)) {
      continue;
    }
    env[name] = value;
  }
  return {
    ...env,
    MAILBOX_LOCAL_ROOT: join(root, "mailbox"),
    MAILBOX_STATE_ROOT: join(root, "state"),
    MAILBOX_CONFIG_PATH: join(root, "mailbox-config.json"),
    COPILOT_SESSION_CONTROL_DIR: join(root, "session-control"),
    ...extra,
  };
}

async function writeCliConfiguration(root) {
  await writeFile(
    join(root, "mailbox-config.json"),
    JSON.stringify({
      schemaVersion: 1,
      machineName: "thinkpad",
      remoteMailboxRoot: join(root, "remote"),
    }),
  );
}

function runCli(root, args, extra) {
  return new Promise((resolve) => {
    execFile(
      process.execPath,
      [cliPath, ...args],
      { env: cliEnvironment(root, extra), timeout: 20_000 },
      (error, stdout, stderr) => {
        resolve({ code: error ? (error.code ?? 1) : 0, stdout, stderr });
      },
    );
  });
}

const CLAUDE_ID = "20261103T100000Z-claudeone";
const BARE_ID = "20261103T090000Z-bareone";

async function seedSelfFixtures(root) {
  await writeCliConfiguration(root);
  const mailboxRoot = join(root, "mailbox");
  await writeEnvelopeFile(
    mailboxRoot,
    "_providers/claude/alpha",
    "pending",
    envelopeFor(CLAUDE_ID, providerTo("claude", "alpha"), {
      summary: "claude-only summary",
      message: "claude-only message",
    }),
  );
  await writeEnvelopeFile(
    mailboxRoot,
    "_providers/codex/alpha",
    "pending",
    envelopeFor("20261103T110000Z-codexone", providerTo("codex", "alpha"), {
      summary: "codex-only summary",
      message: "codex-only message",
    }),
  );
  await writeEnvelopeFile(
    mailboxRoot,
    "alpha",
    "pending",
    envelopeFor(BARE_ID, { name: "alpha" }, {
      summary: "bare-copilot summary",
      message: "bare-copilot message",
    }),
  );
}

test("legacy Copilot CLI resolution works without MAILBOX_SELF_ADDRESS", async () => {
  await sandbox("cli-legacy", async (root) => {
    await seedSelfFixtures(root);
    const checked = await runCli(root, ["check"], { COPILOT_AGENT_NAME: "alpha" });
    assert.equal(checked.code, 0, checked.stderr);
    assert.match(checked.stdout, /bare-copilot summary/);
    assert.match(checked.stdout, /mailbox=copilot:alpha\s+from=copilot:whisky/);
    assert.doesNotMatch(checked.stdout, /claude-only|codex-only/);
    const read = await runCli(root, ["read", BARE_ID], { COPILOT_AGENT_NAME: "alpha" });
    assert.equal(read.code, 0, read.stderr);
    assert.match(read.stdout, /bare-copilot message/);
    assert.match(read.stdout, /FROM: copilot:whisky/);
    assert.match(read.stdout, /TO:\s+copilot:alpha/);
  });
});

test("MAILBOX_SELF_ADDRESS selects exact provider mailboxes for check, read, and ack", async () => {
  await sandbox("cli-self-address", async (root) => {
    await seedSelfFixtures(root);
    const trap = { COPILOT_AGENT_NAME: "alpha" };
    const claude = { ...trap, MAILBOX_SELF_ADDRESS: "claude:alpha" };

    const checked = await runCli(root, ["check"], claude);
    assert.equal(checked.code, 0, checked.stderr);
    assert.match(checked.stdout, /claude-only summary/);
    assert.doesNotMatch(checked.stdout, /bare-copilot|codex-only/);

    const explicit = await runCli(root, ["check", "--name", "claude:alpha"], trap);
    assert.equal(explicit.code, 0, explicit.stderr);
    assert.match(explicit.stdout, /claude-only summary/);
    assert.doesNotMatch(explicit.stdout, /bare-copilot|codex-only/);

    const codex = await runCli(root, ["check"], {
      ...trap,
      MAILBOX_SELF_ADDRESS: "codex:alpha",
    });
    assert.equal(codex.code, 0, codex.stderr);
    assert.match(codex.stdout, /codex-only summary/);
    assert.doesNotMatch(codex.stdout, /bare-copilot|claude-only/);

    for (const address of ["copilot:alpha", "alpha"]) {
      const copilot = await runCli(root, ["check"], { MAILBOX_SELF_ADDRESS: address });
      assert.equal(copilot.code, 0, copilot.stderr);
      assert.match(copilot.stdout, /bare-copilot summary/);
      assert.doesNotMatch(copilot.stdout, /claude-only|codex-only/);
    }

    const read = await runCli(root, ["read", CLAUDE_ID], claude);
    assert.equal(read.code, 0, read.stderr);
    assert.match(read.stdout, /claude-only message/);
    const foreignRead = await runCli(root, ["read", BARE_ID], claude);
    assert.notEqual(foreignRead.code, 0);
    assert.doesNotMatch(foreignRead.stdout, /bare-copilot message/);

    const foreignAck = await runCli(root, ["ack", BARE_ID], claude);
    assert.notEqual(foreignAck.code, 0);
    assert.ok(await exists(join(root, "mailbox", "alpha", "pending", `${BARE_ID}.json`)));

    const ack = await runCli(root, ["ack", CLAUDE_ID], claude);
    assert.equal(ack.code, 0, ack.stderr);
    assert.ok(
      await exists(
        join(root, "mailbox", "_providers", "claude", "alpha", "delivered", `${CLAUDE_ID}.json`),
      ),
    );
    assert.ok(await exists(join(root, "mailbox", "alpha", "pending", `${BARE_ID}.json`)));
  });
});

test("MAILBOX_SELF_ADDRESS makes send and reply sender identity provider-qualified", async () => {
  await sandbox("cli-send-reply", async (root) => {
    await writeCliConfiguration(root);
    const claude = { COPILOT_AGENT_NAME: "alpha", MAILBOX_SELF_ADDRESS: "claude:alpha" };
    const sent = await runCli(
      root,
      ["send", "hotel", "--summary", "from claude", "--message", "hello", "--no-wakeup"],
      claude,
    );
    assert.equal(sent.code, 0, sent.stderr);
    const pending = join(root, "mailbox", "hotel", "pending");
    const [name] = (await readdir(pending)).filter((entry) => entry.endsWith(".json"));
    const envelope = JSON.parse(await readFile(join(pending, name), "utf8"));
    assert.equal(envelope.from.address, "claude:alpha");
    assert.equal(envelope.from.provider, "claude");
    assert.equal(envelope.from.name, "alpha");

    // A reply is a send to the sender address recorded in the envelope.
    const reply = await runCli(
      root,
      ["send", envelope.from.address, "--summary", "re: from claude", "--message", "pong", "--no-wakeup"],
      { COPILOT_AGENT_NAME: "hotel" },
    );
    assert.equal(reply.code, 0, reply.stderr);
    const replies = (
      await readdir(join(root, "mailbox", "_providers", "claude", "alpha", "pending"))
    ).filter((entry) => entry.endsWith(".json"));
    assert.equal(replies.length, 1);
    assert.deepEqual((await readdir(join(root, "mailbox"))).sort(), [
      "_providers",
      "hotel",
    ]);

    const codexSend = await runCli(
      root,
      ["send", "claude:alpha", "--summary", "from codex", "--message", "hi", "--no-wakeup"],
      { MAILBOX_SELF_ADDRESS: "codex:beta" },
    );
    assert.equal(codexSend.code, 0, codexSend.stderr);
    const claudePending = join(root, "mailbox", "_providers", "claude", "alpha", "pending");
    const received = [];
    for (const file of (await readdir(claudePending)).filter((entry) => entry.endsWith(".json"))) {
      received.push(JSON.parse(await readFile(join(claudePending, file), "utf8")));
    }
    assert.ok(received.some(({ from }) => from.address === "codex:beta"));
  });
});

test("MAILBOX_SELF_ADDRESS selects the provider watcher identity", async () => {
  await sandbox("cli-watch", async (root) => {
    await writeCliConfiguration(root);
    const watched = await runCli(root, ["watch", "--once", "--interval", "100"], {
      COPILOT_AGENT_NAME: "alpha",
      MAILBOX_SELF_ADDRESS: "claude:alpha",
    });
    assert.equal(watched.code, 0, watched.stderr);
    const log = (await readFile(join(root, "state", "logs", "mailbox.jsonl"), "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const started = log.filter(({ event }) => event === "watcher.started");
    assert.deepEqual(
      started.map(({ mailbox }) => mailbox),
      ["claude:alpha"],
    );
  });
});

test("invalid MAILBOX_SELF_ADDRESS fails closed for every receiver command", async () => {
  await sandbox("cli-invalid-self", async (root) => {
    await seedSelfFixtures(root);
    const invalid = [
      "claude:",
      "codex:",
      ":alpha",
      "gemini:alpha",
      "Claude:alpha",
      "claude:alpha:beta",
      "claude:bad name",
      "codex:../alpha",
      "bad name",
    ];
    const commands = [
      ["check"],
      ["read", BARE_ID],
      ["ack", BARE_ID],
      ["send", "hotel", "--summary", "s", "--message", "m", "--no-wakeup"],
      ["watch", "--once", "--interval", "100"],
    ];
    for (const address of invalid) {
      for (const args of commands) {
        const result = await runCli(root, args, {
          COPILOT_AGENT_NAME: "alpha",
          MAILBOX_SELF_ADDRESS: address,
        });
        assert.notEqual(result.code, 0, `${args[0]} accepted ${address}`);
        assert.match(result.stderr, /MAILBOX_SELF_ADDRESS/, `${args[0]} ${address}`);
        assert.doesNotMatch(result.stdout, /bare-copilot/);
      }
    }
    assert.ok(await exists(join(root, "mailbox", "alpha", "pending", `${BARE_ID}.json`)));
    assert.deepEqual(await listFiles(join(root, "mailbox", "hotel")), []);
  });
});

test("a Claude session without MAILBOX_SELF_ADDRESS never falls back to a bare name", async () => {
  await sandbox("cli-missing-self", async (root) => {
    await seedSelfFixtures(root);
    // CLAUDE_CODE_MESSAGING_SOCKET is Claude's documented hook environment;
    // it identifies a non-Copilot process that lacks a provider self address.
    const environment = {
      COPILOT_AGENT_NAME: "alpha",
      CLAUDE_CODE_MESSAGING_SOCKET: join(root, "not-a-real-socket"),
    };
    for (const args of [
      ["check"],
      ["read", BARE_ID],
      ["ack", BARE_ID],
      ["send", "hotel", "--summary", "s", "--message", "m", "--no-wakeup"],
      ["watch", "--once", "--interval", "100"],
    ]) {
      const result = await runCli(root, args, environment);
      assert.notEqual(result.code, 0, `${args[0]} fell back to a bare name`);
      assert.match(result.stderr, /MAILBOX_SELF_ADDRESS/, args[0]);
      assert.doesNotMatch(result.stdout, /bare-copilot/);
    }
    assert.ok(await exists(join(root, "mailbox", "alpha", "pending", `${BARE_ID}.json`)));
    assert.deepEqual(await listFiles(join(root, "mailbox", "hotel")), []);
  });
});

// ---------------------------------------------------------------------------
// (4) Notification markers and structured wakeup outcomes
// ---------------------------------------------------------------------------

async function sendProviderMail(mailbox, recipient, wake = false) {
  return mailbox.send({
    recipient,
    sender: "whisky",
    summary: "wakeup state",
    message: "durable body",
    wake,
  });
}

test("terminal provider outcomes write structured .unverified markers and never replay", async () => {
  for (const outcome of ["submitted", "held", "refused", "ambiguous"]) {
    await sandbox(`outcome-${outcome}`, async (root) => {
      const adapter = recordingAdapter({ outcome, detail: `provider said ${outcome}` });
      const mailbox = providerMailbox(root, { claude: adapter });
      const sent = await sendProviderMail(mailbox, "claude:alpha", true);
      const id = sent.envelope.id;
      const key = "_providers/claude/alpha";

      assert.equal(adapter.calls.length, 1, outcome);
      const request = adapter.calls[0];
      assert.equal(request.address, "claude:alpha");
      assert.equal(request.provider, "claude");
      assert.equal(request.name, "alpha");
      assert.equal(request.envelopeId, id);
      assert.equal(typeof request.attemptId, "string");
      assert.ok(request.attemptId.length > 0);
      assert.match(request.prompt, POSITIVE_PROMPT);
      assert.equal(sent.wakeup.outcome, outcome);
      assert.notEqual(sent.wakeup.status, "delivered", "only verified is delivered");

      const marker = JSON.parse(
        await readFile(notificationFile(root, key, id, "unverified"), "utf8"),
      );
      assert.equal(marker.version, 1);
      assert.equal(marker.attemptId, request.attemptId);
      assert.equal(marker.outcome, outcome);
      assert.equal(marker.detail, `provider said ${outcome}`);
      assert.ok(Number.isFinite(Date.parse(marker.updatedAt)), "updatedAt is a timestamp");
      assert.equal(await exists(notificationFile(root, key, id, "notified")), false);
      assert.equal((await mailbox.check("claude:alpha")).length, 1, "envelope stays pending");

      await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
      await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
      const again = await mailbox.poke("claude:alpha");
      assert.equal(adapter.calls.length, 1, `${outcome} must not replay on a later tick`);
      assert.equal(again.outcome, outcome, "sender reports the recorded outcome");
      assert.equal(again.envelopeId, id);
    });
  }
});

test("provider preparation precedes attempting and interrupted submission becomes ambiguous", async () => {
  await sandbox("outcome-attempting", async (root) => {
    let preparedWithoutMarker = false;
    let wokeWithAttempting = false;
    const adapter = {
      calls: 0,
      async prepare(request) {
        preparedWithoutMarker = !(await exists(
          notificationFile(
            root,
            "_providers/claude/alpha",
            request.envelopeId,
            "unverified",
          ),
        ));
        return { prepared: true };
      },
      async wake(request) {
        this.calls += 1;
        const marker = JSON.parse(
          await readFile(
            notificationFile(
              root,
              "_providers/claude/alpha",
              request.envelopeId,
              "unverified",
            ),
            "utf8",
          ),
        );
        wokeWithAttempting =
          marker.outcome === "attempting" && marker.attemptId === request.attemptId;
        throw Object.assign(new Error("synthetic transport loss"), {
          code: "ECONNRESET",
        });
      },
    };
    const mailbox = providerMailbox(root, { claude: adapter });
    const sent = await sendProviderMail(mailbox, "claude:alpha", true);
    const marker = JSON.parse(
      await readFile(
        notificationFile(
          root,
          "_providers/claude/alpha",
          sent.envelope.id,
          "unverified",
        ),
        "utf8",
      ),
    );

    assert.equal(preparedWithoutMarker, true);
    assert.equal(wokeWithAttempting, true);
    assert.equal(sent.wakeup.outcome, "ambiguous");
    assert.equal(marker.outcome, "ambiguous");
    assert.equal(adapter.calls, 1);
    await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
    assert.equal(adapter.calls, 1, "an interrupted attempt must never replay");
  });
});

test("a stale attempting marker is promoted to ambiguous without replay", async () => {
  await sandbox("outcome-stale-attempting", async (root) => {
    const adapter = recordingAdapter({ outcome: "verified" });
    const mailbox = providerMailbox(root, { claude: adapter });
    const sent = await sendProviderMail(mailbox, "claude:alpha", false);
    const path = notificationFile(
      root,
      "_providers/claude/alpha",
      sent.envelope.id,
      "unverified",
    );
    await mkdir(dirname(path), { recursive: true });
    await writeFile(
      path,
      `${JSON.stringify({
        version: 1,
        attemptId: "interrupted-attempt",
        outcome: "attempting",
        detail: "submission in progress",
        updatedAt: new Date().toISOString(),
      })}\n`,
      { flag: "wx" },
    );

    const outcome = await mailbox.poke("claude:alpha");
    const marker = JSON.parse(await readFile(path, "utf8"));
    assert.equal(outcome.outcome, "ambiguous");
    assert.equal(marker.outcome, "ambiguous");
    assert.equal(marker.attemptId, "interrupted-attempt");
    assert.equal(adapter.calls.length, 0);
  });
});

test("a later envelope after a terminal outcome starts a new attempt", async () => {
  await sandbox("outcome-new-envelope", async (root) => {
    const adapter = recordingAdapter([
      { outcome: "held", detail: "first held" },
      { outcome: "verified" },
    ]);
    const mailbox = providerMailbox(root, { claude: adapter });
    const first = await sendProviderMail(mailbox, "claude:alpha", true);
    const second = await sendProviderMail(mailbox, "claude:alpha", true);
    assert.equal(adapter.calls.length, 2);
    assert.equal(adapter.calls[1].envelopeId, second.envelope.id);
    assert.equal(second.wakeup.outcome, "verified");
    const key = "_providers/claude/alpha";
    for (const id of [first.envelope.id, second.envelope.id]) {
      assert.match(
        await readFile(notificationFile(root, key, id, "notified"), "utf8"),
        /^\d{4}-\d{2}-\d{2}T.*Z\n$/,
      );
      assert.equal(await exists(notificationFile(root, key, id, "unverified")), false);
    }
  });
});

test("verified provider outcome keeps the compatible .notified marker", async () => {
  await sandbox("outcome-verified", async (root) => {
    const adapter = recordingAdapter({ outcome: "verified" });
    const mailbox = providerMailbox(root, { codex: adapter });
    const sent = await sendProviderMail(mailbox, "codex:alpha", true);
    const id = sent.envelope.id;
    const key = "_providers/codex/alpha";
    assert.equal(sent.wakeup.outcome, "verified");
    assert.equal(sent.wakeup.status, "delivered");
    assert.match(
      await readFile(notificationFile(root, key, id, "notified"), "utf8"),
      /^\d{4}-\d{2}-\d{2}T.*Z\n$/,
    );
    assert.equal(await exists(notificationFile(root, key, id, "unverified")), false);
    assert.equal(await exists(notificationFile(root, key, id, "attempt")), false);
    await mailbox.watch("codex:alpha", { once: true, intervalMs: 100 });
    assert.equal(adapter.calls.length, 1);
    assert.equal((await mailbox.poke("codex:alpha")).status, "already-poked");
  });
});

test("deferred outcome writes no marker and retries on a later watch tick", async () => {
  await sandbox("outcome-deferred", async (root) => {
    const adapter = recordingAdapter([
      { outcome: "deferred", detail: "endpoint busy" },
      { outcome: "deferred", detail: "endpoint busy" },
      { outcome: "verified" },
    ]);
    const mailbox = providerMailbox(root, { claude: adapter });
    const sent = await sendProviderMail(mailbox, "claude:alpha", false);
    const id = sent.envelope.id;
    const key = "_providers/claude/alpha";
    const markers = async () =>
      (await listFiles(join(root, "state", "notified"))).filter((path) =>
        /\.(notified|unverified)$/.test(path),
      );

    await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
    assert.equal(adapter.calls.length, 1);
    assert.deepEqual(await markers(), []);
    await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
    assert.equal(adapter.calls.length, 2, "deferred retries automatically");
    assert.deepEqual(await markers(), []);
    assert.equal((await mailbox.check("claude:alpha")).length, 1);
    await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
    assert.equal(adapter.calls.length, 3);
    assert.ok(await exists(notificationFile(root, key, id, "notified")));
    await mailbox.watch("claude:alpha", { once: true, intervalMs: 100 });
    assert.equal(adapter.calls.length, 3, "verified stops retries");
    assert.ok(adapter.calls.every((call) => call.envelopeId === id));
  });
});

test("deferred outcome removes attempting before an ownership handoff", async () => {
  await sandbox("outcome-deferred-handoff", async (root) => {
    const adapter = recordingAdapter({
      outcome: "deferred",
      detail: "definitive pre-submission refusal",
    });
    const mailbox = providerMailbox(root, { claude: adapter });
    const sent = await sendProviderMail(mailbox, "claude:alpha", false);
    const outcome = await mailbox.poke("claude:alpha", {
      ownershipGuard: async () => false,
    });

    assert.equal(outcome.outcome, "deferred");
    assert.equal(outcome.releaseWatcher, true);
    assert.equal(
      await exists(
        notificationFile(
          root,
          "_providers/claude/alpha",
          sent.envelope.id,
          "unverified",
        ),
      ),
      false,
    );
  });
});

test("provider mail without a registered adapter stays deferred and never reaches Copilot", async () => {
  await sandbox("outcome-no-adapter", async (root) => {
    const requestMock = await writeRequestMock(root);
    const mailbox = providerMailbox(root, {}, { requestCli: requestMock.script });
    await mailbox.send({
      recipient: "alpha",
      sender: "whisky",
      summary: "bare twin",
      message: "bare",
      wake: false,
    });
    await sendProviderMail(mailbox, "codex:alpha", false);
    const result = await mailbox.poke("codex:alpha");
    assert.equal(result.outcome, "deferred");
    assert.deepEqual(await requestMock.calls(), []);
    assert.deepEqual(await listFiles(join(root, "state", "notified")), []);
    assert.equal((await mailbox.check("codex:alpha")).length, 1);
    assert.equal((await mailbox.check("alpha")).length, 1);
  });
});

test("provider terminal fallback holds the notification claim against the native watcher", async () => {
  await sandbox("fallback-claim", async (root) => {
    const started = join(root, "fallback-started");
    const release = join(root, "fallback-release");
    const helper = join(root, "terminal-poke.sh");
    await writeFile(
      helper,
      `#!/bin/sh
: > '${started}'
while [ ! -f '${release}' ]; do sleep 0.01; done
echo 'poked: claude:alpha (submission observed)'
`,
      { mode: 0o700 },
    );
    const terminal = providerMailbox(root, {}, {
      extra: { terminalPokeCli: helper },
    });
    const adapter = recordingAdapter({ outcome: "verified" });
    const watcher = providerMailbox(root, { claude: adapter });
    await sendProviderMail(terminal, "claude:alpha", false);

    const fallbackResult = terminal.poke("claude:alpha", {
      targetName: "claude-alpha",
    });
    for (let attempt = 0; attempt < 100 && !(await exists(started)); attempt += 1) {
      await sleep(10);
    }
    assert.ok(await exists(started), "terminal fallback did not start");

    const watcherResult = await watcher.poke("claude:alpha", {
      targetName: "alpha",
    });
    assert.equal(watcherResult.status, "in-progress");
    assert.equal(adapter.calls.length, 0, "native watcher submitted a duplicate wakeup");

    await writeFile(release, "");
    assert.equal((await fallbackResult).status, "delivered");
    assert.equal(adapter.calls.length, 0);
  });
});

test("provider terminal interruption after submission begins is durably unverified", async () => {
  await sandbox("fallback-interrupted", async (root) => {
    const helper = join(root, "terminal-poke.sh");
    await writeFile(
      helper,
      `#!/bin/sh
echo 'MAILBOX_TERMINAL_PHASE=SUBMITTING' >&2
exit 3
`,
      { mode: 0o700 },
    );
    const mailbox = providerMailbox(root, {}, {
      extra: { terminalPokeCli: helper },
    });
    const sent = await sendProviderMail(mailbox, "claude:alpha", false);

    const result = await mailbox.poke("claude:alpha", {
      targetName: "claude-alpha",
    });
    assert.equal(result.status, "unverified");
    assert.equal(result.outcome, "ambiguous");
    assert.ok(
      await exists(
        notificationFile(
          root,
          "_providers/claude/alpha",
          sent.envelope.id,
          "unverified",
        ),
      ),
    );
    assert.equal((await mailbox.poke("claude:alpha")).status, "unverified");
  });
});

test("provider terminal send failure before input remains retryable", async () => {
  await sandbox("fallback-send-failed", async (root) => {
    const helper = join(root, "terminal-poke.sh");
    await writeFile(
      helper,
      `#!/bin/sh
echo 'MAILBOX_TERMINAL_PHASE=SUBMITTING' >&2
echo 'UNVERIFIED: target disappeared before the poke could be entered; the mail is queued.' >&2
exit 3
`,
      { mode: 0o700 },
    );
    const mailbox = providerMailbox(root, {}, {
      extra: { terminalPokeCli: helper },
    });
    const sent = await sendProviderMail(mailbox, "claude:alpha", false);

    const result = await mailbox.poke("claude:alpha", {
      targetName: "claude-alpha",
    });
    assert.equal(result.status, "fallback-deferred");
    assert.equal(result.outcome, "deferred");
    assert.equal(
      await exists(
        notificationFile(
          root,
          "_providers/claude/alpha",
          sent.envelope.id,
          "unverified",
        ),
      ),
      false,
    );
  });
});

test("Copilot ambiguous wakeups record a structured .unverified outcome", async () => {
  await sandbox("copilot-ambiguous", async (root) => {
    const requestMock = await writeRequestMock(root, {
      stdout: '{"status":"completed","result":{"delivery":"unconfirmed"}}',
    });
    const mailbox = providerMailbox(root, {}, { requestCli: requestMock.script });
    const sent = await mailbox.send({
      recipient: "alpha",
      sender: "whisky",
      summary: "ambiguous",
      message: "older extension",
      wake: false,
    });
    assert.equal((await mailbox.poke("alpha")).status, "unverified");
    const attemptId = (
      await readFile(notificationFile(root, "alpha", sent.envelope.id, "attempt"), "utf8")
    ).trim();
    const marker = JSON.parse(
      await readFile(notificationFile(root, "alpha", sent.envelope.id, "unverified"), "utf8"),
    );
    assert.equal(marker.version, 1);
    assert.equal(marker.attemptId, attemptId);
    assert.equal(marker.outcome, "ambiguous");
    assert.equal((await mailbox.poke("alpha")).status, "unverified");
    assert.equal((await requestMock.calls()).length, 1);
  });
});

test("legacy .unverified and .notified markers still suppress replay", async () => {
  await sandbox("legacy-markers", async (root) => {
    const requestMock = await writeRequestMock(root);
    const mailbox = providerMailbox(root, {}, { requestCli: requestMock.script });
    const unverified = await mailbox.send({
      recipient: "alpha",
      sender: "whisky",
      summary: "legacy unverified",
      message: "old marker",
      wake: false,
    });
    const notified = await mailbox.send({
      recipient: "alpha",
      sender: "whisky",
      summary: "legacy notified",
      message: "old marker",
      wake: false,
    });
    const directory = join(root, "state", "notified", "alpha");
    await mkdir(directory, { recursive: true });
    await writeFile(join(directory, `${unverified.envelope.id}.unverified`), "1700000000-abcd\n");
    await writeFile(join(directory, `${notified.envelope.id}.notified`), "2026-11-01T00:00:00.000Z\n");

    const result = await mailbox.poke("alpha");
    assert.equal(result.status, "unverified", "legacy attempt-ID marker is still honored");
    assert.deepEqual(await requestMock.calls(), []);
    assert.equal(
      await readFile(join(directory, `${notified.envelope.id}.notified`), "utf8"),
      "2026-11-01T00:00:00.000Z\n",
    );
  });
});

test("provider .notified markers from earlier writers still suppress replay", async () => {
  await sandbox("provider-legacy-marker", async (root) => {
    const adapter = recordingAdapter({ outcome: "verified" });
    const providerBox = providerMailbox(root, { codex: adapter });
    const provider = await sendProviderMail(providerBox, "codex:alpha", false);
    const providerDirectory = join(root, "state", "notified", "_providers", "codex", "alpha");
    await mkdir(providerDirectory, { recursive: true });
    await writeFile(
      join(providerDirectory, `${provider.envelope.id}.notified`),
      "2026-11-01T00:00:00.000Z\n",
    );
    assert.equal((await providerBox.poke("codex:alpha")).status, "already-poked");
    assert.equal(adapter.calls.length, 0);
  });
});

// ---------------------------------------------------------------------------
// (5) Provider-qualified remote publish and import
// ---------------------------------------------------------------------------

test("provider-qualified remote mail publishes and imports exactly once beside bare Copilot", async () => {
  await sandbox("remote", async (root) => {
    const remoteMailboxRoot = join(root, "remote");
    const requestMock = await writeRequestMock(root);
    const attachment = join(root, "proof.txt");
    await writeFile(attachment, "attachment bytes");
    const sender = createMailbox({
      mailboxRoot: join(root, "sender-mailbox"),
      remoteMailboxRoot,
      stateRoot: join(root, "sender-state"),
      machineName: "desktop",
      requestCli: requestMock.script,
      terminalPokeCli: null,
    });
    const recipients = ["alpha@surface-pro", "claude:alpha@surface-pro", "codex:alpha@surface-pro"];
    const sent = {};
    for (const recipient of recipients) {
      sent[recipient] = await sender.send({
        recipient,
        sender: "whisky",
        summary: `to ${recipient}`,
        message: `body ${recipient}`,
        files: recipient.startsWith("claude:") ? [attachment] : [],
      });
    }
    assert.deepEqual(sent["claude:alpha@surface-pro"].envelope.to, {
      ...providerTo("claude", "alpha", "surface-pro"),
    });
    assert.deepEqual(sent["codex:alpha@surface-pro"].envelope.to, {
      ...providerTo("codex", "alpha", "surface-pro"),
    });
    for (const recipient of recipients) {
      assert.equal(sent[recipient].wakeup.status, "remote-pending", recipient);
    }
    assert.deepEqual(await requestMock.calls(), []);

    const published = await listFiles(remoteMailboxRoot);
    const remoteKey = (recipient) =>
      mailboxCore.mailboxPathKey(recipient).replaceAll("\\", "/");
    for (const recipient of recipients) {
      assert.ok(
        published.includes(`${remoteKey(recipient)}/pending/${sent[recipient].envelope.id}.json`),
        `${recipient} not published under its path key:\n${published.join("\n")}`,
      );
    }
    assert.ok(
      published.includes(
        `_providers/claude/alpha@surface-pro/pending/${sent["claude:alpha@surface-pro"].envelope.id}/proof.txt`,
      ),
    );
    assert.ok(published.every((path) => !path.includes(":")));

    const snapshot = async () =>
      new Map(
        await Promise.all(
          (await listFiles(remoteMailboxRoot)).map(async (path) => [
            path,
            (await readFile(join(remoteMailboxRoot, ...path.split("/")))).toString("base64"),
          ]),
        ),
      );
    const remoteBefore = await snapshot();

    const recipient = createMailbox({
      mailboxRoot: join(root, "recipient-mailbox"),
      remoteMailboxRoot,
      stateRoot: join(root, "recipient-state"),
      machineName: "surface-pro",
      requestCli: requestMock.script,
      terminalPokeCli: null,
    });
    for (const address of recipients) {
      const first = await recipient.importRemote(address);
      if (address.startsWith("claude:")) {
        assert.equal(first, 0, `attachment must stabilize before import ${address}`);
        assert.equal(await recipient.importRemote(address), 1, `stable import ${address}`);
      } else {
        assert.equal(first, 1, `first import ${address}`);
      }
      assert.equal(await recipient.importRemote(address), 0, `repeat import ${address}`);
    }

    const localFiles = await listFiles(join(root, "recipient-mailbox"));
    for (const local of ["alpha", "claude:alpha", "codex:alpha"]) {
      const remoteAddress = local === "alpha" ? "alpha@surface-pro" : `${local}@surface-pro`;
      const checked = await recipient.check(local);
      assert.deepEqual(
        checked.map(({ envelope }) => envelope.id),
        [sent[remoteAddress].envelope.id],
        `${local} imports only its own mail`,
      );
      assert.ok(
        localFiles.includes(
          `${remoteKey(local)}/pending/${sent[remoteAddress].envelope.id}.json`,
        ),
        local,
      );
    }
    assert.deepEqual((await recipient.check("claude:alpha"))[0].envelope.to, {
      ...providerTo("claude", "alpha"),
    });
    assert.equal(
      (await recipient.read("claude:alpha", sent["claude:alpha@surface-pro"].envelope.id))
        .envelope.message,
      "body claude:alpha@surface-pro",
    );
    assert.equal(
      await readFile(
        join(
          root,
          "recipient-mailbox",
          "_providers",
          "claude",
          "alpha",
          "pending",
          sent["claude:alpha@surface-pro"].envelope.id,
          "proof.txt",
        ),
        "utf8",
      ),
      "attachment bytes",
    );
    assert.ok(localFiles.every((path) => !path.includes(":")));
    assert.ok(
      (await listFiles(join(root, "recipient-state"))).filter((path) => path.includes("remote-imported")).length === 3,
      "one import marker per address",
    );
    assert.deepEqual(await snapshot(), remoteBefore, "import never mutates remote bytes");

    for (const address of ["claude:alpha", "codex:alpha", "alpha"]) {
      const [{ envelope }] = await recipient.check(address);
      await recipient.acknowledge(address, envelope.id);
    }
    for (const address of recipients) {
      assert.equal(await recipient.importRemote(address), 0, `re-import after ack ${address}`);
    }
    for (const address of ["claude:alpha", "codex:alpha", "alpha"]) {
      assert.equal((await recipient.check(address)).length, 0, address);
    }

    const remoteAfter = await snapshot();
    for (const [path, bytes] of remoteBefore) {
      assert.equal(remoteAfter.get(path), bytes, `${path} is immutable`);
    }
    const added = [...remoteAfter.keys()].filter((path) => !remoteBefore.has(path));
    assert.deepEqual(
      added,
      recipients.map((address) => `receipts/${remoteKey(address)}/${sent[address].envelope.id}.json`).sort(),
    );
    for (const path of remoteAfter.keys()) {
      assert.doesNotMatch(
        path,
        /\.(notified|unverified|attempt|lock|imported|tmp)$|\.uploading-|watchers|notifying|watermarks|remote-imported/,
        `mutable state leaked into the remote root: ${path}`,
      );
    }
  });
});

test("remote outbox retry preserves provider identity beside bare Copilot", async () => {
  await sandbox("remote-outbox", async (root) => {
    const remoteMailboxRoot = join(root, "remote");
    const stateRoot = join(root, "state");
    await writeFile(remoteMailboxRoot, "temporarily unavailable");
    const mailbox = createMailbox({
      mailboxRoot: join(root, "mailbox"),
      remoteMailboxRoot,
      stateRoot,
      machineName: "desktop",
      terminalPokeCli: null,
    });
    const recipients = ["alpha@surface-pro", "claude:alpha@surface-pro", "codex:alpha@surface-pro"];
    const sent = {};
    for (const recipient of recipients) {
      sent[recipient] = await mailbox.send({
        recipient,
        sender: "whisky",
        summary: recipient,
        message: `outage ${recipient}`,
        wake: false,
      });
    }
    const outbox = await listFiles(join(stateRoot, "remote-outbox", "envelopes"));
    for (const [recipient, key] of [
      ["alpha@surface-pro", "alpha@surface-pro"],
      ["claude:alpha@surface-pro", "_providers/claude/alpha@surface-pro"],
      ["codex:alpha@surface-pro", "_providers/codex/alpha@surface-pro"],
    ]) {
      assert.ok(
        outbox.includes(`${key}/${sent[recipient].envelope.id}.json`),
        `${recipient} missing from outbox: ${outbox.join(", ")}`,
      );
    }
    assert.ok(outbox.every((path) => !path.includes(":")));

    await rm(remoteMailboxRoot);
    await mkdir(remoteMailboxRoot);
    await mailbox.flushRemoteOutbox();
    const published = await listFiles(remoteMailboxRoot);
    for (const [recipient, key] of [
      ["alpha@surface-pro", "alpha@surface-pro"],
      ["claude:alpha@surface-pro", "_providers/claude/alpha@surface-pro"],
      ["codex:alpha@surface-pro", "_providers/codex/alpha@surface-pro"],
    ]) {
      assert.ok(
        published.includes(`${key}/pending/${sent[recipient].envelope.id}.json`),
        `${recipient} was not republished: ${published.join(", ")}`,
      );
    }
    assert.deepEqual(await listFiles(join(stateRoot, "remote-outbox", "envelopes")), []);
  });
});

// ---------------------------------------------------------------------------
// (6) Watcher lock generation semantics
// ---------------------------------------------------------------------------

async function readLockOwner(root, key) {
  try {
    return JSON.parse(
      await readFile(join(root, "state", "watchers", ...`${key}.lock`.split("/")), "utf8"),
    );
  } catch (error) {
    if (error?.code === "ENOENT" || error instanceof SyntaxError) return undefined;
    throw error;
  }
}

const WATCH_KEY = "_providers/claude/alpha";

function startWatcher(mailbox, generation, controller) {
  return trackSettled(
    mailbox.watch("claude:alpha", {
      generation,
      intervalMs: 100,
      signal: controller.signal,
    }),
  );
}

async function waitForOwner(root, generation, watcher) {
  return waitFor(`watcher lock owned by ${generation}`, async () => {
    if (watcher?.error) throw watcher.error;
    const owner = await readLockOwner(root, WATCH_KEY);
    return owner?.generation === generation ? owner : undefined;
  });
}

test("legacy Copilot watcher locks still reject a duplicate without a generation", async () => {
  await sandbox("lock-legacy", async (root) => {
    const first = providerMailbox(root, {});
    const second = providerMailbox(root, {});
    const controller = new AbortController();
    const watching = trackSettled(
      first.watch("alpha", { intervalMs: 100, signal: controller.signal }),
    );
    await waitFor("legacy lock", () => exists(join(root, "state", "watchers", "alpha.lock")));
    await assert.rejects(
      second.watch("alpha", { once: true, intervalMs: 100 }),
      /already running/,
    );
    controller.abort();
    await watching.promise;
  });
});

test("same socket generation reuses the live watcher and the new watcher exits", async () => {
  await sandbox("lock-same-generation", async (root) => {
    const first = recordingAdapter({ outcome: "verified" });
    const second = recordingAdapter({ outcome: "verified" });
    const mailboxA = providerMailbox(root, { claude: first });
    const mailboxB = providerMailbox(root, { claude: second });
    const controller = new AbortController();
    const watchingA = startWatcher(mailboxA, "socket-a", controller);
    const ownerBefore = await waitForOwner(root, "socket-a", watchingA);

    const refire = trackSettled(
      mailboxB.watch("claude:alpha", {
        generation: "socket-a",
        intervalMs: 100,
        signal: new AbortController().signal,
      }),
    );
    await waitFor("duplicate hook watcher exit", () => refire.settled);
    assert.equal(refire.error, undefined, String(refire.error));
    assert.deepEqual(await readLockOwner(root, WATCH_KEY), ownerBefore);
    assert.equal(watchingA.settled, false);

    const sent = await sendProviderMail(mailboxA, "claude:alpha", false);
    await waitFor("acting watcher delivery", () => first.calls.length === 1);
    assert.equal(first.calls[0].envelopeId, sent.envelope.id);
    await sleep(300);
    assert.equal(second.calls.length, 0, "the re-fired hook child never acts");
    assert.equal(first.calls.length, 1);
    controller.abort();
    await watchingA.promise;
    assert.equal(await readLockOwner(root, WATCH_KEY), undefined);
  });
});

test("changed socket generation waits on the existing lock as a non-acting waiter", async () => {
  await sandbox("lock-changed-generation", async (root) => {
    const first = recordingAdapter({ outcome: "verified" });
    const second = recordingAdapter({ outcome: "verified" });
    const mailboxA = providerMailbox(root, { claude: first });
    const mailboxB = providerMailbox(root, { claude: second });
    const controllerA = new AbortController();
    const controllerB = new AbortController();
    const watchingA = startWatcher(mailboxA, "socket-a", controllerA);
    const ownerA = await waitForOwner(root, "socket-a", watchingA);
    const watchingB = startWatcher(mailboxB, "socket-b", controllerB);

    await sleep(500);
    assert.equal(watchingB.settled, false, `waiter exited: ${watchingB.error}`);
    assert.deepEqual(await readLockOwner(root, WATCH_KEY), ownerA, "old watcher keeps the lock");

    const one = await sendProviderMail(mailboxA, "claude:alpha", false);
    await waitFor("old watcher delivery", () => first.calls.length === 1);
    assert.equal(first.calls[0].envelopeId, one.envelope.id);
    await sleep(300);
    assert.equal(second.calls.length, 0, "the waiter never acts while the old watcher lives");

    controllerA.abort();
    await watchingA.promise;
    await waitForOwner(root, "socket-b", watchingB);
    const two = await sendProviderMail(mailboxB, "claude:alpha", false);
    await waitFor("waiter delivery after handover", () => second.calls.length === 1);
    assert.equal(second.calls[0].envelopeId, two.envelope.id);
    assert.equal(first.calls.length, 1);
    controllerB.abort();
    await watchingB.promise;
    assert.equal(await readLockOwner(root, WATCH_KEY), undefined);
  });
});

test("terminal pre-write endpoint loss releases the lock and the waiter retries the mail", async () => {
  await sandbox("lock-terminal-handoff", async (root) => {
    const first = recordingAdapter({
      outcome: "deferred",
      detail: "endpoint missing before write",
      releaseWatcher: true,
    });
    const second = recordingAdapter({ outcome: "verified" });
    const mailboxA = providerMailbox(root, { claude: first });
    const mailboxB = providerMailbox(root, { claude: second });
    const controllerA = new AbortController();
    const controllerB = new AbortController();
    const watchingA = startWatcher(mailboxA, "socket-a", controllerA);
    await waitForOwner(root, "socket-a", watchingA);
    const watchingB = startWatcher(mailboxB, "socket-b", controllerB);
    await sleep(300);
    assert.equal(second.calls.length, 0);

    const sent = await sendProviderMail(mailboxA, "claude:alpha", false);
    await waitFor("old watcher exit after terminal loss", () => watchingA.settled);
    assert.equal(watchingA.error, undefined, String(watchingA.error));
    assert.equal(first.calls.length, 1);
    assert.equal(first.calls[0].envelopeId, sent.envelope.id);

    await waitForOwner(root, "socket-b", watchingB);
    await waitFor("waiter delivery", () => second.calls.length === 1);
    assert.equal(second.calls[0].envelopeId, sent.envelope.id);
    assert.equal(
      await exists(notificationFile(root, WATCH_KEY, sent.envelope.id, "unverified")),
      false,
      "pre-write loss records no terminal marker",
    );
    await waitFor("verified marker", () =>
      exists(notificationFile(root, WATCH_KEY, sent.envelope.id, "notified")),
    );
    assert.equal(first.calls.length, 1, "the old generation never retries after releasing");
    controllerB.abort();
    await watchingB.promise;
  });
});

test("transient busy errors keep the old watcher and its lock", async () => {
  await sandbox("lock-transient-busy", async (root) => {
    const first = recordingAdapter([
      { outcome: "deferred", detail: "pipe busy" },
      { outcome: "deferred", detail: "pipe busy" },
      { outcome: "verified" },
    ]);
    const second = recordingAdapter({ outcome: "verified" });
    const mailboxA = providerMailbox(root, { claude: first });
    const mailboxB = providerMailbox(root, { claude: second });
    const controllerA = new AbortController();
    const controllerB = new AbortController();
    const watchingA = startWatcher(mailboxA, "socket-a", controllerA);
    const ownerA = await waitForOwner(root, "socket-a", watchingA);
    const watchingB = startWatcher(mailboxB, "socket-b", controllerB);

    const sent = await sendProviderMail(mailboxA, "claude:alpha", false);
    await waitFor("busy retries then verified delivery", () => first.calls.length === 3);
    await waitFor("verified marker", () =>
      exists(notificationFile(root, WATCH_KEY, sent.envelope.id, "notified")),
    );
    assert.equal(watchingA.settled, false, "transient busy must not exit the watcher");
    assert.deepEqual(await readLockOwner(root, WATCH_KEY), ownerA);
    assert.equal(second.calls.length, 0, "the waiter did not take over");
    assert.equal(watchingB.settled, false);
    assert.ok(first.calls.every((call) => call.envelopeId === sent.envelope.id));

    controllerA.abort();
    controllerB.abort();
    await Promise.all([watchingA.promise, watchingB.promise]);
  });
});

test("a stale generation cannot record success after another generation owns the lock", async () => {
  await sandbox("lock-stale-generation", async (root) => {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const stale = {
      calls: [],
      async wake(request) {
        stale.calls.push(request);
        await gate;
        return { outcome: "verified" };
      },
    };
    const mailbox = providerMailbox(root, { claude: stale });
    const controller = new AbortController();
    const watching = startWatcher(mailbox, "socket-a", controller);
    await waitForOwner(root, "socket-a", watching);
    const sent = await sendProviderMail(mailbox, "claude:alpha", false);
    await waitFor("in-flight wakeup", () => stale.calls.length === 1);

    const lockPath = join(root, "state", "watchers", "_providers", "claude", "alpha.lock");
    await writeFile(
      lockPath,
      `${JSON.stringify({
        pid: process.pid,
        address: "claude:alpha",
        generation: "socket-b",
        startedAt: new Date().toISOString(),
      })}\n`,
    );
    release();
    await sleep(400);
    assert.equal(
      await exists(notificationFile(root, WATCH_KEY, sent.envelope.id, "notified")),
      false,
      "stale generation wrote a success marker",
    );
    controller.abort();
    await watching.promise;
    assert.equal(
      (await readLockOwner(root, WATCH_KEY))?.generation,
      "socket-b",
      "a stale watcher must not remove its successor lock",
    );
  });
});
