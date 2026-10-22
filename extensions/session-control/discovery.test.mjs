import assert from "node:assert/strict";
import { access, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("extension discovery exposes only session-control as a loadable extension", async () => {
  const extensionsDirectory = dirname(
    dirname(fileURLToPath(import.meta.url)),
  );
  const entries = await readdir(extensionsDirectory, { withFileTypes: true });
  const extensionNames = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name);

  assert.equal(extensionNames.includes("session-control"), true);
  assert.equal(extensionNames.includes("session-inbox"), true);
  await assert.rejects(
    access(join(extensionsDirectory, "session-inbox", "extension.mjs")),
    (error) => error?.code === "ENOENT",
  );
});
