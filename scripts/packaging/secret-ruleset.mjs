// Two tiers, selected by the repo's declared visibility.
//
// Tier 1 is live authentication material: possession is compromise, so it is
// rejected everywhere, private repos included.
//
// Tier 2 is locators — they identify a host already behind Tailscale auth or a
// LAN boundary. Publishing them is the leak; storing them in a private repo is
// the payload. A single always-reject table would block the private repo's own
// migration commit, because the skills being migrated document a container
// network by design.
//
// Approved fixture syntax lets documentation show a payload shape without
// tripping the gate. It is deliberately implausible as a real value.
export const FIXTURE_MARKER = "<redacted>";
export const FIXTURE_PATTERNS = [
  /<redacted>/,
  /\bxxxxxxxx\b/i,
  /\b(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}\b/, // RFC 5737 documentation ranges
  /\bexample\.ts\.net\b/,
];

export const TIER_1 = [
  {
    id: "printer-access-code",
    label: "printer LAN access code",
    // 8 alphanumerics in proximity to an access_code key. Short and
    // low-entropy, which is exactly the case a generic entropy scanner misses.
    pattern: /access[_-]?code["'\s:=]+([A-Za-z0-9]{8})\b/i,
  },
  {
    id: "ams-rfid-identifier",
    label: "AMS / RFID identifier",
    pattern: /\b(?:tag_uid|tray_uuid|chip_id)["'\s:=]+([0-9A-Fa-f]{16,32})\b/i,
  },
  {
    id: "generic-credential",
    label: "generic credential",
    pattern:
      /\b(?:bearer\s+[A-Za-z0-9._-]{16,}|(?:api[_-]?key|password|passwd|secret|token)["'\s:=]+[^\s"'{}<>]{12,})/i,
  },
  {
    id: "private-key",
    label: "private key block",
    pattern: /-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----/,
  },
];

export const TIER_2 = [
  {
    id: "device-serial",
    label: "device serial",
    pattern: /\b(?:serial(?:_number)?|dev_id)["'\s:=]+([0-9A-Z]{12,20})\b/i,
  },
  {
    id: "network-identity",
    label: "network identity (LAN address / Tailscale host / internal URL)",
    pattern:
      /\b(?:(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|[A-Za-z0-9-]+\.ts\.net)\b/,
  },
];

export function rulesFor(visibility) {
  if (visibility === "private") return TIER_1;
  if (visibility === "public") return [...TIER_1, ...TIER_2];
  throw new Error(`unknown visibility ${JSON.stringify(visibility)}`);
}

function isFixture(line) {
  return FIXTURE_PATTERNS.some((pattern) => pattern.test(line));
}

// Returns one finding per matching line. Fixture lines are skipped so a skill
// can document a payload shape; everything else is reported with its location
// but never with the matched value, because a scanner that prints the secret it
// found writes that secret into whatever log is watching.
export function scanText(text, visibility, label = "<input>") {
  const rules = rulesFor(visibility);
  const findings = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (isFixture(line)) continue;
    for (const rule of rules) {
      if (rule.pattern.test(line)) {
        findings.push({ file: label, line: i + 1, rule: rule.id, label: rule.label });
      }
    }
  }
  return findings;
}
