#!/bin/sh
set -eu

skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
repo_root=$(CDPATH= cd -- "$skill_dir/../.." && pwd)
skill="$skill_dir/SKILL.md"
template="$skill_dir/references/brief-template.md"
rollback="$skill_dir/references/legacy-schedule-rollback.md"
development_loop="$repo_root/skills/development-loop/SKILL.md"

require() {
	pattern=$1
	file=$2
	if ! grep -Eq "$pattern" "$file"; then
		printf 'missing required contract %s in %s\n' "$pattern" "$file" >&2
		exit 1
	fi
}

reject() {
	pattern=$1
	file=$2
	if grep -Eq "$pattern" "$file"; then
		printf 'found retired contract %s in %s\n' "$pattern" "$file" >&2
		exit 1
	fi
}

require '[Ee]vent-driven governance' "$skill"
require 'interval=4h' "$skill"
require 'interval=1h' "$skill"
require 'alone never makes a challenge due' "$skill"
require 'Migrate at the next safe phase boundary' "$skill"
require 'stale, missing, duplicated, or inconsistent' "$skill"
require 'no legacy' "$skill"
require 'charter_check.*4h' "$skill"
require 'progress.*1h' "$skill"
require 'both returned IDs' "$skill"
require 'confirmed four-hour check live as the recovery path' "$skill"
require 'mark progress pending' "$skill"
require 'preserve each launched model attempt' "$skill"
require 'pre-registered repetitions' "$skill"
require 'rubber-duck agent' "$skill"
require 'Record each real stall' "$skill"
require 'even when' "$skill"
require 'ALL independent ready scopes' "$skill"
require 'Complete this audit before' "$skill"
require 'every unowned' "$skill"
require 'stop BOTH registered' "$skill"
require 'completed migration' "$skill"
require 'Existing event triggers remain' "$skill"
require 'throughout rollback' "$skill"
require 'legacy charter re-brief/challenge' "$skill"
require 'Re-list and require exactly one matching schedule' "$skill"
require 'reframe trigger' "$skill"

require 'interval: 4h' "$template"
require 'interval: 1h' "$template"
require 'charter_check:' "$template"
require 'progress:' "$template"
require 'Mark second-hand incidents unverified' "$template"
require 'every hourly progress nudge' "$template"
require 'ready-lane audit before ending' "$template"
require 'run start' "$template"
require 'compaction or resumption' "$template"
require 'candidate movement' "$template"
require 'phase boundary' "$template"
require 'failure' "$template"
require 'ownership handoff' "$template"
require 'material user direction' "$template"
require 'Time passing alone never makes a challenge due' "$template"
require 'reframe trigger' "$template"
require 'liveness schedule' "$development_loop"
require 'constraint challenges remain event-driven' "$development_loop"
require 'compaction or resumption, candidate movement' "$development_loop"
require 'ownership handoff, or material user direction' "$development_loop"
require 'build, external' "$development_loop"
require 'agent, approval, or live system becomes the current wait' "$development_loop"

require 'manage_schedule action=create interval=2h' "$rollback"
require 'manage_schedule action=create interval=8h' "$rollback"
require 'Rollback only' "$rollback"

reject 'interval=2h' "$skill"
reject 'interval=8h' "$skill"
reject 'interval: 2h' "$template"
reject 'interval: 8h' "$template"
reject '^  constraint_challenge:' "$template"
reject '^  liveness:' "$template"
reject 'select the cheapest evidence-backed next action' "$skill"
reject 'hourly idle-frontier nudge' "$template"
reject 'live eight-hour challenge schedule' "$development_loop"
reject 'scheduled challenge due' "$development_loop"
reject 'scheduled-challenge tick' "$development_loop"

printf 'event-driven unattended contract ok\n'
