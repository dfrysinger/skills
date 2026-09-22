import assert from "node:assert/strict";
import { join } from "node:path";
import test from "node:test";

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
