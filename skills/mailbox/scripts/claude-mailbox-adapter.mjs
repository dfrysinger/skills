// Claude Code native mailbox wakeup adapter.
//
// Delivers the fixed mailbox wakeup prompt to a long-lived Claude Code process
// through its private messaging pipe (CLAUDE_CODE_MESSAGING_SOCKET), using the
// own-child token (CLAUDE_CODE_MESSAGING_TOKEN). The pipe never replies, so a
// clean write is `submitted`, never `verified`.
//
// Secret handling: the token is held only in the closure of the adapter and is
// written only to the pipe. It is never placed in argv, results, details,
// errors, logs or files. Failure details are fixed strings plus an allowlisted
// error code.
import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import net from "node:net";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { canonicalizeMailboxAddress } from "./mailbox-core.mjs";

export const CLAUDE_PROVIDER = "claude";
export const CLAUDE_ENV = Object.freeze({
  selfAddress: "MAILBOX_SELF_ADDRESS",
  socket: "CLAUDE_CODE_MESSAGING_SOCKET",
  token: "CLAUDE_CODE_MESSAGING_TOKEN",
  pid: "CLAUDE_PID",
});
export const DEFAULT_AUTH_GAP_MS = 250;
const DEFAULT_CONNECT_TIMEOUT_MS = 5_000;
const DEFAULT_CLOSE_TIMEOUT_MS = 2_000;
// Pre-write errors that mean the pipe is gone for good. Anything else (for
// example a busy pipe) is treated as transient.
const TERMINAL_CONNECT_CODES = new Set(["ENOENT", "ECONNREFUSED"]);

export class ClaudeEnvironmentError extends Error {
  constructor(message) {
    super(message);
    this.name = "ClaudeEnvironmentError";
  }
}

export function claudeSocketGeneration(socket) {
  if (typeof socket !== "string" || !socket) {
    throw new ClaudeEnvironmentError(`${CLAUDE_ENV.socket} must be a non-empty string`);
  }
  return createHash("sha256").update(socket, "utf8").digest("hex");
}

export function parseClaudePid(value) {
  if (typeof value !== "string" || !/^[1-9]\d{0,14}$/.test(value)) return undefined;
  return Number(value);
}

export function isProcessAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

// Validates the inherited environment. Errors name variables, never values.
export function readClaudeEnvironment(env = process.env) {
  const missing = [CLAUDE_ENV.selfAddress, CLAUDE_ENV.socket, CLAUDE_ENV.token, CLAUDE_ENV.pid]
    .filter((name) => typeof env[name] !== "string" || env[name] === "");
  if (missing.length > 0) {
    throw new ClaudeEnvironmentError(`missing required environment: ${missing.join(", ")}`);
  }
  let address;
  try {
    address = canonicalizeMailboxAddress(env[CLAUDE_ENV.selfAddress]);
  } catch {
    throw new ClaudeEnvironmentError(`${CLAUDE_ENV.selfAddress} is not a valid mailbox address`);
  }
  if (address.provider !== CLAUDE_PROVIDER || address.machine !== undefined) {
    throw new ClaudeEnvironmentError(
      `${CLAUDE_ENV.selfAddress} must be a local claude:<name> address`,
    );
  }
  const claudePid = parseClaudePid(env[CLAUDE_ENV.pid]);
  if (claudePid === undefined) {
    throw new ClaudeEnvironmentError(`${CLAUDE_ENV.pid} must be a positive integer`);
  }
  return {
    address: address.address,
    name: address.name,
    socket: env[CLAUDE_ENV.socket],
    token: env[CLAUDE_ENV.token],
    claudePid,
  };
}

function safeErrorCode(error) {
  const code = error?.code;
  return typeof code === "string" && /^[A-Z][A-Z0-9_]{1,40}$/.test(code) ? code : "UNKNOWN";
}

const result = (outcome, detail, releaseWatcher = false) =>
  releaseWatcher ? { outcome, detail, releaseWatcher: true } : { outcome, detail };

