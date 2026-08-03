#!/usr/bin/env node

import { readdir, readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

async function readJson(path) {
  return JSON.parse(await readFile(resolve(root, path), "utf8"));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
};

function assertParsableFrontmatter(frontmatter, label) {
  const lines = frontmatter.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const match = /^([A-Za-z0-9_-]+):[ \t]+(.*)$/.exec(line);
    if (!match) continue;
    const value = match[2];
    if (/^["'>|]/.test(value)) continue;
    assert(
      !/:\s/.test(value),
      `${label} frontmatter key "${match[1]}" has an unquoted value containing ": ", which breaks YAML parsing and silently unloads the skill`,
    );
  }
}

function hasNonEmptyFrontmatterField(frontmatter, field) {
  const lines = frontmatter.split("\n");
  const index = lines.findIndex((line) => line.startsWith(`${field}:`));
  if (index === -1) return false;
  const value = lines[index].slice(field.length + 1).trim();
  if (/^[>|][+-]?$/.test(value)) {
    const block = [];
    for (const line of lines.slice(index + 1)) {
      if (!/^[ \t]/.test(line)) break;
      block.push(line.trim());
    }
    return block.join(" ").trim().length > 0;
  }
  return value !== "" && value !== "\"\"" && value !== "''";
}

const [claudePlugin, claudeMarketplace, codexPlugin, codexMarketplace] =
  await Promise.all([
    readJson(".claude-plugin/plugin.json"),
    readJson(".claude-plugin/marketplace.json"),
    readJson(".codex-plugin/plugin.json"),
    readJson(".agents/plugins/marketplace.json"),
  ]);

const expectedName = "dfrysinger-skills";
const expectedSkillsPath = "./skills/";

for (const [label, manifest] of [
  ["Claude plugin", claudePlugin],
  ["Codex plugin", codexPlugin],
]) {
  assert(manifest.name === expectedName, `${label} name must be ${expectedName}`);
  assert(
    manifest.version === claudePlugin.version,
    `${label} version must match the Claude plugin version`,
  );
  assert(
    manifest.description === claudePlugin.description,
    `${label} description must match the Claude plugin description`,
  );
}

assert(codexPlugin.skills === expectedSkillsPath, "Codex plugin must expose ./skills/");
assert(
  claudeMarketplace.name === expectedName,
  "Claude marketplace name must match the plugin name",
);
assert(
  claudeMarketplace.metadata?.version === claudePlugin.version,
  "Claude marketplace version must match the plugin version",
);
assert(
  claudeMarketplace.metadata?.description === claudePlugin.description,
  "Claude marketplace description must match the plugin description",
);

const claudeMarketplacePlugin = claudeMarketplace.plugins?.find(
  ({ name }) => name === expectedName,
);
assert(claudeMarketplacePlugin, "Claude marketplace must expose the plugin");
assert(
  claudeMarketplacePlugin.version === claudePlugin.version,
  "Claude marketplace plugin version must match the plugin version",
);
assert(
  claudeMarketplacePlugin.description === claudePlugin.description,
  "Claude marketplace plugin description must match the plugin description",
);
assert(
  claudeMarketplacePlugin.source === "./",
  "Claude marketplace plugin source must be ./",
);

assert(
  codexMarketplace.name === expectedName,
  "Codex marketplace name must match the plugin name",
);
const codexMarketplacePlugin = codexMarketplace.plugins?.find(
  ({ name }) => name === expectedName,
);
assert(codexMarketplacePlugin, "Codex marketplace must expose the plugin");
assert(
  codexMarketplacePlugin.source?.source === "local" &&
    codexMarketplacePlugin.source.path === "./",
  "Codex marketplace plugin source must be local ./",
);
assert(
  codexMarketplacePlugin.policy?.installation === "AVAILABLE" &&
    codexMarketplacePlugin.policy.authentication === "ON_INSTALL",
  "Codex marketplace plugin policy must be AVAILABLE/ON_INSTALL",
);
assert(
  codexMarketplacePlugin.category === "Productivity",
  "Codex marketplace plugin category must be Productivity",
);

const skillDirectories = (await readdir(resolve(root, "skills"), {
  withFileTypes: true,
}))
  .filter((entry) => entry.isDirectory() && !entry.name.startsWith("."))
  .map((entry) => entry.name)
  .sort();
const listedSkills = [...claudePlugin.skills].sort();
assert(
  JSON.stringify(listedSkills) ===
    JSON.stringify(skillDirectories.map((directory) => `./skills/${directory}`)),
  "Claude plugin skills must list every direct skills/ directory",
);
for (const directory of skillDirectories) {
  const skillContent = await readFile(
    resolve(root, "skills", directory, "SKILL.md"),
    "utf8",
  );
  assert(
    (await stat(resolve(root, "skills", directory, "SKILL.md"))).isFile(),
    `skills/${directory} must contain SKILL.md`,
  );
  const frontmatter = skillContent.match(/^---\n([\s\S]*?)\n---\n/);
  assert(frontmatter, `skills/${directory}/SKILL.md must start with frontmatter`);
  assert(
    new RegExp(`^name:\\s*${directory.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$`, "m")
      .test(frontmatter[1]),
    `skills/${directory}/SKILL.md name must match its directory`,
  );
  assert(
    hasNonEmptyFrontmatterField(frontmatter[1], "description"),
    `skills/${directory}/SKILL.md must have a non-empty description`,
  );
  assertParsableFrontmatter(frontmatter[1], `skills/${directory}/SKILL.md`);
}

console.log("Plugin manifests are consistent.");
