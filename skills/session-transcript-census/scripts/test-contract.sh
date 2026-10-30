#!/bin/sh
set -eu

skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
skill="$skill_dir/SKILL.md"

require() {
	pattern=$1
	if ! grep -Eq "$pattern" "$skill"; then
		printf 'missing required transcript census contract: %s\n' "$pattern" >&2
		exit 1
	fi
}

require 'Cloud history'
require 'Local and running sessions'
require 'source: "local"'
require 'queried directly in both stores'
require 'empty result from one source is unresolved'
require 'Stable session or task IDs are authority'
require 'why did you stop'
require 'any progress'
require 'historical-case-capture'
require 'searched all sessions.*both cloud and local/running'

printf 'session transcript census contract ok\n'
