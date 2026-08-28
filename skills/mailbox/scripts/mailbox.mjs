#!/usr/bin/env node

import {
  createMailbox,
  parseMailboxAddress,
  POKE_NO_ACTIVE_COPILOT,
  POKE_UNVERIFIED,
  resolveOwnName,
} from "./mailbox-core.mjs";

function usage(message) {
  if (message) console.error(`mailbox: ${message}`);
  console.error(
    "usage: mailbox.mjs <send|check|read|ack|list|resume-hint|poke|watch> [options]",
  );
  process.exit(2);
}

function parseOptions(args, booleanFlags = new Set()) {
  const positional = [];
  const options = {};
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index];
    if (!value.startsWith("--")) {
      positional.push(value);
      continue;
    }
    const name = value.slice(2);
    if (booleanFlags.has(name)) {
      options[name] = true;
      continue;
    }
    const optionValue = args[index + 1];
    if (optionValue === undefined) usage(`missing value for --${name}`);
    if (name === "file") {
      options.file ??= [];
      options.file.push(optionValue);
    } else {
      options[name] = optionValue;
    }
    index += 1;
  }
  return { positional, options };
}

async function requiredOwnName(explicitName) {
  const name = await resolveOwnName(explicitName);
  if (!name) {
    throw new Error(
      "agent name is required; pass --name, set COPILOT_AGENT_NAME, or run inside tmux",
    );
  }
  return name;
}

function printEnvelope(envelope, attachmentDirectory) {
  console.log(`FROM: ${envelope.from.name}`);
  console.log(`TO:   ${envelope.to.name}`);
  console.log(`SENT: ${envelope.sent_at}`);
  console.log(`ID:   ${envelope.id}`);
  console.log(`SUMMARY: ${envelope.summary}`);
  console.log();
  console.log(envelope.message);
  if (envelope.attachments.length > 0) {
    console.log();
    console.log("ATTACHMENTS:");
    for (const attachment of envelope.attachments) {
      console.log(`  ${attachmentDirectory}/${attachment}`);
    }
  }
}

const [command, ...args] = process.argv.slice(2);
if (!command) usage();
const mailbox = createMailbox();

