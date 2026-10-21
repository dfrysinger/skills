#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

function usage(message) {
	if (message) console.error(message);
	console.error(
		"usage: validate-mermaid.mjs --repo /path/to/repo --file /path/to/doc.md|-",
	);
	process.exit(64);
}

function parseArgs(argv) {
	let repo;
	let file;
	for (let index = 0; index < argv.length; index += 1) {
		const argument = argv[index];
		if (argument === "--repo") {
			repo = argv[++index];
		} else if (argument === "--file") {
			file = argv[++index];
		} else {
			usage(`unknown argument: ${argument}`);
		}
	}
	if (!repo || !file) usage("both --repo and --file are required");
	return { repo: path.resolve(repo), file };
}

function loadMarkdown(file) {
	if (file === "-") return fs.readFileSync(0, "utf8");
	return fs.readFileSync(path.resolve(file), "utf8");
}

function resolveFromRepo(requireFromRepo, packageName) {
	try {
		return requireFromRepo.resolve(packageName);
	} catch {
		throw new Error(
			`repository dependency "${packageName}" is unavailable; use an existing repository Mermaid renderer or parser`,
		);
	}
}

function leadingSpaces(line) {
	return line.match(/^ */)[0].length;
}

function listItemContent(line) {
	const match = line.match(/^( {0,3})((?:[-+*])|(?:\d{1,9}[.)]))( +)(.*)$/);
	if (match == null) return null;
	return {
		indent: match[1].length + match[2].length + match[3].length,
		content: match[4],
	};
}

function extractMermaidDiagrams(markdown) {
	const diagrams = [];
	const lines = markdown.split(/\r?\n/);
	const listIndents = [];
	let fence = null;

	for (const [index, line] of lines.entries()) {
		if (fence == null) {
			if (/^ {0,3}(?:> ?)+ {0,3}(?:`{3,}|~{3,})mermaid(?:\s|$)/i.test(line)) {
				throw new Error(
					`blockquoted Mermaid fence on line ${index + 1}: use the repository renderer or move the diagram outside the quote`,
				);
			}
			const indent = leadingSpaces(line);
			if (line.trim() !== "") {
				while (
					listIndents.length > 0 &&
					indent < listIndents[listIndents.length - 1]
				) {
					listIndents.pop();
				}
			}

			const containerIndent = listIndents[listIndents.length - 1] ?? 0;
			let content =
				indent >= containerIndent ? line.slice(containerIndent) : line;
			const listItem = listItemContent(content);
			let fenceIndent = containerIndent;
			if (listItem != null) {
				fenceIndent += listItem.indent;
				listIndents.push(fenceIndent);
				content = listItem.content;
			}

			const opening = content.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
			if (opening == null) continue;
			const marker = opening[1][0];
			const info = opening[2].trim();
			fence = {
				containerIndent: fenceIndent,
				marker,
				length: opening[1].length,
				mermaid: /^mermaid(?:\s|$)/i.test(info),
				openingLine: index + 1,
				lines: [],
			};
			continue;
		}

		const content =
			leadingSpaces(line) >= fence.containerIndent
				? line.slice(fence.containerIndent)
				: line;
		const closing = new RegExp(
			`^\\s{0,3}${fence.marker}{${fence.length},}\\s*$`,
		);
		if (closing.test(content)) {
			if (fence.mermaid) diagrams.push(fence.lines.join("\n"));
			fence = null;
			continue;
		}

		if (fence.mermaid) fence.lines.push(content);
	}

	if (fence?.mermaid) {
		throw new Error(
			`unterminated Mermaid fence opened on line ${fence.openingLine}`,
		);
	}
	return diagrams;
}

const { repo, file } = parseArgs(process.argv.slice(2));
const packageJson = path.join(repo, "package.json");
if (!fs.existsSync(packageJson)) {
	throw new Error(`repository package.json not found: ${packageJson}`);
}

const markdown = loadMarkdown(file);
const diagrams = extractMermaidDiagrams(markdown);
if (diagrams.length === 0) {
	throw new Error("no Mermaid code fences found");
}

const requireFromRepo = createRequire(packageJson);
const jsdomEntry = resolveFromRepo(requireFromRepo, "jsdom");
const mermaidEntry = resolveFromRepo(requireFromRepo, "mermaid");
const { JSDOM } = await import(pathToFileURL(jsdomEntry).href);

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
	pretendToBeVisual: true,
});
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
globalThis.CSSStyleSheet = window.CSSStyleSheet;

window.SVGElement.prototype.getBBox = function getBBox() {
	const text = this.textContent ?? "";
	return {
		x: 0,
		y: 0,
		width: Math.max(20, text.length * 7),
		height: 20,
	};
};
window.SVGElement.prototype.getComputedTextLength =
	function getComputedTextLength() {
		return (this.textContent ?? "").length * 7;
	};

const { default: mermaid } = await import(pathToFileURL(mermaidEntry).href);
mermaid.initialize({
	startOnLoad: false,
	securityLevel: "strict",
	flowchart: { htmlLabels: false },
});

let failures = 0;
for (const [index, diagram] of diagrams.entries()) {
	try {
		await mermaid.parse(diagram);
		const { svg } = await mermaid.render(
			`arch-map-${index + 1}`,
			diagram,
		);
		if (!svg.includes("<svg")) throw new Error("renderer returned no SVG");
		console.log(`diagram ${index + 1}: rendered ${svg.length} bytes`);
	} catch (error) {
		failures += 1;
		const message = error instanceof Error ? error.message : String(error);
		console.error(`diagram ${index + 1}: ${message}`);
	}
}

console.log(`diagrams=${diagrams.length} failed=${failures}`);
if (failures > 0) process.exit(1);
