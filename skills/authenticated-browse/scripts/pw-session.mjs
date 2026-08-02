#!/usr/bin/env node
// pw-session.mjs - Playwright-backed persistent-context browser helper.
//
// In every subcommand below, <profile> is OPTIONAL. If omitted (or if the first
// positional arg starts with http(s)://), the profile name "default" is used.
//
// Subcommands:
//   auth [profile] <url>                              Headed login. Persists cookies/storage under ~/.cache/copilot-skills/authenticated-browse/profiles/<profile>.
//   fetch [profile] <url> [text|html|links|title]     Headless visit; prints rendered output to stdout.
//   screenshot [profile] <url> [out.png]              Headless full-page screenshot; prints output path.
//   eval [profile] <url> <jsExpr>                     Headless eval of a single JS expression in page context; prints JSON.stringify(result).
//   list-profiles                                     Print known profile names, one per line.
//   purge [profile]                                   Delete a profile's persistent data (default: "default").

import { chromium } from 'playwright';
import { existsSync, mkdirSync, readdirSync, rmSync, openSync, closeSync, unlinkSync, writeFileSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const BASE_DIR = process.env.COPILOT_AUTH_BROWSE_DIR
  || join(homedir(), '.cache', 'copilot-skills', 'authenticated-browse');
const PROFILES_DIR = join(BASE_DIR, 'profiles');
const SHOTS_DIR = join(BASE_DIR, 'shots');

function profileDirFor(name) {
  if (!name || !/^[A-Za-z0-9._-]+$/.test(name)) {
    fail(`Invalid profile name "${name}". Use letters, digits, dot, dash, underscore.`);
  }
  return join(PROFILES_DIR, name);
}

function fail(msg, code = 2) {
  console.error(`[authenticated-browse] ${msg}`);
  process.exit(code);
}

function acquireProfileLock(profile) {
  const dir = profileDirFor(profile);
  mkdirSync(dir, { recursive: true });
  const lockPath = join(dir, '.copilot-skill.lock');
  if (existsSync(lockPath)) {
    let owner = '';
    try { owner = readFileSync(lockPath, 'utf8').trim(); } catch { /* ignore */ }
    const [pidStr] = owner.split(/\s+/, 1);
    const pid = Number.parseInt(pidStr, 10);
    let alive = false;
    if (Number.isFinite(pid) && pid > 0) {
      try { process.kill(pid, 0); alive = true; } catch { alive = false; }
    }
    if (alive) {
      fail(`Profile "${profile}" is already in use by another command (pid ${pid}). ` +
           `Close the running auth/browse command, or pick a different profile.`, 75);
    }
    try { unlinkSync(lockPath); } catch { /* ignore */ }
  }
  try {
    writeFileSync(lockPath, `${process.pid} ${new Date().toISOString()}\n`, { flag: 'wx' });
  } catch (e) {
    fail(`Could not acquire profile lock for "${profile}": ${e.message}`, 75);
  }
  const release = () => { try { unlinkSync(lockPath); } catch { /* ignore */ } };
  process.on('exit', release);
  process.on('SIGINT', () => { release(); process.exit(130); });
  process.on('SIGTERM', () => { release(); process.exit(143); });
  return release;
}

async function openContext(profile, { headless }) {
  const dir = profileDirFor(profile);
  mkdirSync(dir, { recursive: true });
  return chromium.launchPersistentContext(dir, {
    headless,
    viewport: headless ? { width: 1440, height: 900 } : null,
    args: headless ? [] : ['--start-maximized'],
    ignoreHTTPSErrors: false,
  });
}

async function cmdAuth(profile, url) {
  if (!url) fail('Usage: pw-session.mjs auth <profile> <url>');
  acquireProfileLock(profile);
  const ctx = await openContext(profile, { headless: false });

  // Track the most recently active page URL live, so we can report it after close.
  let lastUrl = url;
  const bindPage = (p) => {
    const update = () => { try { lastUrl = p.url(); } catch { /* ignore */ } };
    p.on('framenavigated', (frame) => { if (frame === p.mainFrame()) update(); });
    p.on('domcontentloaded', update);
    p.on('load', update);
    update();
  };
  ctx.on('page', bindPage);
  for (const p of ctx.pages()) bindPage(p);

  const page = ctx.pages()[0] || await ctx.newPage();
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 120_000 });
  } catch (e) {
    console.error(`[authenticated-browse] Initial navigation warning: ${e.message}. Browser still open; you can navigate manually.`);
  }
  console.error('');
  console.error('[authenticated-browse] ============================================================');
  console.error(`[authenticated-browse] Browser open with profile: ${profile}`);
  console.error(`[authenticated-browse] Profile dir: ${profileDirFor(profile)}`);
  console.error('[authenticated-browse] Complete any login / MFA / SSO in the visible window.');
  console.error('[authenticated-browse] You may navigate to additional pages you want the agent');
  console.error('[authenticated-browse] to be able to see - cookies and storage will be saved.');
  console.error('[authenticated-browse] When you are done, CLOSE the browser window to finish.');
  console.error('[authenticated-browse] ============================================================');
  console.error('');

  // Resolve when the persistent context closes (user closes window) OR when the
  // browser process disconnects. Belt-and-suspenders so we never hang.
  await new Promise((resolve) => {
    ctx.once('close', resolve);
    const browser = ctx.browser();
    if (browser) browser.once('disconnected', resolve);
  });

  console.error(`[authenticated-browse] Session saved. Last seen URL: ${lastUrl}`);
  process.stdout.write(JSON.stringify({ profile, profile_dir: profileDirFor(profile), last_url: lastUrl }) + '\n');
}