try {
  switch (command) {
    case "send": {
      const { positional, options } = parseOptions(
        args,
        new Set(["no-wakeup", "wait"]),
      );
      if (positional.length !== 1) usage("send requires one recipient");
      const sender = (await resolveOwnName(options.from)) ?? "unknown";
      const result = await mailbox.send({
        recipient: positional[0],
        sender,
        summary: options.summary,
        message: options.message,
        files: options.file ?? [],
        wake: !options["no-wakeup"],
        wait: Boolean(options.wait),
      });
      console.log(`envelope: ${result.envelopePath}`);
      if (options["no-wakeup"]) break;
      switch (result.wakeup.status) {
        case "delivered":
          console.log("wakeup: recipient accepted the mailbox nudge (verified)");
          break;
        case "no-active-copilot":
          console.log(
            `wakeup: skipped (no active Copilot session named '${parseMailboxAddress(positional[0]).name}'; envelope waits in pending/)`,
          );
          break;
        case "remote-pending":
          console.log(`wakeup: ${result.wakeup.detail}`);
          break;
        case "unverified":
          console.log(
            "wakeup: recipient did not acknowledge the nudge (NOT verified); envelope waits in pending/",
          );
          break;
        default:
          console.log(`wakeup: ${result.wakeup.status}`);
      }
      break;
    }
    case "check": {
      const { positional, options } = parseOptions(args);
      if (positional.length !== 0) usage("check takes no positional arguments");
      const name = await requiredOwnName(options.name);
      const envelopes = await mailbox.checkLocal(name);
      if (envelopes.length === 0) {
        console.log(`no pending mail for ${mailbox.localAddresses(name).join(" or ")}`);
        break;
      }
      console.log(
        `${mailbox.localAddresses(name).join(" + ")} have ${envelopes.length} pending envelope(s):`,
      );
      for (const { envelope, path, mailboxAddress } of envelopes) {
        console.log(
          `  [${envelope.id}]  mailbox=${mailboxAddress}  from=${envelope.from.name}  sent=${envelope.sent_at}`,
        );
        console.log(`     summary: ${envelope.summary}`);
        if (envelope.attachments.length > 0) {
          console.log(`     attachments (${envelope.attachments.length}):`);
          for (const attachment of envelope.attachments) {
            console.log(`       ${path.slice(0, -5)}/${attachment}`);
          }
        }
      }
      console.log();
      console.log("Read one with: mailbox-read.sh <id>    Ack with: mailbox-ack.sh <id>");
      break;
    }
    case "read": {
      const { positional, options } = parseOptions(args);
      if (positional.length !== 1) usage("read requires one envelope id");
      const name = await requiredOwnName(options.name);
      const result = await mailbox.readLocal(name, positional[0]);
      printEnvelope(result.envelope, result.attachmentDirectory);
      break;
    }
    case "ack": {
      const { positional, options } = parseOptions(args);
      if (positional.length !== 1) usage("ack requires one envelope id");
      const name = await requiredOwnName(options.name);
      await mailbox.acknowledgeLocal(name, positional[0]);
      console.log(`acked: ${positional[0]} -> delivered/`);
      break;
    }
    case "list": {
      const { positional } = parseOptions(args);
      if (positional.length !== 0) usage("list takes no arguments");
      console.log(`=== mailboxes (${mailbox.mailboxRoot}) ===`);
      const mailboxes = await mailbox.list();
      if (mailboxes.length === 0) {
        console.log("  (none)");
      } else {
        for (const entry of mailboxes) {
          console.log(
            `  ${entry.name.padEnd(20)}  pending=${entry.pending}  delivered=${entry.delivered}`,
          );
        }
      }
      break;
    }
    case "resume-hint": {
      const { positional, options } = parseOptions(args);
      if (positional.length > 1) usage("resume-hint accepts at most one agent name");
      const name = await requiredOwnName(positional[0] ?? options.name);
      const hint = await mailbox.resumeHint(name);
      if (hint) console.log(hint);
      break;
    }
    case "poke": {
      const { positional, options } = parseOptions(args, new Set(["wait"]));
      if (positional.length !== 1) usage("poke requires one agent name");
      const address = parseMailboxAddress(positional[0]);
      if (address.machine && address.machine !== mailbox.machineName) {
        console.log(`poke: deferred to mailbox watcher on ${address.machine}`);
        break;
      }
      const result = await mailbox.poke(positional[0], {
        targetName: address.name,
        wait: Boolean(options.wait),
      });
      if (result.status === "delivered") {
        console.log(`poked: ${positional[0]} (SDK native delivery verified)`);
      } else if (result.status === "no-active-copilot") {
        console.error(
          `UNAVAILABLE: no active Copilot session named '${positional[0]}'; the mail remains queued.`,
        );
        process.exitCode = POKE_NO_ACTIVE_COPILOT;
      } else if (result.status === "unverified") {
        console.error(
          `UNVERIFIED: '${positional[0]}' did not acknowledge the SDK wakeup; the mail remains queued.`,
        );
        process.exitCode = POKE_UNVERIFIED;
      }
      break;
    }
    case "watch": {
      const { positional, options } = parseOptions(args, new Set(["once"]));
      if (positional.length > 1) usage("watch accepts at most one agent name");
      const address = positional[0] ?? (await requiredOwnName(options.name));
      const parsedAddress = parseMailboxAddress(address);
      if (
        parsedAddress.machine &&
        parsedAddress.machine !== mailbox.machineName
      ) {
        throw new Error(
          `mailbox ${parsedAddress.address} belongs to machine ${parsedAddress.machine}`,
        );
      }
      const targetName = parsedAddress.name;
      const intervalMs = Number(options.interval ?? "2000");
      const controller = new AbortController();
      for (const signal of ["SIGINT", "SIGTERM"]) {
        process.on(signal, () => controller.abort());
      }
      console.log(
        `watching ${mailbox.mailboxRoot}/${address}/pending for local session ${targetName} every ${intervalMs} ms`,
      );
      await mailbox.watch(address, {
        targetName,
        intervalMs,
        once: Boolean(options.once),
        signal: controller.signal,
      });
      break;
    }
    default:
      usage(`unknown command: ${command}`);
  }
} catch (error) {
  console.error(`mailbox: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}
