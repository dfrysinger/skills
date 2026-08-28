import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createMailbox } from "./mailbox-core.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
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

test("recipient-local watcher wakes a live session by its Copilot session name", async () => {
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
    assert.equal(
      request.dedupeKey,
      `mailbox:immediate-v2:hotel:${sent.envelope.id}`,
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

    assert.equal((await mailbox.poke("hotel")).status, "already-poked");
    await assert.rejects(
      readFile(join(stateRoot, "watchers", "hotel.lock"), "utf8"),
      { code: "ENOENT" },
    );
    const diagnostics = await readFile(join(stateRoot, "logs", "mailbox.jsonl"), "utf8");
    assert.match(diagnostics, /"event":"watcher.started"/);
    assert.match(diagnostics, /"event":"wakeup.accepted"/);
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

test("sender and watcher serialize notification requests for one mailbox", async () => {
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
      mailbox.poke("hotel"),
      mailbox.poke("hotel", { requireStableAttachments: true }),
    ]);
    assert.deepEqual(
      results.map((result) => result.status).sort(),
      ["delivered", "in-progress"],
    );
    assert.equal((await readFile(callLog, "utf8")).trim(), "called");
    assert.equal((await mailbox.poke("hotel")).status, "already-poked");
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
