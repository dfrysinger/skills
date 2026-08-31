import { execFile } from "node:child_process";
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
    "Arm one native steered compaction after this assistant turn ends. Use only as the final action required by the self-compact skill. The brief remains in this private tool call instead of visible chat prose.",
  parameters: {
    type: "object",
    properties: {
      brief: {
        type: "string",
        description:
          "The complete Keep/Drop/After compaction brief. It must start with Keep:, include Drop:, and end with an After compaction: instruction containing the exact words 'do not compact again'.",
      },
    },
    required: ["brief"],
    additionalProperties: false,
  },
  defer: "never",
  handler: async ({ brief }, invocation) => {
    if (!validBrief(brief)) {
      return {
        textResultForLlm:
          "Self-compact was not armed: brief must be at most 16 KiB and contain nonempty Keep:, Drop:, and After compaction: sections; After compaction must include 'do not compact again'.",
        resultType: "failure",
      };
    }
    try {
      const { stdout } = await execFileAsync(
        nodeBin,
        [submitter, "--tool-call-id", invocation.toolCallId],
        {
          env: {
            ...process.env,
            COPILOT_AGENT_SESSION_ID: invocation.sessionId,
          },
          maxBuffer: 1024 * 1024,
        },
      );
      return stdout.trim();
    } catch (error) {
      const detail = (error.stderr || error.message || String(error)).trim();
      return {
        textResultForLlm: `Self-compact was not armed: ${detail}`,
        resultType: "failure",
      };
    }
  },
};

await joinSession({ tools: [selfCompactTool] });
