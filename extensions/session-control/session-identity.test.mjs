import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";
import test from "node:test";

import {
  currentSessionName,
  currentTmuxSession,
  isForegroundSession,
  preferredAgentName,
} from "./session-identity.mjs";

function foregroundConnection(sessionId) {
  return {
    async sendRequest(method, params) {
      assert.equal(method, "session.getForeground");
      assert.deepEqual(params, {});
      return { sessionId };
    },
  };
}

test("foreground ownership follows the native host rather than the joined session", async () => {
  let foreground = "old";
  const session = {
    sessionId: "old",
    connection: {
      async sendRequest() { return { sessionId: foreground }; },
    },
  };
  assert.equal(await isForegroundSession(session), true);
  foreground = "current";
  assert.equal(await isForegroundSession(session), false);
  assert.equal(await preferredAgentName(session), undefined);
  foreground = undefined;
  assert.equal(await isForegroundSession(session), false);
});

test("foreground ownership refuses unavailable, malformed and stalled answers", async () => {
  await assert.rejects(isForegroundSession({}), /unavailable/);
  for (const response of [null, [], { sessionId: 1 }, { sessionId: "" }]) {
    await assert.rejects(
      isForegroundSession({
        sessionId: "old",
        connection: { async sendRequest() { return response; } },
      }),
      /invalid foreground/,
    );
  }
  await assert.rejects(
    isForegroundSession({
      sessionId: "old",
      connection: { sendRequest() { return new Promise(() => {}); } },
    }),
    /timed out/,
  );
});

async function writeExecutable(root, body) {
  if (process.platform === "win32") {
    const executable = join(root, "tmux.cmd");
    await writeFile(executable, `@echo off\r\n${body}\r\n`);
    return executable;
  }
  const executable = join(root, "tmux");
  await writeFile(executable, `#!/usr/bin/env bash\n${body}\n`);
  await chmod(executable, 0o700);
  return executable;
}

test("identity prefers the current tmux name and refreshes after a rename", {
  skip: process.platform === "win32",
}, async () => {
  const root = await mkdtemp(join(tmpdir(), "session-identity-"));
  const previousPath = process.env.PATH;
  const previousPane = process.env.TMUX_PANE;
  const previousState = process.env.MOCK_TMUX_NAME;
  try {
    const state = join(root, "tmux-name");
    await writeExecutable(
      root,
      process.platform === "win32"
        ? 'type "%MOCK_TMUX_NAME%"'
        : 'cat "$MOCK_TMUX_NAME"',
    );
    process.env.PATH = `${root}${delimiter}${previousPath}`;
    process.env.TMUX_PANE = "%1";
    process.env.MOCK_TMUX_NAME = state;
    await writeFile(state, "hotel\n");
    assert.equal(await currentTmuxSession(), "hotel");
    await writeFile(state, "india\n");
    assert.equal(await currentTmuxSession(), "india");

    const session = {
      sessionId: "session-1",
      connection: foregroundConnection("session-1"),
      rpc: {
        metadata: {
          async snapshot() {
            return {
              workspace: {
                id: "session-1",
                name: "session-name",
                user_named: true,
              },
            };
          },
        },
      },
    };
    assert.equal(await preferredAgentName(session), "india");
  } finally {
    process.env.PATH = previousPath;
    if (previousPane === undefined) delete process.env.TMUX_PANE;
    else process.env.TMUX_PANE = previousPane;
    if (previousState === undefined) delete process.env.MOCK_TMUX_NAME;
    else process.env.MOCK_TMUX_NAME = previousState;
    await rm(root, { recursive: true, force: true });
  }
});

test("identity falls back to the current live Copilot session name", async () => {
  const previousPane = process.env.TMUX_PANE;
  try {
    delete process.env.TMUX_PANE;
    const session = {
      sessionId: "session-1",
      connection: foregroundConnection("session-1"),
      rpc: {
        metadata: {
          async snapshot() {
            return {
              workspace: { id: "session-1", name: "india", user_named: true },
            };
          },
        },
      },
    };
    assert.equal(await currentSessionName(session), "india");
    assert.equal(await preferredAgentName(session), "india");
  } finally {
    if (previousPane === undefined) delete process.env.TMUX_PANE;
    else process.env.TMUX_PANE = previousPane;
  }
});

test("identity ignores an auto-generated session title", async () => {
  const previousPane = process.env.TMUX_PANE;
  try {
    delete process.env.TMUX_PANE;
    const session = {
      rpc: {
        metadata: {
          async snapshot() {
            return {
              workspace: {
                id: "session-1",
                name: "Set Up Local Dev Builds",
                user_named: false,
              },
            };
          },
        },
      },
    };

    assert.equal(await currentSessionName(session), undefined);
    assert.equal(await preferredAgentName(session), undefined);
  } finally {
    if (previousPane === undefined) delete process.env.TMUX_PANE;
    else process.env.TMUX_PANE = previousPane;
  }
});

test("identity falls back to the session name when tmux lookup fails", {
  skip: process.platform === "win32",
}, async () => {
  const root = await mkdtemp(join(tmpdir(), "session-identity-failed-tmux-"));
  const previousPath = process.env.PATH;
  const previousPane = process.env.TMUX_PANE;
  try {
    await writeExecutable(
      root,
      process.platform === "win32" ? "exit /b 1" : "exit 1",
    );
    process.env.PATH = `${root}${delimiter}${previousPath}`;
    process.env.TMUX_PANE = "%stale";
    const session = {
      sessionId: "session-1",
      connection: foregroundConnection("session-1"),
      rpc: {
        metadata: {
          async snapshot() {
            return { workspace: { name: "india", user_named: true } };
          },
        },
      },
    };

    await assert.rejects(currentTmuxSession());
    assert.equal(await preferredAgentName(session), "india");
  } finally {
    process.env.PATH = previousPath;
    if (previousPane === undefined) delete process.env.TMUX_PANE;
    else process.env.TMUX_PANE = previousPane;
    await rm(root, { recursive: true, force: true });
  }
});
