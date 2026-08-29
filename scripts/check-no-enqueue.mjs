#!/usr/bin/env node

import { readdir, readFile } from "node:fs/promises";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const scanRoots = ["extensions", "skills", "scripts"];
const runtimeExtensions = new Set([".js", ".mjs", ".sh", ".ts"]);
const forbidden = [
  {
    pattern: /\bcommands\s*(?:\?\.|\.)\s*enqueue\s*\(/,
    message: "commands.enqueue() submits slash commands to the FIFO",
  },
  {
    pattern: /["'`]enqueue["'`]/,
    message: "the enqueue delivery mode is forbidden in runtime code",
  },
  {
    pattern: /--mode(?:=|\s+)enqueue\b/,
    message: "--mode enqueue submits messages to the FIFO",
  },
];

async function* walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      yield* walk(path);
    } else {
      yield path;
    }
  }
}

function scanContent(content, label) {
  const violations = [];
  for (const { pattern, message } of forbidden) {
    const match = pattern.exec(content);
    if (!match) continue;
    const line = content.slice(0, match.index).split("\n").length;
    violations.push(`${label}:${line}: ${message}`);
  }
  const sendPattern = /\bsession\s*\.\s*send\s*\(\s*\{([\s\S]*?)\}\s*\)/g;
  for (const match of content.matchAll(sendPattern)) {
    if (/\bmode\s*:\s*["'`]immediate["'`]/.test(match[1])) continue;
    const line = content.slice(0, match.index).split("\n").length;
    violations.push(
      `${label}:${line}: session.send() must declare literal immediate delivery`,
    );
  }
  return violations;
}

if (process.argv.includes("--self-test")) {
  const violations = [
    "await session.rpc.commands.enqueue({command});",
    'await session.send({prompt, mode: "enqueue"});',
    "await session.send({prompt, mode});",
    "await session.send({prompt});",
    "request.mjs send --mode enqueue",
  ];
  for (const [index, fixture] of violations.entries()) {
    if (scanContent(fixture, `violation-${index}`).length === 0) {
      throw new Error(`INV-001 self-test did not reject fixture ${index}`);
    }
  }
  const legitimate = `
    await session.rpc.queue.pendingItems();
    await session.send({prompt, mode: "immediate"});
    await session.rpc.commands.invoke({name: "autopilot", input: prompt});
    if (event.data.delivery === "queued") throw new Error("reject queued delivery");
  `;
  if (scanContent(legitimate, "legitimate").length !== 0) {
    throw new Error("INV-001 self-test rejected queue observation");
  }
  console.log("INV-001 no-enqueue guard self-test passed.");
  process.exit(0);
}

const violations = [];
for (const scanRoot of scanRoots) {
  for await (const path of walk(join(root, scanRoot))) {
    const repoPath = relative(root, path);
    if (
      path === fileURLToPath(import.meta.url) ||
      !runtimeExtensions.has(extname(path)) ||
      /\.test\.(?:js|mjs|sh|ts)$/.test(path)
    ) {
      continue;
    }
    const content = await readFile(path, "utf8");
    violations.push(...scanContent(content, repoPath));
  }
}

if (violations.length) {
  console.error("INV-001: queued Copilot delivery is forbidden:\n");
  for (const violation of violations) console.error(`- ${violation}`);
  process.exit(1);
}

console.log("INV-001 passed: no runtime skill or extension uses queued Copilot delivery.");
