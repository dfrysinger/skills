// Codex native mailbox wakeup adapter.
//
// The launcher owns the app-server, TUI, Job Object, and watcher process
// lifetime. This adapter only connects to that already-running loopback
// server. Its capability token is held in the adapter closure and is sent only
// in the WebSocket Authorization header; it never enters argv, files, logs, or
// returned details.
import { createHash, randomBytes } from "node:crypto";
import net from "node:net";
import { isAbsolute, resolve } from "node:path";

import { canonicalizeMailboxAddress } from "./mailbox-core.mjs";

export const CODEX_PROVIDER = "codex";
export const CODEX_ENV = Object.freeze({
  selfAddress: "MAILBOX_SELF_ADDRESS",
  endpoint: "CODEX_APP_SERVER_ENDPOINT",
  token: "CODEX_APP_SERVER_TOKEN",
  workspace: "CODEX_WORKSPACE",
  launcherPid: "CODEX_LAUNCHER_PID",
  allowAll: "CODEX_ALLOW_ALL",
});

const DEFAULT_CONNECT_TIMEOUT_MS = 5_000;
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;
const MAX_WEBSOCKET_MESSAGE_BYTES = 1_048_576;
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "[::1]"]);
const WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

export class CodexEnvironmentError extends Error {
  constructor(message) {
    super(message);
    this.name = "CodexEnvironmentError";
  }
}

export class CodexTransportError extends Error {
  constructor(phase, code = "UNKNOWN") {
    super(`codex transport ${phase} error: ${code}`);
    this.name = "CodexTransportError";
    this.phase = phase;
    this.code = safeCode(code);
  }
}

function safeCode(value) {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  return typeof value === "string" && /^[A-Z][A-Z0-9_]{1,40}$/.test(value)
    ? value
    : "UNKNOWN";
}

function result(outcome, detail, releaseWatcher = false) {
  return releaseWatcher ? { outcome, detail, releaseWatcher: true } : { outcome, detail };
}

function isLoopbackEndpoint(value) {
  let endpoint;
  try {
    endpoint = new URL(value);
  } catch {
    throw new CodexEnvironmentError(`${CODEX_ENV.endpoint} must be a valid ws:// loopback URL`);
  }
  if (
    endpoint.protocol !== "ws:" ||
    !LOOPBACK_HOSTS.has(endpoint.hostname.toLowerCase()) ||
    endpoint.username ||
    endpoint.password
  ) {
    throw new CodexEnvironmentError(
      `${CODEX_ENV.endpoint} must be a ws://127.0.0.1 or ws://[::1] URL`,
    );
  }
  return endpoint;
}

