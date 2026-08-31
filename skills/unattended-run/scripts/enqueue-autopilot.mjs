#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const usage =
  "usage: enqueue-autopilot.mjs (--target-session ID | --target-tmux NAME) <objective-file>";

class InputError extends Error {
  constructor(message, exitCode = 64) {
    super(message);
    this.exitCode = exitCode;
  }
}

function parseTimeout(value) {
  if (!/^[0-9]+$/.test(value)) {
    throw new InputError("timeout must be between 1 and 360 seconds");
  }
  const timeout = Number(value);
  if (timeout < 1 || timeout > 360) {
    throw new InputError("timeout must be between 1 and 360 seconds");
  }
  return String(timeout);
}

function validateObjective(text) {
  if (!/\S/u.test(text)) {
    throw new InputError("objective file must contain a non-empty objective");
  }
  if (text.includes("<SLOT>")) {
    throw new InputError("objective still contains an unresolved <SLOT>");
  }

  const lines = text.split("\n");
  const firstInstruction = lines.find((line) => /\S/u.test(line))?.trimStart();
  if (
    firstInstruction?.startsWith("/autopilot") ||
    firstInstruction?.startsWith("/goal")
  ) {
    throw new InputError("objective file must contain only the objective body");
  }
  if (firstInstruction?.startsWith("/allow-all")) {
    throw new InputError("permission changes remain user-controlled");
  }
  if (
    lines.some((line) =>
      /^\/allow-all(?:\s|$)/u.test(line.trimStart()),
    )
  ) {
    throw new InputError("permission changes remain user-controlled");
  }
}

function canonicalObjective(text) {
  return text.replace(/(?:\r?\n)+$/u, "");
}

function expectedDedupeKey(sessionId, objectiveDigest) {
  return `autopilot:session:${sessionId}:${objectiveDigest}`;
}

function nonEmptyString(value) {
  return typeof value === "string" && value.length > 0;
}

function runRequest(requestCli, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [requestCli, ...args], {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    child.stdout.on("data", (chunk) => {
      output += chunk;
    });
    child.stderr.on("data", (chunk) => {
      output += chunk;
    });
    child.on("error", reject);
    child.on("close", (code, signal) => {
      resolve({
        exitCode: Number.isInteger(code) ? code : 1,
        output,
        signal,
      });
    });
  });
}

function receiptPathFromOutput(output) {
  let receiptPath;
  for (const line of output.split(/\r?\n/u)) {
    if (line.startsWith("receipt: ")) {
      receiptPath = line.slice("receipt: ".length);
    }
  }
  return receiptPath;
}