async function cmdFetch(profile, url, mode = 'text') {
  if (!url) fail('Usage: pw-session.mjs fetch <profile> <url> [text|html|links|title]');
  acquireProfileLock(profile);
  const ctx = await openContext(profile, { headless: true });
  const page = ctx.pages()[0] || await ctx.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 });
  } catch (e) {
    console.error(`[authenticated-browse] networkidle wait timed out: ${e.message}. Continuing with current DOM.`);
  }
  let out;
  if (mode === 'html') {
    out = await page.content();
  } else if (mode === 'title') {
    out = await page.title();
  } else if (mode === 'links') {
    const links = await page.$$eval('a[href]', as =>
      as.map(a => ({ text: (a.innerText || '').trim().slice(0, 200), href: a.href }))
    );
    out = JSON.stringify(links, null, 2);
  } else if (mode === 'text') {
    out = await page.evaluate(() => document.body ? document.body.innerText : '');
  } else {
    await ctx.close();
    fail(`Unknown mode "${mode}". Use text | html | links | title.`);
  }
  process.stdout.write(out);
  if (!out.endsWith('\n')) process.stdout.write('\n');
  await ctx.close();
}

async function cmdScreenshot(profile, url, outPath) {
  if (!url) fail('Usage: pw-session.mjs screenshot <profile> <url> [out.png]');
  acquireProfileLock(profile);
  mkdirSync(SHOTS_DIR, { recursive: true });
  const target = outPath || join(SHOTS_DIR, `${profile}-${Date.now()}.png`);
  const ctx = await openContext(profile, { headless: true });
  const page = ctx.pages()[0] || await ctx.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 });
  } catch (e) {
    console.error(`[authenticated-browse] networkidle wait timed out: ${e.message}. Screenshotting current DOM.`);
  }
  await page.screenshot({ path: target, fullPage: true });
  await ctx.close();
  console.log(target);
}

async function cmdEval(profile, url, expr) {
  if (!url || !expr) fail('Usage: pw-session.mjs eval <profile> <url> <jsExpr>');
  acquireProfileLock(profile);
  const ctx = await openContext(profile, { headless: true });
  const page = ctx.pages()[0] || await ctx.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 });
  } catch (e) {
    console.error(`[authenticated-browse] networkidle wait timed out: ${e.message}. Continuing.`);
  }
  const result = await page.evaluate(`(() => { return (${expr}); })()`);
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  await ctx.close();
}

function cmdListProfiles() {
  if (!existsSync(PROFILES_DIR)) return;
  for (const name of readdirSync(PROFILES_DIR)) console.log(name);
}

function cmdPurge(profile) {
  if (!profile) fail('Usage: pw-session.mjs purge <profile>');
  const dir = profileDirFor(profile);
  if (!existsSync(dir)) fail(`Profile "${profile}" not found.`, 1);
  rmSync(dir, { recursive: true, force: true });
  console.error(`[authenticated-browse] Purged ${dir}`);
}

const DEFAULT_PROFILE = 'default';
const URL_RE = /^https?:\/\//i;

// Resolve [profile?, url] from positional args. If the first arg looks like a
// URL, treat profile as omitted and use the default profile.
function resolveProfileUrl(args) {
  if (args.length === 0) return { profile: DEFAULT_PROFILE, url: undefined, rest: [] };
  if (URL_RE.test(args[0])) {
    return { profile: DEFAULT_PROFILE, url: args[0], rest: args.slice(1) };
  }
  return { profile: args[0], url: args[1], rest: args.slice(2) };
}

async function main() {
  const [, , cmd, ...rest] = process.argv;
  switch (cmd) {
    case 'auth': {
      const { profile, url } = resolveProfileUrl(rest);
      return cmdAuth(profile, url);
    }
    case 'fetch': {
      const { profile, url, rest: tail } = resolveProfileUrl(rest);
      return cmdFetch(profile, url, tail[0]);
    }
    case 'screenshot': {
      const { profile, url, rest: tail } = resolveProfileUrl(rest);
      return cmdScreenshot(profile, url, tail[0]);
    }
    case 'eval': {
      const { profile, url, rest: tail } = resolveProfileUrl(rest);
      return cmdEval(profile, url, tail[0]);
    }
    case 'list-profiles': return cmdListProfiles();
    case 'purge':         return cmdPurge(rest[0] || DEFAULT_PROFILE);
    default:
      fail('Commands: auth | fetch | screenshot | eval | list-profiles | purge');
  }
}

main().catch((e) => fail(e.stack || String(e), 1));
