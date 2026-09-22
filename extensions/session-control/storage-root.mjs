#!/usr/bin/env node

import { lstatSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const SESSION_CONTROL_DIR_ENV = "COPILOT_SESSION_CONTROL_DIR";
export const DEPRECATED_SESSION_INBOX_DIR_ENV =
  "COPILOT_SESSION_INBOX_DIR";

function pathEntryExists(path) {
  try {
    lstatSync(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT" || error?.code === "ENOTDIR") return false;
    throw error;
  }
}

function explicitRoot(value, environmentName) {
  if (!value || !isAbsolute(value)) {
    throw new Error(`${environmentName} must be a non-empty absolute path`);
  }
  return value;
}

export function resolveSessionControlRoot({
  env = process.env,
  home = homedir(),
  exists = pathEntryExists,
} = {}) {
  if (env[SESSION_CONTROL_DIR_ENV] !== undefined) {
    return {
      root: explicitRoot(env[SESSION_CONTROL_DIR_ENV], SESSION_CONTROL_DIR_ENV),
      source: "explicit",
    };
  }
  if (env[DEPRECATED_SESSION_INBOX_DIR_ENV] !== undefined) {
    return {
      root: explicitRoot(
        env[DEPRECATED_SESSION_INBOX_DIR_ENV],
        DEPRECATED_SESSION_INBOX_DIR_ENV,
      ),
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
  if (!process.argv[1]) return false;
  const modulePath = fileURLToPath(import.meta.url);
  try {
    return realpathSync(process.argv[1]) === realpathSync(modulePath);
  } catch {
    return resolve(process.argv[1]) === resolve(modulePath);
  }
}

if (isEntrypoint()) {
  const selection = resolveSessionControlRoot();
  emitSessionControlDeprecation(selection);
  process.stdout.write(`${selection.root}\n`);
}
