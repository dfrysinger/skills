import { skillPaths } from "./config.mjs";

// One function per manifest. Key order here is the key order on disk: these are
// compared byte-for-byte after regeneration, so reordering a key is a real
// change even though the parsed object is identical.

export function claudePlugin(config, version, directories) {
  return {
    name: config.name,
    version,
    description: config.description,
    author: config.author,
    skills: skillPaths(directories, config.hostExclusions?.claude),
  };
}

export function copilotPlugin(config, version, directories) {
  return {
    name: config.name,
    version,
    description: config.description,
    author: config.author,
    skills: skillPaths(directories, config.hostExclusions?.copilot),
  };
}

// Codex takes a directory rather than an allowlist, so it cannot express a
// per-host exclusion. A skill excluded only for Codex would still load; the
// generator refuses rather than emitting a manifest that quietly ignores it.
export function codexPlugin(config, version) {
  if (config.hostExclusions?.codex?.length) {
    throw new Error(
      'Codex manifest uses "skills": "./skills/" (a directory) and cannot express ' +
        `exclusions, but hostExclusions.codex lists: ${config.hostExclusions.codex.join(", ")}`,
    );
  }
  return {
    name: config.name,
    version,
    description: config.description,
    author: {
      ...config.author,
      ...(config.repository ? { url: config.repository.replace(/\/[^/]+$/, "") } : {}),
    },
    ...(config.repository ? { homepage: config.repository } : {}),
    ...(config.repository ? { repository: config.repository } : {}),
    ...(config.license ? { license: config.license } : {}),
    skills: "./skills/",
  };
}

export function claudeMarketplace(config, version) {
  return {
    name: config.name,
    metadata: {
      description: config.description,
      version,
    },
    owner: config.author,
    plugins: [
      {
        name: config.name,
        description: config.description,
        version,
        source: "./",
      },
    ],
  };
}

// Copilot's marketplace carries no version or description field; it is
// deliberately absent rather than omitted by accident, so the version-only
// diff check never sees this file change at all.
export function copilotMarketplace(config) {
  return {
    name: config.name,
    interface: {
      displayName: config.displayName ?? config.name,
    },
    plugins: [
      {
        name: config.name,
        source: {
          source: "local",
          path: "./",
        },
        policy: {
          installation: "AVAILABLE",
          authentication: "ON_INSTALL",
        },
        category: "Productivity",
      },
    ],
  };
}
