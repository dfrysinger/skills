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
require 'Time passing alone (is|never makes)' "$skill"
require 'Migrate them at the next safe phase boundary' "$skill"
require 'stale, missing, duplicated, or inconsistent' "$skill"
require 'no challenge schedule pointed at the charter' "$skill"
require 'add the pending `liveness` entry alongside them' "$skill"
require 'Only after that replacement is live, stop every old charter' "$skill"
require 'prior schedules and registry unchanged' "$skill"
require 'To roll back a completed migration' "$skill"
require 'Existing event triggers remain' "$skill"
require 'valid throughout rollback' "$skill"
require 'legacy charter re-brief or challenge' "$skill"
require 'Re-list and require exactly one matching' "$skill"
require 'reframe trigger' "$skill"

require 'interval: 4h' "$template"
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
reject 'live eight-hour challenge schedule' "$development_loop"
reject 'scheduled challenge due' "$development_loop"
reject 'scheduled-challenge tick' "$development_loop"

printf 'event-driven unattended contract ok\n'
