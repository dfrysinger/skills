import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, mkdir, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  DEPRECATED_SESSION_INBOX_DIR_ENV,
  SESSION_CONTROL_DIR_ENV,
  emitSessionControlDeprecation,
  resolveSessionControlRoot,
} from "./storage-root.mjs";

const home = join("test", "home");
const legacyRoot = join(home, ".copilot", "session-inbox");
const defaultRoot = join(home, ".copilot", "session-control");

test("explicit session-control root overrides every other root", () => {
  const selection = resolveSessionControlRoot({
    env: {
      [SESSION_CONTROL_DIR_ENV]: "/explicit/control",
      [DEPRECATED_SESSION_INBOX_DIR_ENV]: "/explicit/inbox",
    },
    home,
    exists: () => true,
  });

  assert.deepEqual(selection, {
    root: "/explicit/control",
    source: "explicit",
  });
});

test("deprecated explicit root overrides default roots", () => {
  const selection = resolveSessionControlRoot({
    env: { [DEPRECATED_SESSION_INBOX_DIR_ENV]: "/explicit/inbox" },
    home,
    exists: () => true,
  });

  assert.equal(selection.root, "/explicit/inbox");
  assert.equal(selection.source, "deprecated-env");
  assert.match(selection.deprecation, /deprecated/);
});

test("explicit roots must be non-empty absolute paths", () => {
  for (const environmentName of [
    SESSION_CONTROL_DIR_ENV,
    DEPRECATED_SESSION_INBOX_DIR_ENV,
  ]) {
    for (const value of ["", "relative/root"]) {
      assert.throws(
        () =>
          resolveSessionControlRoot({
            env: { [environmentName]: value },
            home,
            exists: () => false,
          }),
        new RegExp(`${environmentName} must be a non-empty absolute path`),
      );
    }
  }
});

test("existing legacy default root remains authoritative", () => {
  const selection = resolveSessionControlRoot({
    env: {},
    home,
    exists: (path) => path === legacyRoot,
  });

  assert.equal(selection.root, legacyRoot);
  assert.equal(selection.source, "deprecated-default");
  assert.match(selection.deprecation, /deprecated/);
});

test("legacy default root wins when both default roots exist", () => {
  const observed = [];
  const selection = resolveSessionControlRoot({
    env: {},
    home,
    exists: (path) => {
      observed.push(path);
      return path === legacyRoot || path === defaultRoot;
    },
  });

  assert.equal(selection.root, legacyRoot);
  assert.deepEqual(observed, [legacyRoot]);
});

test("new default root is selected when no higher-precedence root exists", () => {
  const selection = resolveSessionControlRoot({
    env: {},
    home,
    exists: () => false,
  });

  assert.deepEqual(selection, {
    root: defaultRoot,
    source: "default",
  });
});

test("deprecated selections emit diagnostics without changing the root", () => {
  const selection = resolveSessionControlRoot({
    env: { [DEPRECATED_SESSION_INBOX_DIR_ENV]: "/explicit/inbox" },
    home,
    exists: () => false,
  });
  const messages = [];

  emitSessionControlDeprecation(selection, (message) => messages.push(message));

  assert.equal(selection.root, "/explicit/inbox");
  assert.deepEqual(messages, [
    "session-control: COPILOT_SESSION_INBOX_DIR is deprecated; use COPILOT_SESSION_CONTROL_DIR",
  ]);
});

test("non-deprecated selections do not emit diagnostics", () => {
  const messages = [];

  emitSessionControlDeprecation(
    { root: defaultRoot, source: "default" },
    (message) => messages.push(message),
  );

  assert.deepEqual(messages, []);
});

test("legacy symlink entry remains authoritative when its target is unavailable", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-control-root-"));
  try {
    const testHome = join(root, "home");
    const copilotHome = join(testHome, ".copilot");
    await mkdir(copilotHome, { recursive: true });
    await symlink(join(root, "missing-target"), join(copilotHome, "session-inbox"));

    const selection = resolveSessionControlRoot({ env: {}, home: testHome });

    assert.equal(selection.source, "deprecated-default");
    assert.equal(selection.root, join(copilotHome, "session-inbox"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("CLI works through a symlink and keeps diagnostics off stdout", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-control-cli-"));
  try {
    const cli = join(root, "storage-root.mjs");
    const selectedRoot = join(root, "selected");
    await symlink(fileURLToPath(new URL("./storage-root.mjs", import.meta.url)), cli);

    const result = spawnSync(process.execPath, [cli], {
      encoding: "utf8",
      env: Object.fromEntries(
        Object.entries({
          ...process.env,
          [SESSION_CONTROL_DIR_ENV]: undefined,
          [DEPRECATED_SESSION_INBOX_DIR_ENV]: selectedRoot,
        }).filter(([, value]) => value !== undefined),
      ),
    });

    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, `${selectedRoot}\n`);
    assert.match(result.stderr, /COPILOT_SESSION_INBOX_DIR is deprecated/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
