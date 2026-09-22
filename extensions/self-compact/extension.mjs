import { execFile } from "node:child_process";
import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import { joinSession } from "@github/copilot-sdk/extension";

const execFileAsync = promisify(execFile);
const extensionDirectory = dirname(fileURLToPath(import.meta.url));
const submitter =
  process.env.SELF_COMPACT_SUBMITTER ??
  join(
    extensionDirectory,
    "../../skills/self-compact/scripts/submit-compact.mjs",
  );
const nodeBin = process.env.SELF_COMPACT_NODE_BIN ?? "node";
const sessionStateRoot =
  process.env.SELF_COMPACT_SESSION_STATE_DIR ??
  join(homedir(), ".copilot", "session-state");
let session;

async function readObjective() {
  const saved = await session.rpc.workspaces.readAutopilotObjective();
  if (!saved.content) return null;
  try {
    const state = JSON.parse(saved.content);
    const current = state?.current;
    if (
      current &&
      typeof current.objective === "string" &&
      current.objective &&
      typeof current.status === "string"
    ) {
      return current;
    }
  } catch {
    // A concurrently replaced objective is not stable enough to pause.
  }
  return null;
}

async function waitForObjectiveStatus(expected, objective) {
  const deadline = Date.now() + 2_000;
  while (Date.now() < deadline) {
    const current = await readObjective();
    if (current?.objective === objective && expected.includes(current.status)) {
      return current;
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(`native autopilot objective did not reach ${expected.join(" or ")}`);
}

function preparedObjectivePath(sessionId) {
  return join(
    sessionStateRoot,
    sessionId,
    "files",
    "self-compact.autopilot-objective.json",
  );
}

async function writePreparedObjective(sessionId, objective) {
  const path = preparedObjectivePath(sessionId);
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  await writeFile(
    temporary,
    `${JSON.stringify(
      {
        version: 1,
        sessionId,
        objective,
        preparedAt: new Date().toISOString(),
      },
      null,
      2,
    )}\n`,
    { mode: 0o600 },
  );
  await rename(temporary, path);
}

async function readPreparedObjective(sessionId) {
  const path = preparedObjectivePath(sessionId);
  let text;
  try {
    text = await readFile(path, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
  try {
    const prepared = JSON.parse(text);
    const age = Date.now() - Date.parse(prepared.preparedAt);
    if (
      prepared?.version === 1 &&
      prepared.sessionId === sessionId &&
      typeof prepared.objective === "string" &&
      prepared.objective &&
      Number.isFinite(age) &&
      age >= 0 &&
      age <= 5 * 60_000
    ) {
      return prepared.objective;
    }
  } catch {
    // Malformed or expired state cannot authorize an objective restore.
  }
  await rm(path, { force: true });
  return null;
}

async function removePreparedObjective(sessionId) {
  await rm(preparedObjectivePath(sessionId), { force: true });
}

async function pauseActiveObjective(sessionId) {
  const current = await readObjective();
  if (current?.status !== "active") {
    await removePreparedObjective(sessionId);
    return null;
  }
  const invocation = await session.rpc.commands.invoke({
    name: "autopilot",
    input: "",
  });
  if (invocation.kind !== "text" && invocation.kind !== "completed") {
    throw new Error(`autopilot pause returned unsupported result ${invocation.kind}`);
  }
  await waitForObjectiveStatus(["paused"], current.objective);
  await writePreparedObjective(sessionId, current.objective);
  return current.objective;
}

async function restoreObjective(objective) {
  const invocation = await session.rpc.commands.invoke({
    name: "autopilot",
    input: objective,
  });
  if (invocation.kind === "agent-prompt") {
    await session.send({
      prompt: invocation.prompt,
      mode: "immediate",
      agentMode: invocation.mode,
    });
  } else if (invocation.kind !== "text") {
    throw new Error(`autopilot restore returned unsupported result ${invocation.kind}`);
  }
  await waitForObjectiveStatus(["active", "completed"], objective);
}

function validBrief(value) {
  return (
    typeof value === "string" &&
    value.length <= 16_384 &&
    !value.includes("\0") &&
    /^Keep:[ \t]*\S[^\n]*/.test(value) &&
    /\nDrop:[^\n]*/.test(value) &&
    /\nAfter compaction:[ \t]*\S[^\n]*do not compact again[^\n]*/.test(value)
  );
}

const selfCompactTool = {
  name: "self_compact",
  description:
    "Prepare or arm one native steered compaction. While autopilot is active, call with action 'prepare' first. Then call with the brief as the only and final tool request.",
  parameters: {
    type: "object",
    properties: {
      action: {
        type: "string",
        enum: ["prepare", "compact"],
        description:
          "Use 'prepare' in a prior assistant message while autopilot is active. Omit or use 'compact' for the final brief-bearing call.",
      },
      brief: {
        type: "string",
        description:
          "The complete Keep/Drop/After compaction brief. It must start with Keep:, include Drop:, and end with an After compaction: instruction containing the exact words 'do not compact again'.",
      },
    },
    additionalProperties: false,
  },
  defer: "never",
  handler: async ({ action = "compact", brief }, invocation) => {
    if (action === "prepare") {
      try {
        const objective = await pauseActiveObjective(invocation.sessionId);
        return objective
          ? "Native autopilot is paused and its exact objective is staged. Invoke self_compact with the brief as the only and final tool request in the next assistant message."
          : "No active native autopilot objective required preparation. Invoke self_compact with the brief as the only and final tool request.";
      } catch (error) {
        return {
          textResultForLlm: `Self-compact preparation failed: ${
            error?.message ?? String(error)
          }`,
          resultType: "failure",
        };
      }
    }
    if (!validBrief(brief)) {
      return {
        textResultForLlm:
          "Self-compact was not armed: brief must be at most 16 KiB and contain nonempty Keep:, Drop:, and After compaction: sections; After compaction must include 'do not compact again'.",
        resultType: "failure",
      };
    }
    let preparedObjective = null;
    try {
      const current = await readObjective();
      if (current?.status === "active") {
        throw new Error(
          "native autopilot is active; call self_compact_prepare first, then invoke self_compact as the only and final tool request",
        );
      }
      preparedObjective = await readPreparedObjective(invocation.sessionId);
      const { stdout } = await execFileAsync(
        nodeBin,
        [submitter, "--tool-call-id", invocation.toolCallId],
        {
          env: {
            ...process.env,
            COPILOT_AGENT_SESSION_ID: invocation.sessionId,
            ...(preparedObjective
              ? {
                  SELF_COMPACT_AUTOPILOT_OBJECTIVE_BASE64:
                    Buffer.from(preparedObjective, "utf8").toString("base64"),
                }
              : {}),
          },
          maxBuffer: 1024 * 1024,
        },
      );
      await removePreparedObjective(invocation.sessionId);
      return stdout.trim();
    } catch (error) {
      let detail = (error.stderr || error.message || String(error)).trim();
      if (preparedObjective) {
        try {
          await restoreObjective(preparedObjective);
          await removePreparedObjective(invocation.sessionId);
        } catch (restoreError) {
          const restoreDetail = (
            restoreError.stderr ||
            restoreError.message ||
            String(restoreError)
          ).trim();
          detail = `${detail}; native autopilot restore also failed: ${restoreDetail}`;
        }
      }
      return {
        textResultForLlm: `Self-compact was not armed: ${detail}`,
        resultType: "failure",
      };
    }
  },
};

session = await joinSession({ tools: [selfCompactTool] });
