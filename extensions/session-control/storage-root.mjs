#!/usr/bin/env node

import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

export const SESSION_CONTROL_DIR_ENV = "COPILOT_SESSION_CONTROL_DIR";
export const DEPRECATED_SESSION_INBOX_DIR_ENV =
  "COPILOT_SESSION_INBOX_DIR";

export function resolveSessionControlRoot({
  env = process.env,
  home = homedir(),
  exists = existsSync,
} = {}) {
  if (env[SESSION_CONTROL_DIR_ENV] !== undefined) {
    return {
      root: env[SESSION_CONTROL_DIR_ENV],
      source: "explicit",
    };
  }
  if (env[DEPRECATED_SESSION_INBOX_DIR_ENV] !== undefined) {
    return {
      root: env[DEPRECATED_SESSION_INBOX_DIR_ENV],
      source: "deprecated-env",
      deprecation:
        "COPILOT_SESSION_INBOX_DIR is deprecated; use COPILOT_SESSION_CONTROL_DIR",
    };
  }

  const legacyRoot = join(home, ".copilot", "session-inbox");
  if (exists(legacyRoot)) {
    return {
      root: legacyRoot,
      source: "deprecated-default",
      deprecation: `using deprecated session-control storage root ${legacyRoot}; remove or rename it only after shared requests and self-compact operations are drained`,
    };
  }
  return {
    root: join(home, ".copilot", "session-control"),
    source: "default",
  };
}

export function emitSessionControlDeprecation(
  selection,
  write = (message) => console.error(message),
) {
  if (selection.deprecation) {
    write(`session-control: ${selection.deprecation}`);
  }
}

function isEntrypoint() {
  return process.argv[1] === fileURLToPath(import.meta.url);
}

if (isEntrypoint()) {
  const selection = resolveSessionControlRoot();
  emitSessionControlDeprecation(selection);
  process.stdout.write(`${selection.root}\n`);
}
