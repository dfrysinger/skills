import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const script = fileURLToPath(new URL("./validate-mermaid.mjs", import.meta.url));
const repo = process.env.MERMAID_TEST_REPO;
if (!repo) throw new Error("Set MERMAID_TEST_REPO to a repository with mermaid and jsdom.");

function run(markdown, { file = false, repoPath = repo } = {}) {
	const dir = mkdtempSync(join(tmpdir(), "arch-map-test-"));
	try {
		const input = join(dir, "diagram.md");
		if (file) writeFileSync(input, markdown);
		const result = spawnSync(process.execPath, [
			script, "--repo", repoPath, "--file", file ? input : "-",
		], { input: file ? undefined : markdown, encoding: "utf8", timeout: 90_000 });
		assert.ifError(result.error);
		return { status: result.status, output: result.stdout + result.stderr };
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
}

test("renders flowcharts and sequences from a file, lists, and both fence styles", () => {
	const result = run([
		"```mermaid", "flowchart LR", ' A["src/main.ts<br/>run"] --> B', "```",
		"1. Sequence", "",
		"   ~~~mermaid", "   sequenceDiagram", "   A->>B: request",
		"   B-->>A: response", "   ~~~",
	].join("\n"), { file: true });
	assert.equal(result.status, 0, result.output);
	assert.match(result.output, /diagrams=2 failed=0/);
});

test("ignores Mermaid-looking examples inside a non-Mermaid fence", () => {
	const result = run("````text\n```mermaid\nnot a diagram\n```\n````\n~~~mermaid\nflowchart LR\n A --> B\n~~~");
	assert.equal(result.status, 0, result.output);
	assert.match(result.output, /diagrams=1 failed=0/);
});

test("reports invalid diagrams without skipping later valid diagrams", () => {
	const result = run("```mermaid\nnot a diagram\n```\n```mermaid\nflowchart LR\n A --> B\n```");
	assert.equal(result.status, 1, result.output);
	assert.match(result.output, /diagrams=2 failed=1/);
});

for (const [name, markdown, expected] of [
	["empty document", "# No diagrams", /no Mermaid code fences found/],
	["unclosed fence", "```mermaid\nflowchart LR\n A --> B", /unterminated Mermaid fence/],
	["blockquote", "```mermaid\nflowchart LR\n A --> B\n```\n> ```mermaid\n> bad\n> ```", /blockquoted Mermaid fence/],
]) {
	test(`rejects ${name}`, () => {
		const result = run(markdown);
		assert.notEqual(result.status, 0);
		assert.match(result.output, expected);
	});
}

test("reports missing repository dependencies", () => {
	const dir = mkdtempSync(join(tmpdir(), "arch-map-deps-"));
	try {
		writeFileSync(join(dir, "package.json"), '{"private":true}');
		const result = run("```mermaid\nflowchart LR\n A --> B\n```", { repoPath: dir });
		assert.notEqual(result.status, 0);
		assert.match(result.output, /repository dependency ".*" is unavailable/);
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
});
