import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";
import test from "node:test";

import {
  currentSessionName,
  currentTmuxSession,
  preferredAgentName,
} from "./session-identity.mjs";

test("identity prefers the current tmux name and refreshes after a rename", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-identity-"));
  const previousPath = process.env.PATH;
  const previousPane = process.env.TMUX_PANE;
  const previousState = process.env.MOCK_TMUX_NAME;
  try {
    const executable = join(root, "tmux");
    const state = join(root, "tmux-name");
    await writeFile(
      executable,
      `#!/usr/bin/env bash
cat "$MOCK_TMUX_NAME"
`,
    );
    await chmod(executable, 0o700);
    process.env.PATH = `${root}${delimiter}${previousPath}`;
    process.env.TMUX_PANE = "%1";
    process.env.MOCK_TMUX_NAME = state;
    await writeFile(state, "hotel\n");
    assert.equal(await currentTmuxSession(), "hotel");
    await writeFile(state, "india\n");
    assert.equal(await currentTmuxSession(), "india");

    const session = {
      sessionId: "session-1",
      rpc: {
        metadata: {
          async snapshot() {
            return { workspace: { id: "session-1", name: "session-name" } };
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
      rpc: {
        metadata: {
          async snapshot() {
            return { workspace: { id: "session-1", name: "india" } };
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

test("identity falls back to the session name when tmux lookup fails", async () => {
  const root = await mkdtemp(join(tmpdir(), "session-identity-failed-tmux-"));
  const previousPath = process.env.PATH;
  const previousPane = process.env.TMUX_PANE;
  try {
    const executable = join(root, "tmux");
    await writeFile(executable, "#!/usr/bin/env bash\nexit 1\n");
    await chmod(executable, 0o700);
    process.env.PATH = `${root}${delimiter}${previousPath}`;
    process.env.TMUX_PANE = "%stale";
    const session = {
      rpc: {
        metadata: {
          async snapshot() {
            return { workspace: { name: "india" } };
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