export function createClaudeWakeupAdapter({
  address,
  socket,
  token,
  claudePid,
  connect = (path) => net.connect(path),
  authGapMs = DEFAULT_AUTH_GAP_MS,
  connectTimeoutMs = DEFAULT_CONNECT_TIMEOUT_MS,
  closeTimeoutMs = DEFAULT_CLOSE_TIMEOUT_MS,
  isAlive = isProcessAlive,
}) {
  if (typeof token !== "string" || token === "") {
    throw new ClaudeEnvironmentError(`${CLAUDE_ENV.token} is required`);
  }
  claudeSocketGeneration(socket);
  const authLine = `${JSON.stringify({ type: "auth", token })}\n`;

  function attempt(prompt) {
    const messageLine = `${JSON.stringify({
      type: "user",
      message: { role: "user", content: prompt },
    })}\n`;

    return new Promise((resolveAttempt) => {
      let settled = false;
      let phase = "connecting";
      let remoteEnded = false;
      let errored = false;
      let writeFailed = false;
      let connection;
      let connectTimer;
      let gapTimer;
      let closeTimer;

      const finish = (value) => {
        if (settled) return;
        settled = true;
        clearTimeout(connectTimer);
        clearTimeout(gapTimer);
        clearTimeout(closeTimer);
        connection?.destroy();
        resolveAttempt(value);
      };
      const closedAfterAuth = (code) =>
        finish(
          result(
            "deferred",
            code
              ? `claude pipe error after authentication before any message was written: ${code}`
              : "claude pipe closed after authentication before any message was written",
            true,
          ),
        );

      try {
        connection = connect(socket);
      } catch (error) {
        finish(result("deferred", `claude pipe connect failed: ${safeErrorCode(error)}`));
        return;
      }

      connectTimer = setTimeout(
        () => finish(result("deferred", "claude pipe connect timed out")),
        connectTimeoutMs,
      );

      connection.on("error", (error) => {
        if (settled) return;
        errored = true;
        const code = safeErrorCode(error);
        if (phase === "connecting") {
          finish(
            result(
              "deferred",
              `claude pipe unavailable before write: ${code}`,
              TERMINAL_CONNECT_CODES.has(code),
            ),
          );
        } else if (phase === "auth") {
          closedAfterAuth(code);
        } else {
          finish(
            result("ambiguous", `claude pipe error after message write began: ${code}`),
          );
        }
      });
      connection.on("end", () => {
        remoteEnded = true;
      });
      connection.on("close", (hadError) => {
        if (settled) return;
        if (phase === "connecting") {
          finish(result("deferred", "claude pipe closed before connect"));
        } else if (phase === "auth") {
          closedAfterAuth();
        } else if (hadError || errored || writeFailed) {
          finish(result("ambiguous", "claude pipe closed with an error after message write"));
        } else {
          finish(
            result(
              "submitted",
              "message line written and pipe closed cleanly; claude pipe returns no acknowledgement",
            ),
          );
        }
      });
      connection.on("connect", () => {
        if (settled) return;
        clearTimeout(connectTimer);
        phase = "auth";
        connection.write(authLine, (error) => {
          if (error && !settled && phase === "auth") closedAfterAuth(safeErrorCode(error));
        });
        gapTimer = setTimeout(() => {
          if (settled) return;
          if (remoteEnded || connection.destroyed) {
            closedAfterAuth();
            return;
          }
          phase = "message";
          connection.write(messageLine, (error) => {
            if (error) writeFailed = true;
          });
          connection.end();
          closeTimer = setTimeout(
            () => finish(result("ambiguous", "claude pipe did not close after message write")),
            closeTimeoutMs,
          );
        }, authGapMs);
      });
    });
  }

  return {
    async wake(request) {
      if (request?.provider !== CLAUDE_PROVIDER || request.address !== address) {
        return result("deferred", "claude adapter is bound to a different mailbox address");
      }
      if (typeof request.prompt !== "string" || request.prompt === "") {
        return result("deferred", "wakeup prompt must be a non-empty string");
      }
      if (!isAlive(claudePid)) {
        return result("deferred", "claude process is no longer running", true);
      }
      return attempt(request.prompt);
    },
  };
}

export function isMainModule(importMetaUrl, argvPath = process.argv[1]) {
  if (!argvPath) return false;
  try {
    return realpathSync(resolve(argvPath)) === realpathSync(fileURLToPath(importMetaUrl));
  } catch {
    return false;
  }
}
