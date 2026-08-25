import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

// Every repo that consumes this packaging tree carries one of these at its
// root. Nothing here hardcodes a repo name: the name, visibility and per-host
// exclusions are inputs, which is the whole of the "fix once" requirement.
export const CONFIG_FILENAME = "packaging.config.json";

export async function loadConfig(root) {
  const raw = await readFile(resolve(root, CONFIG_FILENAME), "utf8");
  const config = JSON.parse(raw);

  const required = ["name", "visibility", "description", "emit"];
  for (const key of required) {
    if (config[key] === undefined) {
      throw new Error(`${CONFIG_FILENAME} is missing required key "${key}"`);
    }
  }
  if (config.visibility !== "public" && config.visibility !== "private") {
    throw new Error(
      `${CONFIG_FILENAME} visibility must be "public" or "private", got ${JSON.stringify(config.visibility)}`,
    );
  }
  return config;
}

// A skill directory is a direct child of skills/ that is not dot- or
// underscore-prefixed. Sorted, because manifest order is compared byte-for-byte
// by the version-only-diff check.
export async function listSkillDirectories(root) {
  const entries = await readdir(resolve(root, "skills"), { withFileTypes: true });
  return entries
    .filter(
      (entry) =>
        entry.isDirectory() &&
        !entry.name.startsWith(".") &&
        !entry.name.startsWith("_"),
    )
    .map((entry) => entry.name)
    .sort();
}

export function skillPaths(directories, exclusions = []) {
  const excluded = new Set(exclusions);
  return directories
    .filter((directory) => !excluded.has(directory))
    .map((directory) => `./skills/${directory}`);
}

// 2-space indent plus a trailing newline reproduces the hand-maintained files
// byte-for-byte. Anything else turns every emission into a whole-file diff and
// makes the version-only guarantee unobservable.
export function serialize(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

// The repo being operated on is not the repo this code lives in: a consumer
// runs it out of the packaging submodule. Resolving from import.meta.dirname
// silently targets the submodule instead, which is how the generator once
// emitted a private repo's manifests under the public config with the
// visibility assertion skipped. Every entry point resolves the root here.
export async function resolveRepoRoot() {
  if (process.env.PACKAGING_ROOT) return resolve(process.env.PACKAGING_ROOT);
  const flag = process.argv.find((arg) => arg.startsWith("--root="))?.split("=")[1];
  if (flag) return resolve(flag);
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  try {
    const { stdout } = await promisify(execFile)("git", ["rev-parse", "--show-toplevel"], {
      cwd: process.cwd(),
    });
    return stdout.trim();
  } catch {
    throw new Error(
      "cannot determine the repo to operate on: run from inside it, or pass --root=<path>",
    );
  }
}
