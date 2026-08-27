import {
  appendFileSync,
  mkdirSync,
  readdirSync,
  rmSync,
  statSync,
} from "node:fs";
import { join } from "node:path";

const RETENTION_MS = 14 * 24 * 60 * 60 * 1_000;

export function errorDetails(error) {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      ...(error.code ? { code: error.code } : {}),
      ...(error.stack ? { stack: error.stack } : {}),
    };
  }
  return { message: String(error) };
}

export function createDiagnosticLogger(root, filename, initialContext = {}) {
  const directory = join(root, "logs");
  const path = join(directory, filename);
  let context = { ...initialContext };

  try {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    const cutoff = Date.now() - RETENTION_MS;
    for (const name of readdirSync(directory)) {
      const candidate = join(directory, name);
      try {
        if (statSync(candidate).mtimeMs < cutoff) rmSync(candidate, { force: true });
      } catch {
        // A concurrent logger may rotate or remove its own file.
      }
    }
  } catch (error) {
    console.error(
      `session-inbox could not initialize diagnostic logs: ${errorDetails(error).message}`,
    );
  }

  return {
    path,
    setContext(next) {
      context = { ...context, ...next };
    },
    log(event, details = {}) {
      try {
        appendFileSync(
          path,
          `${JSON.stringify({
            timestamp: new Date().toISOString(),
            event,
            ...context,
            ...details,
          })}\n`,
          { encoding: "utf8", mode: 0o600 },
        );
      } catch (error) {
        console.error(
          `session-inbox could not write diagnostic log ${path}: ${errorDetails(error).message}`,
        );
      }
    },
  };
}
