#!/usr/bin/env node

import { execFile } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { promisify } from "node:util";

import { loadConfig, listSkillDirectories, serialize } from "./config.mjs";
import {
  claudeMarketplace,
  claudePlugin,
  codexPlugin,
  copilotMarketplace,
  copilotPlugin,
} from "./templates.mjs";

const execFileAsync = promisify(execFile);

// The generator, not the validator, owns the visibility assertion. A validator
// runs after files exist; by then a private repo that is actually public has
// already had its manifests written. Refusing to emit is the only point where
// the assertion can still prevent the disclosure.
async function assertVisibility(config, { stubFailure = false } = {}) {
  if (config.visibility !== "private") {
    // A public-declared repo skips the assertion entirely. Blocking here would
    // block the public repo that this same tooling serves.
    return { asserted: false, reason: "declared public" };
  }
  if (stubFailure) {
    throw new Error(
      "visibility assertion stubbed to fail (PACKAGING_STUB_VISIBILITY_FAILURE): refusing to emit",
    );
  }
  const slug = config.repository?.replace(/^https:\/\/github\.com\//, "");
  if (!slug) {
    throw new Error(
      'config declares visibility "private" but has no "repository" to assert against',
    );
  }
  let stdout;
  try {
    ({ stdout } = await execFileAsync("gh", ["repo", "view", slug, "--json", "visibility"]));
  } catch (error) {
    throw new Error(
      `could not confirm ${slug} is private (gh repo view failed: ${error.message.split("\n")[0]}); refusing to emit`,
    );
  }
  const visibility = JSON.parse(stdout).visibility;
  if (visibility !== "PRIVATE") {
    throw new Error(
      `${slug} reports visibility ${visibility}, expected PRIVATE; refusing to emit`,
    );
  }
  return { asserted: true, reason: `${slug} is PRIVATE` };
}

function bumpPatch(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  if (!match) throw new Error(`version ${version} is not major.minor.patch`);
  return `${match[1]}.${match[2]}.${Number(match[3]) + 1}`;
}

// Every emission bumps the version, because the plugin cache is keyed by it:
// an unbumped version leaves stale code installed while every surface reports
// success. The current version is read from the Claude plugin manifest, which
// is the one the host actually resolves.
async function nextVersion(root, config, explicit) {
  if (explicit) return explicit;
  const current = JSON.parse(
    await readFile(resolve(root, config.emit.claudePlugin), "utf8"),
  ).version;
  return bumpPatch(current);
}

export async function generate(root, options = {}) {
  const config = await loadConfig(root);
  const visibility = await assertVisibility(config, options);
  const directories = await listSkillDirectories(root);
  const version = await nextVersion(root, config, options.version);

  const outputs = [
    [config.emit.claudePlugin, claudePlugin(config, version, directories)],
    [config.emit.copilotPlugin, copilotPlugin(config, version, directories)],
    [config.emit.codexPlugin, codexPlugin(config, version)],
    [config.emit.claudeMarketplace, claudeMarketplace(config, version)],
    [config.emit.copilotMarketplace, copilotMarketplace(config)],
  ];

  for (const [path, value] of outputs) {
    await writeFile(resolve(root, path), serialize(value), "utf8");
  }

  return { version, visibility, written: outputs.map(([path]) => path) };
}

// The repo being generated is NOT the repo this script lives in. When a
// consumer runs it out of the packaging submodule, resolving the root from
// this file's location loads the SUBMODULE's config and writes manifests into
// the submodule -- so a private repo would emit under the public config, with
// the visibility assertion silently skipped because that config declares
// public. Resolve the consuming repo explicitly instead.
async function resolveRoot() {
  if (process.env.PACKAGING_ROOT) return resolve(process.env.PACKAGING_ROOT);
  const flag = process.argv.find((arg) => arg.startsWith("--root="))?.split("=")[1];
  if (flag) return resolve(flag);
  try {
    const { stdout } = await execFileAsync("git", ["rev-parse", "--show-toplevel"], {
      cwd: process.cwd(),
    });
    return stdout.trim();
  } catch {
    throw new Error(
      "cannot determine the repo to generate: run from inside it, or pass --root=<path>",
    );
  }
}

const invokedDirectly = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (invokedDirectly) {
  const root = await resolveRoot();
  const explicit = process.argv.find((arg) => arg.startsWith("--version="))?.split("=")[1];
  // A refusal is an expected outcome of this tool, not a crash. Printing a
  // stack trace buries the one line that says why it refused, and the person
  // reading it is usually being told their repo is not private.
  let result;
  try {
    result = await generate(root, {
      version: explicit,
      stubFailure: process.env.PACKAGING_STUB_VISIBILITY_FAILURE === "1",
    });
  } catch (error) {
    console.error(`generate-manifests: ${error.message}`);
    console.error("generate-manifests: nothing was written.");
    process.exit(1);
  }
  console.log(
    `Emitted version ${result.version} (visibility: ${result.visibility.reason}):\n  ${result.written.join("\n  ")}`,
  );
}
