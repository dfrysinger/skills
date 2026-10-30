#!/bin/sh
set -eu

skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
repo_root=$(CDPATH= cd -- "$skill_dir/../.." && pwd)
skill="$skill_dir/SKILL.md"
reference="$skill_dir/references/design-incubation.md"
design_doc="$repo_root/skills/design-doc/SKILL.md"

require() {
	pattern=$1
	file=$2
	if ! grep -Eq "$pattern" "$file"; then
		printf 'missing design-incubation contract %s in %s\n' "$pattern" "$file" >&2
		exit 1
	fi
}

require 'Arm continuity for a long systemic or critical design' "$design_doc"
require 'before launching the first' "$design_doc"
require 'asynchronous owner' "$design_doc"
require 'return the work order to' "$design_doc"
require 'development-loop' "$design_doc"
require 'Design-incubation mode' "$skill"
require '30-minute.*liveness and recovery backstop' "$skill"
require 'not create the normal hourly progress and four-hour charter pair' "$skill"
require 'design_progress' "$reference"
require 'interval=30m' "$reference"
require 'Design cycle:.*DESIGN_CYCLE' "$reference"
require 'waiting_user' "$reference"
require 'persisting its stopped status without repeating the question' "$reference"
require 'increments and persists it before delivery' "$reference"
require 'idle.*steering' "$reference"
require 'activation' "$reference"
require 'handoff_pending' "$reference"
require 'let `development-loop` choose attended or unattended execution' "$reference"
require 'normal hourly progress' "$reference"
require 'four-hour charter reminders' "$reference"
require 'before stopping the design reminder' "$reference"
require 'leaving unrelated schedules untouched' "$reference"
require 'implementation-objective delivery is interrupted' "$reference"
require 'implementation_objective_handoff' "$reference"
require 'status: prepared' "$reference"
require 'receipt: null' "$reference"
require 'submitted' "$reference"
require 'that was not submitted' "$reference"
require 'unresolved implementation-objective handoff' "$skill"
require 'deduplication identity' "$skill"

printf 'design incubation contract ok\n'