export function parseLauncherPid(value) {
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

export function codexGeneration({ endpoint, workspace, launcherPid }) {
  const parsed = isLoopbackEndpoint(endpoint);
  if (!isAbsolute(workspace)) {
    throw new CodexEnvironmentError(`${CODEX_ENV.workspace} must be an absolute path`);
  }
  if (!Number.isSafeInteger(launcherPid) || launcherPid < 1) {
    throw new CodexEnvironmentError(`${CODEX_ENV.launcherPid} must be a positive integer`);
  }
  return createHash("sha256")
    .update(`${parsed.href}\0${normalizeWorkspace(workspace)}\0${launcherPid}`, "utf8")
    .digest("hex");
}

function normalizeWorkspace(workspace) {
  return process.platform === "win32"
    ? resolve(workspace).toLowerCase()
    : resolve(workspace);
}

// Validates names and shape without ever returning a token in an error.
export function readCodexEnvironment(env = process.env) {
  const missing = [
    CODEX_ENV.selfAddress,
    CODEX_ENV.endpoint,
    CODEX_ENV.token,
    CODEX_ENV.workspace,
    CODEX_ENV.launcherPid,
  ].filter((name) => typeof env[name] !== "string" || env[name] === "");
  if (missing.length > 0) {
    throw new CodexEnvironmentError(`missing required environment: ${missing.join(", ")}`);
  }
  let parsedAddress;
  try {
    parsedAddress = canonicalizeMailboxAddress(env[CODEX_ENV.selfAddress]);
  } catch {
    throw new CodexEnvironmentError(`${CODEX_ENV.selfAddress} is not a valid mailbox address`);
  }
  if (parsedAddress.provider !== CODEX_PROVIDER || parsedAddress.machine !== undefined) {
    throw new CodexEnvironmentError(
      `${CODEX_ENV.selfAddress} must be a local codex:<name> address`,
    );
  }
  const endpoint = isLoopbackEndpoint(env[CODEX_ENV.endpoint]);
  if (!isAbsolute(env[CODEX_ENV.workspace])) {
    throw new CodexEnvironmentError(`${CODEX_ENV.workspace} must be an absolute path`);
  }
  const launcherPid = parseLauncherPid(env[CODEX_ENV.launcherPid]);
  if (launcherPid === undefined) {
    throw new CodexEnvironmentError(`${CODEX_ENV.launcherPid} must be a positive integer`);
  }
  if (/[\r\n]/.test(env[CODEX_ENV.token])) {
    throw new CodexEnvironmentError(`${CODEX_ENV.token} contains invalid characters`);
  }
  if (
    env[CODEX_ENV.allowAll] !== undefined &&
    env[CODEX_ENV.allowAll] !== "true" &&
    env[CODEX_ENV.allowAll] !== "false"
  ) {
    throw new CodexEnvironmentError(`${CODEX_ENV.allowAll} must be true or false`);
  }
  return {
    address: parsedAddress.address,
    name: parsedAddress.name,
    endpoint: endpoint.href,
    token: env[CODEX_ENV.token],
    workspace: normalizeWorkspace(env[CODEX_ENV.workspace]),
    launcherPid,
    allowAll: env[CODEX_ENV.allowAll] === "true",
  };
}

function responseResult(response) {
  return response && typeof response === "object" && response.result && !response.error
    ? response.result
    : undefined;
}

function responseErrorCode(response) {
  return response?.error?.code;
}

function isWrongTurn(response) {
  return responseErrorCode(response) === -32600;
}

function isAcceptedStart(response) {
  return typeof responseResult(response)?.turn?.id === "string";
}

function isAcceptedSteer(response, expectedTurnId) {
  return responseResult(response)?.turnId === expectedTurnId;
}

function transportDetail(error, prefix) {
  return `${prefix}: ${safeCode(error?.code)}`;
}

async function rpcStateRequest(session, method, params) {
  try {
    const response = await session.request(method, params);
    if (!responseResult(response)) {
      return { kind: "deferred", detail: `codex ${method} was refused before wakeup submission` };
    }
    return { kind: "ok", response };
  } catch (error) {
    return {
      kind: "deferred",
      detail: transportDetail(error, `codex ${method} unavailable before wakeup submission`),
    };
  }
}

async function readExactThread(session, workspace) {
  const loaded = await rpcStateRequest(session, "thread/loaded/list", {
    cursor: null,
    limit: 2,
  });
  if (loaded.kind !== "ok") return loaded;
  const loadedIds = loaded.response.result.data;
  if (!Array.isArray(loadedIds) || loadedIds.length !== 1 || loaded.response.result.nextCursor !== null) {
    return { kind: "deferred", detail: "codex does not have exactly one loaded thread" };
  }
  const threadId = loadedIds[0];
  if (typeof threadId !== "string" || threadId === "") {
    return { kind: "deferred", detail: "codex loaded thread identity is invalid" };
  }
  const thread = await rpcStateRequest(session, "thread/read", {
    threadId,
    includeTurns: false,
  });
  if (thread.kind !== "ok") return thread;
  const cwd = thread.response.result.thread?.cwd;
  if (
    typeof cwd !== "string" ||
    cwd === "" ||
    !isAbsolute(cwd) ||
    normalizeWorkspace(cwd) !== workspace
  ) {
    return { kind: "deferred", detail: "codex loaded thread workspace does not match launcher workspace" };
  }
  const status = thread.response.result.thread?.status;
  if (status?.type === "idle") return { kind: "idle", threadId };
  if (status?.type !== "active") {
    return { kind: "deferred", detail: "codex loaded thread is not safely idle or active" };
  }
  const turns = await rpcStateRequest(session, "thread/turns/list", {
    threadId,
    cursor: null,
    limit: 100,
    sortDirection: "desc",
    itemsView: "summary",
  });
  if (turns.kind !== "ok") return turns;
  const activeTurns = (turns.response.result.data ?? []).filter(
    (turn) => turn?.status === "inProgress" && typeof turn.id === "string",
  );
  if (activeTurns.length !== 1) {
    return { kind: "deferred", detail: "codex does not expose exactly one active turn" };
  }
  return { kind: "active", threadId, turnId: activeTurns[0].id };
}

async function submitForState(
  session,
  state,
  prompt,
  { retry = false, allowAll = false } = {},
) {
  const method = state.kind === "idle" ? "turn/start" : "turn/steer";
  const params =
    state.kind === "idle"
      ? {
          threadId: state.threadId,
          input: [{ type: "text", text: prompt }],
          ...(allowAll
            ? {
                approvalPolicy: "never",
                sandboxPolicy: { type: "dangerFullAccess" },
              }
            : {}),
        }
      : {
          threadId: state.threadId,
          expectedTurnId: state.turnId,
          input: [{ type: "text", text: prompt }],
        };
  let response;
  try {
    response = await session.request(method, params);
  } catch (error) {
    return result(
      "ambiguous",
      transportDetail(error, `codex ${method} connection ended after wakeup request`),
    );
  }
  if (state.kind === "idle" && isAcceptedStart(response)) {
    return result(
      "submitted",
      "codex turn/start accepted; a concurrent start may merge into the same active turn",
    );
  }
  if (state.kind === "active" && isAcceptedSteer(response, state.turnId)) {
    return result("submitted", "codex turn/steer accepted for the exact active turn");
  }
  if (state.kind === "active" && isWrongTurn(response)) {
    if (retry) {
      return result("deferred", "codex active turn changed again before retry");
    }
    const reread = await readExactThread(session, state.workspace);
    if (reread.kind !== "idle" && reread.kind !== "active") {
      return result("deferred", reread.detail);
    }
    return submitForState(session, reread, prompt, { retry: true, allowAll });
  }
  return result("deferred", `codex ${method} refused before wakeup submission`);
}

export function createCodexWakeupAdapter({
  address,
  endpoint,
  token,
  workspace,
  launcherPid,
  allowAll = false,
  transport = nativeCodexTransport,
  isAlive = isProcessAlive,
}) {
  if (typeof token !== "string" || token === "") {
    throw new CodexEnvironmentError(`${CODEX_ENV.token} is required`);
  }
  const generation = codexGeneration({ endpoint, workspace, launcherPid });
  const expectedWorkspace = normalizeWorkspace(workspace);

  return {
    generation,
    async wake(request) {
      if (request?.provider !== CODEX_PROVIDER || request.address !== address) {
        return result("deferred", "codex adapter is bound to a different mailbox address");
      }
      if (typeof request.prompt !== "string" || request.prompt === "") {
        return result("deferred", "wakeup prompt must be a non-empty string");
      }
      if (!isAlive(launcherPid)) {
        return result("deferred", "codex launcher process is no longer running", true);
      }
      let session;
      try {
        session = await transport.connect({ endpoint, token });
      } catch (error) {
        return result("deferred", transportDetail(error, "codex endpoint unavailable"));
      }
      try {
        const initialized = await rpcStateRequest(session, "initialize", {
          clientInfo: {
            name: "mailbox-codex-watcher",
            title: "Mailbox Codex Watcher",
            version: "1",
          },
          capabilities: null,
        });
        if (initialized.kind !== "ok") {
          return result("deferred", initialized.detail);
        }
        const state = await readExactThread(session, expectedWorkspace);
        if (state.kind !== "idle" && state.kind !== "active") {
          return result("deferred", state.detail);
        }
        state.workspace = expectedWorkspace;
        return await submitForState(session, state, request.prompt, { allowAll });
      } finally {
        session.close?.();
      }
    },
  };
}

class WebSocketRpcSession {
  #socket;
  #buffer = Buffer.alloc(0);
  #pending = new Map();
  #nextId = 1;
  #closed = false;
  #fragment;

  constructor(socket, requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS) {
    this.#socket = socket;
    this.requestTimeoutMs = requestTimeoutMs;
    socket.on("data", (chunk) => this.#receive(chunk));
    socket.on("error", (error) => this.#failPending(error));
    socket.on("close", () => this.#failPending(new CodexTransportError("request", "CLOSED")));
  }

  request(method, params) {
    if (this.#closed) return Promise.reject(new CodexTransportError("request", "CLOSED"));
    const id = this.#nextId++;
    const payload = JSON.stringify({ method, id, params });
    return new Promise((resolveRequest, rejectRequest) => {
      const timer = setTimeout(() => {
        const pending = this.#pending.get(id);
        if (!pending) return;
        this.#pending.delete(id);
        pending.reject(new CodexTransportError("request", "ETIMEDOUT"));
        this.#socket.destroy();
      }, this.requestTimeoutMs);
      this.#pending.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
      this.#sendFrame(0x1, Buffer.from(payload, "utf8"), (error) => {
        if (!error) return;
        const pending = this.#pending.get(id);
        this.#pending.delete(id);
        clearTimeout(pending?.timer);
        pending?.reject(new CodexTransportError("request", error.code));
      });
    });
  }

  close() {
    if (this.#closed) return;
    this.#closed = true;
    this.#fragment = undefined;
    this.#socket.destroy();
  }

  receiveInitial(chunk) {
    this.#receive(chunk);
  }

  #sendFrame(opcode, payload, callback) {
    const mask = randomBytes(4);
    const length = payload.length;
    let header;
    if (length < 126) {
      header = Buffer.from([0x80 | opcode, 0x80 | length]);
    } else if (length <= 0xffff) {
      header = Buffer.alloc(4);
      header[0] = 0x80 | opcode;
      header[1] = 0x80 | 126;
      header.writeUInt16BE(length, 2);
    } else {
      callback?.(Object.assign(new Error("frame too large"), { code: "EMSGSIZE" }));
      return;
    }
    const body = Buffer.from(payload);
    for (let index = 0; index < body.length; index += 1) body[index] ^= mask[index % 4];
    this.#socket.write(Buffer.concat([header, mask, body]), callback);
  }

  #receive(chunk) {
    this.#buffer = Buffer.concat([this.#buffer, chunk]);
    while (this.#buffer.length >= 2) {
      const first = this.#buffer[0];
      const second = this.#buffer[1];
      let offset = 2;
      let length = second & 0x7f;
      if (length === 126) {
        if (this.#buffer.length < 4) return;
        length = this.#buffer.readUInt16BE(2);
        offset = 4;
      } else if (length === 127) {
        if (this.#buffer.length < 10) return;
        const longLength = this.#buffer.readBigUInt64BE(2);
        if (longLength > BigInt(MAX_WEBSOCKET_MESSAGE_BYTES)) {
          this.#failPending(new CodexTransportError("request", "EMSGSIZE"));
          return;
        }
        length = Number(longLength);
        offset = 10;
      }
      const masked = (second & 0x80) !== 0;
      const maskLength = masked ? 4 : 0;
      if (this.#buffer.length < offset + maskLength + length) return;
      let payload = this.#buffer.subarray(offset + maskLength, offset + maskLength + length);
      if (masked) {
        const mask = this.#buffer.subarray(offset, offset + 4);
        payload = Buffer.from(payload);
        for (let index = 0; index < payload.length; index += 1) payload[index] ^= mask[index % 4];
      }
      this.#buffer = this.#buffer.subarray(offset + maskLength + length);
      const fin = (first & 0x80) !== 0;
      let opcode = first & 0x0f;
      if (opcode === 0x8) {
        this.#failPending(new CodexTransportError("request", "CLOSED"));
        return;
      }
      if (opcode === 0x9) {
        this.#sendFrame(0xa, payload);
        continue;
      }
      if (opcode === 0x1 && !fin) {
        if (payload.length > MAX_WEBSOCKET_MESSAGE_BYTES) {
          this.#failPending(new CodexTransportError("request", "EMSGSIZE"));
          return;
        }
        this.#fragment = payload;
        continue;
      }
      if (opcode === 0x0 && this.#fragment) {
        if (this.#fragment.length + payload.length > MAX_WEBSOCKET_MESSAGE_BYTES) {
          this.#failPending(new CodexTransportError("request", "EMSGSIZE"));
          return;
        }
        this.#fragment = Buffer.concat([this.#fragment, payload]);
        if (!fin) continue;
        payload = this.#fragment;
        this.#fragment = undefined;
        opcode = 0x1;
      }
      if (opcode !== 0x1) continue;
      let response;
      try {
        response = JSON.parse(payload.toString("utf8"));
      } catch {
        this.#failPending(new CodexTransportError("request", "EPROTO"));
        return;
      }
      const pending = this.#pending.get(response?.id);
      if (pending) {
        this.#pending.delete(response.id);
        clearTimeout(pending.timer);
        pending.resolve(response);
      }
    }
  }

  #failPending(error) {
    if (this.#closed) return;
    this.#closed = true;
    for (const { reject, timer } of this.#pending.values()) {
      clearTimeout(timer);
      reject(error instanceof CodexTransportError ? error : new CodexTransportError("request", error?.code));
    }
    this.#pending.clear();
    this.#fragment = undefined;
    this.#socket.destroy();
  }
}

export async function connectCodexWebSocket({
  endpoint,
  token,
  connectTimeoutMs = DEFAULT_CONNECT_TIMEOUT_MS,
}) {
  const url = isLoopbackEndpoint(endpoint);
  const key = randomBytes(16).toString("base64");
  const expectedAccept = createHash("sha1").update(`${key}${WEBSOCKET_GUID}`, "utf8").digest("base64");
  return new Promise((resolveConnect, rejectConnect) => {
    let settled = false;
    let headerBuffer = Buffer.alloc(0);
    const socket = net.createConnection({
      host: url.hostname.replace(/^\[|\]$/g, ""),
      port: url.port ? Number(url.port) : 80,
    });
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      callback(value);
    };
    const timer = setTimeout(() => {
      socket.destroy();
      finish(rejectConnect, new CodexTransportError("connect", "ETIMEDOUT"));
    }, connectTimeoutMs);
    socket.once("error", (error) =>
      finish(rejectConnect, new CodexTransportError("connect", error?.code)),
    );
    socket.once("connect", () => {
      const path = `${url.pathname || "/"}${url.search}`;
      socket.write(
        [
          `GET ${path} HTTP/1.1`,
          `Host: ${url.host}`,
          "Upgrade: websocket",
          "Connection: Upgrade",
          `Sec-WebSocket-Key: ${key}`,
          "Sec-WebSocket-Version: 13",
          `Authorization: Bearer ${token}`,
          "",
          "",
        ].join("\r\n"),
      );
    });
    socket.on("data", function handshake(chunk) {
      if (settled) return;
      headerBuffer = Buffer.concat([headerBuffer, chunk]);
      const boundary = headerBuffer.indexOf("\r\n\r\n");
      if (boundary === -1) return;
      const header = headerBuffer.subarray(0, boundary).toString("ascii");
      const lines = header.split("\r\n");
      const headers = new Map(
        lines.slice(1).map((line) => {
          const separator = line.indexOf(":");
          return [line.slice(0, separator).trim().toLowerCase(), line.slice(separator + 1).trim()];
        }),
      );
      if (!/^HTTP\/1\.1 101\b/.test(lines[0]) || headers.get("sec-websocket-accept") !== expectedAccept) {
        socket.destroy();
        finish(rejectConnect, new CodexTransportError("connect", "EAUTH"));
        return;
      }
      socket.removeListener("data", handshake);
      const session = new WebSocketRpcSession(socket);
      const remaining = headerBuffer.subarray(boundary + 4);
      if (remaining.length > 0) session.receiveInitial(remaining);
      finish(resolveConnect, session);
    });
  });
}

export const nativeCodexTransport = Object.freeze({ connect: connectCodexWebSocket });
