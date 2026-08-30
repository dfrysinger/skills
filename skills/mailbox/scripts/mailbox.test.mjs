import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import {
  createConfiguredMailbox,
  createMailbox,
  MailboxConfigurationError,
  parseMailboxAddress,
} from "./mailbox-core.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const execFileAsync = promisify(execFile);
const mailboxCoreUrl = new URL("./mailbox-core.mjs", import.meta.url).href;
const requestCli = join(
  scriptDirectory,
  "../../../extensions/session-inbox/request.mjs",
);

async function waitForRequest(inboxRoot) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try {
      const names = (await readdir(join(inboxRoot, "pending"))).filter((name) =>
        name.endsWith(".json"),
      );
      if (names.length > 0) {
        const name = names[0];
        return {
          name,
          request: JSON.parse(
            await readFile(join(inboxRoot, "pending", name), "utf8"),
          ),
        };
      }
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error("timed out waiting for session-inbox request");
}

async function waitForFile(path) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try {
      return await readFile(path, "utf8");
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(`timed out waiting for ${path}`);
}

test("portable mailbox publishes complete envelopes and acknowledges them", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-"));
  try {
    const mailboxRoot = join(root, "mailbox");
    const stateRoot = join(root, "state");
    const attachmentA = join(root, "a", "proof.txt");
    const attachmentB = join(root, "b", "proof.txt");
    await mkdir(dirname(attachmentA), { recursive: true });
    await mkdir(dirname(attachmentB), { recursive: true });
    await writeFile(attachmentA, "first");
    await writeFile(attachmentB, "second");
    const mailbox = createMailbox({ mailboxRoot, stateRoot, requestCli });

    const sent = await mailbox.send({
      recipient: "hotel",
      sender: "whisky",
      summary: "portable proof",
      message: "the full message",
      files: [attachmentA, attachmentB],
      wake: false,
    });
    const pendingNames = await readdir(join(mailboxRoot, "hotel", "pending"));
    assert.ok(pendingNames.includes(`${sent.envelope.id}.json`));
    assert.ok(pendingNames.includes(sent.envelope.id));
    assert.ok(pendingNames.every((name) => !name.endsWith(".tmp")));
    assert.deepEqual(sent.envelope.attachments, ["proof.txt", "proof-2.txt"]);

    const checked = await mailbox.check("hotel");
    assert.equal(checked.length, 1);
    assert.equal(checked[0].envelope.summary, "portable proof");
    const read = await mailbox.read("hotel", sent.envelope.id);
    assert.equal(read.envelope.message, "the full message");

    await mailbox.acknowledge("hotel", sent.envelope.id);
    assert.equal((await mailbox.check("hotel")).length, 0);
    const delivered = await readdir(join(mailboxRoot, "hotel", "delivered"));
    assert.ok(delivered.includes(`${sent.envelope.id}.json`));
    assert.ok(delivered.includes(sent.envelope.id));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("wakeup failures never remove a published envelope", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-wakeup-failure-"));
  const previousNode = process.env.COPILOT_MAILBOX_NODE;
  try {
    const mailboxRoot = join(root, "mailbox");
    process.env.COPILOT_MAILBOX_NODE = join(root, "missing-node");
    const mailbox = createMailbox({
      mailboxRoot,
      stateRoot: join(root, "state"),
      requestCli,
    });
    const sent = await mailbox.send({
      recipient: "hotel",
      sender: "whisky",
      summary: "durable despite wakeup failure",
      message: "keep this envelope",
    });

    assert.equal(sent.wakeup.status, "unverified");
    assert.equal((await mailbox.check("hotel")).length, 1);
    assert.equal(
      JSON.parse(await readFile(sent.envelopePath, "utf8")).message,
      "keep this envelope",
    );
  } finally {
    if (previousNode === undefined) delete process.env.COPILOT_MAILBOX_NODE;
    else process.env.COPILOT_MAILBOX_NODE = previousNode;
    await rm(root, { recursive: true, force: true });
  }
});

test("request timeouts reuse the same mailbox delivery attempt", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-timeout-retry-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, JSON.stringify(process.argv.slice(2)) + "\\n");
process.exit(2);
`,
    );
    const mailbox = createMailbox({ mailboxRoot, stateRoot, requestCli: mockRequest });
    const sent = await mailbox.send({
      recipient: "hotel",
      sender: "whisky",
      summary: "timeout retry",
      message: "reuse the in-flight attempt",
      wake: false,
    });

    assert.equal((await mailbox.poke("hotel")).status, "unverified");
    assert.equal((await mailbox.poke("hotel")).status, "unverified");
    const calls = (await readFile(callLog, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const dedupeKeys = calls.map(
      (args) => args[args.indexOf("--dedupe-key") + 1],
    );
    assert.equal(dedupeKeys.length, 2);
    assert.equal(dedupeKeys[0], dedupeKeys[1]);
    assert.match(
      dedupeKeys[0],
      new RegExp(`^mailbox:immediate-v3:hotel:${sent.envelope.id}:`),
    );
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("mailbox addresses preserve valid qualified names and reject malformed input", () => {
  assert.deepEqual(parseMailboxAddress("hotel"), {
    address: "hotel",
    name: "hotel",
  });
  assert.deepEqual(parseMailboxAddress("hotel@surface-pro"), {
    address: "hotel@surface-pro",
    name: "hotel",
    machine: "surface-pro",
  });
  for (const address of [
    "",
    "@surface-pro",
    "hotel@",
    "hotel@surface@pro",
    "hotel @surface-pro",
    "hotel@surface/pro",
  ]) {
    assert.throws(() => parseMailboxAddress(address));
  }
});

test("explicit unqualified-only mode ignores malformed machine configuration", () => {
  const previousMachine = process.env.COPILOT_AGENT_MACHINE;
  try {
    process.env.COPILOT_AGENT_MACHINE = "Surface Pro";
    assert.throws(() => createMailbox(), /COPILOT_AGENT_MACHINE/);
    assert.deepEqual(createMailbox({ machineName: null }).localAddresses("hotel"), [
      "hotel",
    ]);
  } finally {
    if (previousMachine === undefined) delete process.env.COPILOT_AGENT_MACHINE;
    else process.env.COPILOT_AGENT_MACHINE = previousMachine;
  }
});

test("persistent configuration survives a process without mailbox environment", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-config-"));
  const configPath = join(root, "mailbox-config.json");
  const remoteMailboxRoot = join(root, "remote");
  await writeFile(
    configPath,
    `${JSON.stringify({
      schemaVersion: 1,
      machineName: "macbook-pro",
      remoteMailboxRoot,
    })}\n`,
  );

  const mailbox = createConfiguredMailbox({
    configPath,
    mailboxRoot: join(root, "local"),
    stateRoot: join(root, "state"),
  });
  assert.deepEqual(mailbox.watchAddresses("oscar"), [
    "oscar",
    "oscar@macbook-pro",
  ]);
  assert.equal(mailbox.remoteMailboxRoot, remoteMailboxRoot);
  await rm(root, { recursive: true, force: true });
});

test("mailbox environment overrides persistent routing configuration", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-config-env-"));
  const configPath = join(root, "mailbox-config.json");
  const previousMachine = process.env.COPILOT_AGENT_MACHINE;
  const previousRemote = process.env.MAILBOX_REMOTE_ROOT;
  try {
    await writeFile(
      configPath,
      `${JSON.stringify({
        schemaVersion: 1,
        machineName: "configured-machine",
        remoteMailboxRoot: join(root, "configured-remote"),
      })}\n`,
    );
    process.env.COPILOT_AGENT_MACHINE = "environment-machine";
    process.env.MAILBOX_REMOTE_ROOT = join(root, "environment-remote");
    const mailbox = createConfiguredMailbox({
      configPath,
      mailboxRoot: join(root, "local"),
      stateRoot: join(root, "state"),
    });
    assert.equal(mailbox.machineName, "environment-machine");
    assert.equal(mailbox.remoteMailboxRoot, join(root, "environment-remote"));
  } finally {
    if (previousMachine === undefined) delete process.env.COPILOT_AGENT_MACHINE;
    else process.env.COPILOT_AGENT_MACHINE = previousMachine;
    if (previousRemote === undefined) delete process.env.MAILBOX_REMOTE_ROOT;
    else process.env.MAILBOX_REMOTE_ROOT = previousRemote;
    await rm(root, { recursive: true, force: true });
  }
});

test("invalid persistent configuration fails closed", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-config-invalid-"));
  try {
    const cases = [
      {},
      { schemaVersion: 2, machineName: "mac", remoteMailboxRoot: join(root, "r") },
      { schemaVersion: 1, machineName: "bad machine", remoteMailboxRoot: join(root, "r") },
      { schemaVersion: 1, machineName: "mac", remoteMailboxRoot: "relative" },
      {
        schemaVersion: 1,
        machineName: "mac",
        remoteMailboxRoot: join(root, "r"),
        unknown: true,
      },
    ];
    for (const [index, configuration] of cases.entries()) {
      const configPath = join(root, `invalid-${index}.json`);
      await writeFile(configPath, JSON.stringify(configuration));
      assert.throws(
        () =>
          createConfiguredMailbox({
            configPath,
            mailboxRoot: join(root, "local"),
            stateRoot: join(root, "state"),
          }),
        MailboxConfigurationError,
      );
    }
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("an explicit missing configuration path fails closed", () => {
  const previousConfigPath = process.env.MAILBOX_CONFIG_PATH;
  try {
    process.env.MAILBOX_CONFIG_PATH = join(
      tmpdir(),
      `missing-mailbox-config-${process.pid}.json`,
    );
    assert.throws(() => createConfiguredMailbox(), MailboxConfigurationError);
  } finally {
    if (previousConfigPath === undefined) delete process.env.MAILBOX_CONFIG_PATH;
    else process.env.MAILBOX_CONFIG_PATH = previousConfigPath;
  }
});

test("remote transport is path-disjoint from mutable mailbox roots", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-config-overlap-"));
  const configPath = join(root, "mailbox-config.json");
  try {
    for (const [mailboxRoot, stateRoot, remoteMailboxRoot] of [
      [join(root, "same"), join(root, "state"), join(root, "same")],
      [join(root, "local"), join(root, "state"), join(root, "local", "remote")],
      [join(root, "remote", "local"), join(root, "state"), join(root, "remote")],
      [join(root, "local"), join(root, "remote", "state"), join(root, "remote")],
    ]) {
      await writeFile(
        configPath,
        JSON.stringify({
          schemaVersion: 1,
          machineName: "mac",
          remoteMailboxRoot,
        }),
      );
      assert.throws(() =>
        createConfiguredMailbox({ configPath, mailboxRoot, stateRoot }),
      );
    }
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("configure writes durable user-only routing configuration", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-config-cli-"));
  const configPath = join(root, "mailbox-config.json");
  const remoteMailboxRoot = join(root, "remote");
  try {
    const { stdout } = await execFileAsync(process.execPath, [
      join(scriptDirectory, "mailbox.mjs"),
      "configure",
      "--machine",
      "surface-pro",
      "--remote-root",
      remoteMailboxRoot,
      "--config-path",
      configPath,
    ]);
    assert.match(stdout, new RegExp(configPath.replaceAll("\\", "\\\\")));
    assert.deepEqual(JSON.parse(await readFile(configPath, "utf8")), {
      schemaVersion: 1,
      machineName: "surface-pro",
      remoteMailboxRoot,
    });
    if (process.platform !== "win32") {
      assert.equal((await stat(configPath)).mode & 0o077, 0);
    }
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("qualified recipients publish immutable transport and import into a local mailbox", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-qualified-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "sender-mailbox");
    const remoteMailboxRoot = join(root, "remote-mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, "called\\n");
`,
    );
    const senderMailbox = createMailbox({
      mailboxRoot,
      remoteMailboxRoot,
      stateRoot,
      requestCli: mockRequest,
      machineName: "desktop",
    });

    const sent = await senderMailbox.send({
      recipient: "hotel@surface-pro",
      sender: "windows-proof",
      summary: "qualified routing",
      message: "deliver only to surface-pro",
    });

    assert.deepEqual(sent.envelope.to, { name: "hotel@surface-pro" });
    assert.match(sent.envelopePath, /hotel@surface-pro[\\/]pending/);
    assert.equal(sent.wakeup.status, "remote-pending");
    await assert.rejects(readFile(callLog, "utf8"), { code: "ENOENT" });
    assert.equal((await senderMailbox.check("hotel")).length, 0);
    assert.equal(
      JSON.parse(await readFile(sent.envelopePath, "utf8")).to.name,
      "hotel@surface-pro",
    );
    assert.ok(
      (await readdir(join(remoteMailboxRoot, "hotel@surface-pro", "pending"))).every(
        (name) => !name.includes(".uploading-"),
      ),
    );
    assert.equal((await senderMailbox.checkLocal("hotel")).length, 0);

    const recipientMailbox = createMailbox({
      mailboxRoot: join(root, "recipient-mailbox"),
      remoteMailboxRoot,
      stateRoot: join(root, "recipient-state"),
      requestCli: mockRequest,
      machineName: "surface-pro",
    });
    assert.equal(recipientMailbox.machineName, "surface-pro");
    assert.deepEqual(recipientMailbox.localAddresses("hotel"), ["hotel"]);
    assert.deepEqual(recipientMailbox.watchAddresses("hotel"), [
      "hotel",
      "hotel@surface-pro",
    ]);
    assert.equal(await recipientMailbox.importRemote("hotel@surface-pro"), 1);
    assert.equal(await recipientMailbox.importRemote("hotel@surface-pro"), 0);
    assert.equal((await recipientMailbox.checkLocal("hotel")).length, 1);
    assert.equal(
      (await recipientMailbox.readLocal("hotel", sent.envelope.id)).envelope.message,
      "deliver only to surface-pro",
    );
    const remoteBefore = await readFile(sent.envelopePath, "utf8");
    await recipientMailbox.acknowledgeLocal("hotel", sent.envelope.id);
    assert.equal(await readFile(sent.envelopePath, "utf8"), remoteBefore);
    await readFile(
      join(
        remoteMailboxRoot,
        "receipts",
        "hotel@surface-pro",
        `${sent.envelope.id}.json`,
      ),
      "utf8",
    );
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("remote publication failures preserve a retryable local outbox", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-remote-retry-"));
  try {
    const remoteMailboxRoot = join(root, "remote-mailbox");
    const stateRoot = join(root, "state");
    await writeFile(remoteMailboxRoot, "temporarily unavailable");
    const mailbox = createMailbox({
      mailboxRoot: join(root, "local-mailbox"),
      remoteMailboxRoot,
      stateRoot,
      machineName: "desktop",
    });

    const sent = await mailbox.send({
      recipient: "hotel@surface-pro",
      sender: "whisky",
      summary: "retry remote publication",
      message: "keep this locally until OneDrive recovers",
      wake: false,
    });

    assert.match(sent.envelopePath, /remote-outbox[\\/]envelopes/);
    assert.equal(
      JSON.parse(await readFile(sent.envelopePath, "utf8")).message,
      "keep this locally until OneDrive recovers",
    );

    await rm(remoteMailboxRoot);
    await mkdir(remoteMailboxRoot);
    await mailbox.flushRemoteOutbox();
    await readFile(
      join(
        remoteMailboxRoot,
        "hotel@surface-pro",
        "pending",
        `${sent.envelope.id}.json`,
      ),
      "utf8",
    );
    await assert.rejects(readFile(sent.envelopePath, "utf8"), { code: "ENOENT" });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("foreign qualified recipient operations fail before scanning or marking", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-foreign-address-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "mailbox");
    const remoteMailboxRoot = join(root, "remote-mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, "called\\n");
`,
    );
    const mailbox = createMailbox({
      mailboxRoot,
      remoteMailboxRoot,
      stateRoot,
      requestCli: mockRequest,
      machineName: "thinkpad",
    });
    const sent = await mailbox.send({
      recipient: "hotel@macbook-pro",
      sender: "windows-proof",
      summary: "foreign route",
      message: "must remain remote",
      wake: false,
    });

    for (const operation of [
      () => mailbox.check("hotel@macbook-pro"),
      () => mailbox.read("hotel@macbook-pro", sent.envelope.id),
      () => mailbox.acknowledge("hotel@macbook-pro", sent.envelope.id),
      () => mailbox.poke("hotel@macbook-pro", { targetName: "hotel" }),
      () =>
        mailbox.watch("hotel@macbook-pro", {
          targetName: "hotel",
          once: true,
        }),
    ]) {
      await assert.rejects(operation());
    }
    assert.deepEqual(await mailbox.list(), []);
    await assert.rejects(readFile(callLog, "utf8"), { code: "ENOENT" });
    await assert.rejects(
      readFile(join(stateRoot, "watchers", "hotel@macbook-pro.lock"), "utf8"),
      { code: "ENOENT" },
    );
    await assert.rejects(
      readFile(join(stateRoot, "notifying", "hotel@macbook-pro.lock"), "utf8"),
      { code: "ENOENT" },
    );
    await assert.rejects(
      readFile(
        join(
          stateRoot,
          "notified",
          "hotel@macbook-pro",
          `${sent.envelope.id}.notified`,
        ),
        "utf8",
      ),
      { code: "ENOENT" },
    );
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("unqualified envelopes remain visible without machine configuration", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-legacy-"));
  try {
    const mailboxRoot = join(root, "mailbox");
    const senderMailbox = createMailbox({
      mailboxRoot,
      stateRoot: join(root, "sender-state"),
    });
    const sent = await senderMailbox.send({
      recipient: "hotel",
      sender: "windows-proof",
      summary: "legacy routing",
      message: "legacy envelope",
      wake: false,
    });
    const otherMachine = createMailbox({
      mailboxRoot,
      stateRoot: join(root, "recipient-state"),
    });

    assert.deepEqual(sent.envelope.to, { name: "hotel" });
    assert.equal((await otherMachine.check("hotel")).length, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("matching qualified sender imports and targets the base local session", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-qualified-local-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "mailbox");
    const remoteMailboxRoot = join(root, "remote-mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, JSON.stringify(process.argv.slice(2)) + "\\n");
console.log('{"status":"completed","result":{"delivery":"idle"}}');
`,
    );
    const mailbox = createMailbox({
      mailboxRoot,
      remoteMailboxRoot,
      stateRoot,
      requestCli: mockRequest,
      machineName: "surface-pro",
    });

    const sent = await mailbox.send({
      recipient: "hotel@surface-pro",
      sender: "windows-proof",
      summary: "local qualified routing",
      message: "deliver to local hotel",
    });

    assert.equal(sent.wakeup.status, "delivered");
    const args = JSON.parse((await readFile(callLog, "utf8")).trim());
    assert.equal(args[args.indexOf("--target-name") + 1], "hotel");
    assert.match(
      args[args.indexOf("--dedupe-key") + 1],
      new RegExp(`^mailbox:immediate-v3:hotel:${sent.envelope.id}:`),
    );
    await readFile(
      join(
        stateRoot,
        "notified",
        "hotel",
        `${sent.envelope.id}.notified`,
      ),
      "utf8",
    );
    await assert.rejects(
      readFile(
        join(
          stateRoot,
          "notified",
          "hotel@surface-pro",
          `${sent.envelope.id}.notified`,
        ),
        "utf8",
      ),
      { code: "ENOENT" },
    );
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("recipient-local actions use only the unqualified local mailbox", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-local-actions-"));
  try {
    const mailboxRoot = join(root, "mailbox");
    const remoteMailboxRoot = join(root, "remote-mailbox");
    const mailbox = createMailbox({
      mailboxRoot,
      remoteMailboxRoot,
      stateRoot: join(root, "state"),
      machineName: "thinkpad",
    });
    const local = await mailbox.send({
      recipient: "hotel",
      sender: "whisky",
      summary: "local",
      message: "local message",
      wake: false,
    });
    const qualified = await mailbox.send({
      recipient: "hotel@thinkpad",
      sender: "whisky",
      summary: "qualified",
      message: "qualified message",
      wake: false,
    });
    await mailbox.importRemote("hotel@thinkpad");
    await mailbox.importRemote("hotel@thinkpad");

    const checked = await mailbox.checkLocal("hotel");
    assert.equal(checked.length, 2);
    assert.deepEqual(new Set(checked.map(({ mailboxAddress }) => mailboxAddress)), new Set(["hotel"]));
    assert.equal(
      (await mailbox.readLocal("hotel", qualified.envelope.id)).mailboxAddress,
      "hotel",
    );
    await mailbox.acknowledgeLocal("hotel", local.envelope.id);
    assert.equal((await mailbox.check("hotel")).length, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("recipient-local watcher terminates an ambiguous wakeup without duplicate requests", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-watch-"));
  const previousInboxRoot = process.env.COPILOT_SESSION_INBOX_DIR;
  try {
    const mailboxRoot = join(root, "mailbox");
    const stateRoot = join(root, "state");
    const inboxRoot = join(root, "session-inbox");
    process.env.COPILOT_SESSION_INBOX_DIR = inboxRoot;
    const instancePath = join(inboxRoot, "instances", "hotel-session.json");
    await mkdir(dirname(instancePath), { recursive: true });
    await writeFile(
      instancePath,
      `${JSON.stringify({
        sessionId: "hotel-session",
        sessionName: "hotel",
        generation: "generation-1",
        updatedAt: new Date().toISOString(),
      })}\n`,
    );
    const mailbox = createMailbox({ mailboxRoot, stateRoot, requestCli });
    const sent = await mailbox.send({
      recipient: "hotel",
      sender: "whisky",
      summary: "watcher proof",
      message: "wake through the local bridge",
      wake: false,
    });

    const watching = mailbox.watch("hotel", { once: true, intervalMs: 100 });
    const { name, request } = await waitForRequest(inboxRoot);
    assert.equal(request.target.targetName, "hotel");
    assert.equal(request.target.resolvedBy, "session-name");
    assert.equal(request.target.sessionId, "hotel-session");
    assert.equal(request.mode, "immediate");
    assert.match(
      request.dedupeKey,
      new RegExp(`^mailbox:immediate-v3:hotel:${sent.envelope.id}:`),
    );
    assert.match(request.prompt, /^check mailbox; skip if empty \[mb:/);

    const receiptPath = join(inboxRoot, "completed", name);
    await rm(join(inboxRoot, "pending", name));
    await mkdir(dirname(receiptPath), { recursive: true });
    await writeFile(
      receiptPath,
      `${JSON.stringify({
        status: "completed",
        result: {
          messageId: "accepted-by-older-extension",
          delivery: "unconfirmed",
          idleDelivery: false,
        },
      })}\n`,
    );
    await watching;

    const attemptPath = join(
      stateRoot,
      "notified",
      "hotel",
      `${sent.envelope.id}.attempt`,
    );
    const attemptId = (await readFile(attemptPath, "utf8")).trim();
    assert.equal(request.dedupeKey.endsWith(`:${attemptId}`), true);
    assert.equal(
      (await readFile(
        join(stateRoot, "notified", "hotel", `${sent.envelope.id}.unverified`),
        "utf8",
      )).trim(),
      attemptId,
    );
    assert.equal((await mailbox.poke("hotel")).status, "unverified");
    assert.deepEqual(
      (await readdir(join(inboxRoot, "pending"))).filter((entry) =>
        entry.endsWith(".json"),
      ),
      [],
    );

    const later = await mailbox.send({
      recipient: "hotel",
      sender: "whisky",
      summary: "later watcher proof",
      message: "wake both pending envelopes",
      wake: false,
    });
    const retrying = mailbox.poke("hotel");
    const { name: retryName, request: retryRequest } = await waitForRequest(inboxRoot);
    assert.match(
      retryRequest.dedupeKey,
      new RegExp(`^mailbox:immediate-v3:hotel:${later.envelope.id}:`),
    );
    const retryReceiptPath = join(inboxRoot, "completed", retryName);
    await rm(join(inboxRoot, "pending", retryName));
    await mkdir(dirname(retryReceiptPath), { recursive: true });
    await writeFile(
      retryReceiptPath,
      `${JSON.stringify({
        status: "completed",
        result: {
          messageId: "later-confirmed",
          delivery: "steering",
          idleDelivery: false,
        },
      })}\n`,
    );
    assert.equal((await retrying).status, "delivered");
    for (const id of [sent.envelope.id, later.envelope.id]) {
      assert.match(
        await readFile(join(stateRoot, "notified", "hotel", `${id}.notified`), "utf8"),
        /^\d{4}-\d{2}-\d{2}T/,
      );
      await assert.rejects(
        readFile(join(stateRoot, "notified", "hotel", `${id}.unverified`), "utf8"),
        { code: "ENOENT" },
      );
    }
    await assert.rejects(
      readFile(join(stateRoot, "watchers", "hotel.lock"), "utf8"),
      { code: "ENOENT" },
    );
    const diagnostics = await readFile(join(stateRoot, "logs", "mailbox.jsonl"), "utf8");
    assert.match(diagnostics, /"event":"watcher.started"/);
    assert.match(diagnostics, /"event":"wakeup.unverified"/);
    assert.doesNotMatch(diagnostics, /wake through the local bridge/);
  } finally {
    if (previousInboxRoot === undefined) {
      delete process.env.COPILOT_SESSION_INBOX_DIR;
    } else {
      process.env.COPILOT_SESSION_INBOX_DIR = previousInboxRoot;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("qualified watcher uses an isolated full-address lock", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-qualified-lock-"));
  try {
    const stateRoot = join(root, "state");
    const mailbox = createMailbox({
      mailboxRoot: join(root, "mailbox"),
      stateRoot,
      machineName: "thinkpad",
    });
    const controller = new AbortController();
    const watching = mailbox.watch("hotel@thinkpad", {
      targetName: "hotel",
      intervalMs: 1_000,
      signal: controller.signal,
    });
    const lockPath = join(stateRoot, "watchers", "hotel@thinkpad.lock");
    const owner = JSON.parse(await waitForFile(lockPath));
    assert.equal(owner.address, "hotel@thinkpad");
    await assert.rejects(
      readFile(join(stateRoot, "watchers", "hotel.lock"), "utf8"),
      { code: "ENOENT" },
    );
    controller.abort();
    await watching;
    await assert.rejects(readFile(lockPath, "utf8"), { code: "ENOENT" });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("watcher locks are removed when the owner process exits normally", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-exit-lock-"));
  try {
    const stateRoot = join(root, "state");
    const childScript = join(root, "watch-and-exit.mjs");
    await writeFile(
      childScript,
      `import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { createMailbox } from ${JSON.stringify(mailboxCoreUrl)};

const stateRoot = process.argv[2];
const mailbox = createMailbox({
  mailboxRoot: process.argv[3],
  stateRoot,
  machineName: "thinkpad",
});
void mailbox.watch("hotel@thinkpad", {
  targetName: "hotel",
  intervalMs: 1_000,
});
const lockPath = join(stateRoot, "watchers", "hotel@thinkpad.lock");
for (let attempt = 0; attempt < 200; attempt += 1) {
  try {
    await readFile(lockPath, "utf8");
    process.exit(0);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
}
process.exit(1);
`,
    );
    await execFileAsync("node", [
      childScript,
      stateRoot,
      join(root, "mailbox"),
    ]);
    await assert.rejects(
      readFile(join(stateRoot, "watchers", "hotel@thinkpad.lock"), "utf8"),
      { code: "ENOENT" },
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("late-arriving older envelopes receive a new notification", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-order-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, JSON.stringify(process.argv.slice(2)) + "\\n");
console.log('{"status":"completed","result":{"delivery":"steering"}}');
`,
    );
    const pending = join(mailboxRoot, "hotel", "pending");
    await mkdir(pending, { recursive: true });
    const writeEnvelope = async (id) =>
      writeFile(
        join(pending, `${id}.json`),
        `${JSON.stringify({
          id,
          from: { name: "whisky" },
          to: { name: "hotel" },
          summary: id,
          message: "ordering proof",
          attachments: [],
          sent_at: "2026-08-27T00:00:00Z",
        })}\n`,
      );
    const mailbox = createMailbox({
      mailboxRoot,
      stateRoot,
      requestCli: mockRequest,
    });

    await writeEnvelope("20260827T100000Z-newer");
    assert.equal((await mailbox.poke("hotel")).status, "delivered");
    await writeEnvelope("20260827T090000Z-older");
    assert.equal((await mailbox.poke("hotel")).status, "delivered");
    assert.equal((await readFile(callLog, "utf8")).trim().split("\n").length, 2);
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("sender and watcher serialize requests by local mailbox address", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-notification-claim-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, "called\\n");
await new Promise((resolve) => setTimeout(resolve, 200));
console.log('{"status":"completed","result":{"messageAccepted":true,"delivery":"steering"}}');
`,
    );
    const mailbox = createMailbox({
      mailboxRoot,
      stateRoot,
      requestCli: mockRequest,
    });
    await mailbox.send({
      recipient: "hotel",
      sender: "whisky",
      summary: "notification claim proof",
      message: "one request only",
      wake: false,
    });

    const results = await Promise.all([
      mailbox.poke("hotel", { targetName: "hotel" }),
      mailbox.poke("hotel", {
        targetName: "hotel",
        requireStableAttachments: true,
      }),
    ]);
    assert.deepEqual(
      results.map((result) => result.status).sort(),
      ["delivered", "in-progress"],
    );
    assert.equal((await readFile(callLog, "utf8")).trim(), "called");
    assert.equal(
      (await mailbox.poke("hotel", { targetName: "hotel" })).status,
      "already-poked",
    );
    await assert.rejects(
      readFile(join(stateRoot, "notifying", "hotel.lock"), "utf8"),
      { code: "ENOENT" },
    );
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("watcher waits for synced attachments to exist and stabilize", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-attachments-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, "called\\n");
console.log('{"status":"completed","result":{"messageAccepted":true,"delivery":"idle"}}');
`,
    );
    const id = "20260827T100000Z-attachment";
    const pending = join(mailboxRoot, "hotel", "pending");
    await mkdir(pending, { recursive: true });
    await writeFile(
      join(pending, `${id}.json`),
      `${JSON.stringify({
        id,
        from: { name: "whisky" },
        to: { name: "hotel" },
        summary: "attachment",
        message: "wait for attachment",
        attachments: ["proof.txt"],
        sent_at: "2026-08-27T00:00:00Z",
      })}\n`,
    );
    const mailbox = createMailbox({
      mailboxRoot,
      stateRoot,
      requestCli: mockRequest,
    });

    await mailbox.watch("hotel", { once: true, intervalMs: 100 });
    await assert.rejects(readFile(callLog, "utf8"), { code: "ENOENT" });
    const attachmentDirectory = join(pending, id);
    await mkdir(attachmentDirectory);
    await writeFile(join(attachmentDirectory, "proof.txt"), "first");
    await mailbox.watch("hotel", { once: true, intervalMs: 100 });
    await assert.rejects(readFile(callLog, "utf8"), { code: "ENOENT" });
    await mailbox.watch("hotel", { once: true, intervalMs: 100 });
    assert.equal((await readFile(callLog, "utf8")).trim(), "called");
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("attachment stabilization does not delete another pending envelope's notification", async () => {
  const root = await mkdtemp(join(tmpdir(), "node-mailbox-notification-retention-"));
  const previousCallLog = process.env.MOCK_MAILBOX_REQUEST_CALLS;
  try {
    const mailboxRoot = join(root, "mailbox");
    const stateRoot = join(root, "state");
    const callLog = join(root, "request-calls.jsonl");
    const mockRequest = join(root, "mock-request.mjs");
    process.env.MOCK_MAILBOX_REQUEST_CALLS = callLog;
    await writeFile(
      mockRequest,
      `import { appendFileSync } from "node:fs";
appendFileSync(process.env.MOCK_MAILBOX_REQUEST_CALLS, "called\\n");
console.log('{"status":"completed","result":{"messageAccepted":true,"delivery":"steering"}}');
`,
    );
    const pending = join(mailboxRoot, "hotel", "pending");
    const notified = join(stateRoot, "notified", "hotel");
    await mkdir(pending, { recursive: true });
    await mkdir(notified, { recursive: true });
    const olderId = "20260827T100000Z-older";
    const newerId = "20260827T110000Z-newer";
    await writeFile(
      join(pending, `${olderId}.json`),
      `${JSON.stringify({
        id: olderId,
        from: { name: "whisky" },
        to: { name: "hotel" },
        summary: "ready",
        message: "ready now",
        attachments: [],
        sent_at: "2026-08-27T10:00:00Z",
      })}\n`,
    );
    await writeFile(
      join(pending, `${newerId}.json`),
      `${JSON.stringify({
        id: newerId,
        from: { name: "whisky" },
        to: { name: "hotel" },
        summary: "stabilizing",
        message: "already notified",
        attachments: ["proof.txt"],
        sent_at: "2026-08-27T11:00:00Z",
      })}\n`,
    );
    await mkdir(join(pending, newerId));
    await writeFile(join(pending, newerId, "proof.txt"), "proof");
    await writeFile(join(notified, `${newerId}.notified`), "already notified\n");
    const mailbox = createMailbox({
      mailboxRoot,
      stateRoot,
      requestCli: mockRequest,
    });

    assert.equal(
      (await mailbox.poke("hotel", { requireStableAttachments: true })).status,
      "delivered",
    );
    assert.equal(
      (await mailbox.poke("hotel", { requireStableAttachments: true })).status,
      "already-poked",
    );
    assert.equal((await readFile(callLog, "utf8")).trim(), "called");
    assert.equal(
      await readFile(join(notified, `${newerId}.notified`), "utf8"),
      "already notified\n",
    );
  } finally {
    if (previousCallLog === undefined) {
      delete process.env.MOCK_MAILBOX_REQUEST_CALLS;
    } else {
      process.env.MOCK_MAILBOX_REQUEST_CALLS = previousCallLog;
    }
    await rm(root, { recursive: true, force: true });
  }
});