async function readAuthoritativeReceipt(output) {
  const path = receiptPathFromOutput(output);
  if (!path) return { path: undefined, receipt: undefined };
  try {
    return {
      path,
      receipt: JSON.parse(await readFile(path, "utf8")),
    };
  } catch (error) {
    return {
      path,
      receipt: undefined,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function auditDirectory() {
  return (
    process.env.COPILOT_AUTOPILOT_ENQUEUE_DIR ||
    join(homedir(), ".copilot", "autopilot-enqueue")
  );
}

async function writeAudit({
  outcome,
  detail,
  targetFlag,
  target,
  snapshot,
  request,
  authoritative,
}) {
  const directory = auditDirectory();
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const now = new Date();
  const suffix = randomBytes(4).toString("hex");
  const name = `${now.toISOString().replaceAll(/[-:.]/gu, "")}-${process.pid}-${suffix}.json`;
  const path = join(directory, name);
  const temporaryPath = join(directory, `.${name}.tmp`);
  const text = snapshot.toString("utf8");
  const expectedText = canonicalObjective(text);
  const objectiveDigest = createHash("sha256")
    .update(expectedText)
    .digest("hex");
  const receipt = authoritative.receipt;
  const result = receipt?.result;
  const dedupeKey = receipt?.sessionId
    ? expectedDedupeKey(receipt.sessionId, objectiveDigest)
    : undefined;
  const audit = {
    schemaVersion: 1,
    type: "autopilot-enqueue-audit",
    outcome,
    recordedAt: now.toISOString(),
    detail,
    objective: {
      sha256: objectiveDigest,
      byteLength: Buffer.byteLength(expectedText),
      bytesBase64: Buffer.from(expectedText).toString("base64"),
      snapshotSha256: createHash("sha256").update(snapshot).digest("hex"),
      snapshotByteLength: snapshot.length,
      snapshotBytesBase64: snapshot.toString("base64"),
    },
    target: {
      requestedType: targetFlag.slice("--target-".length),
      requested: target,
      sessionId: receipt?.sessionId,
      generation: receipt?.generation,
    },
    authoritativeReceipt: {
      path: authoritative.path,
      readable: Boolean(receipt),
      readError: authoritative.error,
      requestId: receipt?.id,
      status: receipt?.status,
      dedupeKey: receipt?.dedupeKey,
      expectedDedupeKey: dedupeKey,
      dedupeKeyMatches:
        nonEmptyString(dedupeKey) && receipt?.dedupeKey === dedupeKey,
    },
    nativeObjective: {
      objectiveSet: result?.objectiveSet === true,
      objectiveId: result?.objectiveId,
      status: result?.objectiveStatus,
      delivery: result?.delivery,
    },
    request: {
      exitCode: request.exitCode,
      signal: request.signal,
      output: request.output,
    },
  };
  await writeFile(temporaryPath, `${JSON.stringify(audit, null, 2)}\n`, {
    mode: 0o600,
  });
  await rename(temporaryPath, path);
  return path;
}

function notifyFailure() {
  if (process.platform !== "darwin") return;
  const child = spawn(
    "osascript",
    [
      "-e",
      'display notification "Autopilot handoff failed. The latest receipt in ~/.copilot/autopilot-enqueue contains the objective and SDK result." with title "Copilot unattended run"',
    ],
    { stdio: "ignore" },
  );
  child.on("error", () => {});
}

async function main() {
  const [targetFlag, target, objectiveFile, ...extra] = process.argv.slice(2);
  if (
    !["--target-session", "--target-tmux"].includes(targetFlag) ||
    !target ||
    !objectiveFile ||
    extra.length > 0
  ) {
    throw new InputError(usage);
  }

  const timeout = parseTimeout(
    process.env.AUTOPILOT_HANDOFF_TIMEOUT_SECONDS || "360",
  );
  const requestCli =
    process.env.SESSION_INBOX_REQUEST_CLI ||
    join(scriptDirectory, "../../../extensions/session-inbox/request.mjs");
  try {
    await access(objectiveFile, fsConstants.R_OK);
  } catch {
    throw new InputError(usage);
  }
  try {
    await access(requestCli, fsConstants.R_OK);
  } catch {
    throw new InputError("session-inbox request helper is unavailable", 2);
  }

  const temporaryDirectory = await mkdtemp(
    join(tmpdir(), "copilot-autopilot-objective-"),
  );
  const snapshotPath = join(temporaryDirectory, "objective.txt");
  try {
    const snapshot = await readFile(objectiveFile);
    await writeFile(snapshotPath, snapshot, { mode: 0o600 });
    validateObjective(snapshot.toString("utf8"));
    await mkdir(auditDirectory(), { recursive: true, mode: 0o700 });
    const expectedText = canonicalObjective(snapshot.toString("utf8"));
    const objectiveDigest = createHash("sha256")
      .update(expectedText)
      .digest("hex");

    const requestArgs = [
      "autopilot",
      targetFlag,
      target,
      "--prompt-file",
      snapshotPath,
      "--timeout",
      timeout,
    ];
    const request = await runRequest(requestCli, requestArgs);
    const authoritative = await readAuthoritativeReceipt(request.output);

    if (request.exitCode !== 0) {
      let auditPath;
      try {
        auditPath = await writeAudit({
          outcome: "failed",
          detail: `session-inbox request failed with exit status ${request.exitCode}`,
          targetFlag,
          target,
          snapshot,
          request,
          authoritative,
        });
      } catch (error) {
        console.error(
          `enqueue-autopilot: could not write failure audit receipt: ${error.message}`,
        );
      }
      notifyFailure();
      console.error(
        `enqueue-autopilot: SDK handoff failed${auditPath ? `; receipt: ${auditPath}` : ""}`,
      );
      return request.exitCode;
    }

    const receipt = authoritative.receipt;
    const result = receipt?.result;
    const requestedSessionMatches =
      targetFlag !== "--target-session" || receipt?.sessionId === target;
    const correlationConfirmed =
      nonEmptyString(receipt?.id) &&
      nonEmptyString(receipt?.sessionId) &&
      nonEmptyString(receipt?.generation) &&
      requestedSessionMatches &&
      receipt?.dedupeKey ===
        expectedDedupeKey(receipt.sessionId, objectiveDigest) &&
      result?.objectiveId !== undefined &&
      result?.objectiveId !== null &&
      ["active", "completed"].includes(result?.objectiveStatus);
    const confirmed =
      receipt?.status === "completed" &&
      correlationConfirmed &&
      result?.objectiveSet === true &&
      ["idle", "steering"].includes(result?.delivery);
    const outcome = confirmed ? "confirmed" : "unconfirmed";
    const detail = confirmed
      ? "SDK invoked the native autopilot objective and confirmed idle/steering activation"
      : "SDK receipt did not prove both native objective establishment and idle/steering activation";
    const auditPath = await writeAudit({
      outcome,
      detail,
      targetFlag,
      target,
      snapshot,
      request,
      authoritative,
    });
    if (confirmed) {
      console.log(`autopilot handoff confirmed; receipt: ${auditPath}`);
      return 0;
    }

    notifyFailure();
    console.error(
      `enqueue-autopilot: SDK receipt did not prove native objective establishment and idle/steering activation; receipt: ${auditPath}`,
    );
    return 1;
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

try {
  process.exitCode = await main();
} catch (error) {
  if (error instanceof InputError) {
    console.error(`enqueue-autopilot: ${error.message}`);
    process.exitCode = error.exitCode;
  } else {
    console.error(error);
    process.exitCode = 1;
  }
}
