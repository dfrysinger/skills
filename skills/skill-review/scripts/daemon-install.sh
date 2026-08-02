#!/usr/bin/env bash
# Install, migrate, inspect, or roll back the dreaming LaunchAgents.

set -euo pipefail
REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
TPL_DIR="$REPO/skills/skill-review/assets/launchd"
DEST_DIR="${SKILLS_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state}"
DOMAIN="${SKILLS_LAUNCHD_DOMAIN:-gui/$(id -u)}"
LAUNCHCTL="${LAUNCHCTL_BIN:-launchctl}"
LABEL_PREFIX="${SKILLS_LAUNCHD_PREFIX:-com.${USER}.skills}"
KINDS=(dreaming selftest watchdog)
LEGACY_KINDS=(sweep curator memory)
PREVIOUS_KINDS=(sweep curator memory selftest watchdog)
HALT_SWITCH="$STATE_DIR/skill-review/disable-daemon"

label_for() { echo "${LABEL_PREFIX}.$1"; }

render() {
  local kind="$1" label
  label="$(label_for "$kind")"
  sed -e "s#__HOME__#$HOME#g" \
      -e "s#__REPO__#$REPO#g" \
      -e "s#__LABEL__#$label#g" \
      "$TPL_DIR/$kind.plist.tpl" > "$DEST_DIR/$label.plist"
}

bootout_kind() {
  local kind="$1" label
  label="$(label_for "$kind")"
  "$LAUNCHCTL" bootout "$DOMAIN/$label" 2>/dev/null || true
}

backup_previous() {
  local stamp backup kind label src copied=0 legacy_copied=0
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup="$STATE_DIR/dreaming/migration-backups/$stamp"
  mkdir -p "$backup"
  for kind in "${PREVIOUS_KINDS[@]}"; do
    label="$(label_for "$kind")"
    src="$DEST_DIR/$label.plist"
    if [[ -f "$src" ]]; then
      cp "$src" "$backup/"
      copied=$((copied + 1))
      if [[ " ${LEGACY_KINDS[*]} " == *" $kind "* ]]; then
        legacy_copied=$((legacy_copied + 1))
      fi
    fi
  done
  if (( legacy_copied > 0 )); then
    printf '%s\n' "$backup" > "$STATE_DIR/dreaming/latest-migration-backup"
    echo "backed up $copied pre-migration plist(s), including $legacy_copied legacy owner(s), to $backup"
  else
    echo "backed up $copied current plist(s) to $backup; preserved existing legacy rollback pointer"
  fi
}

remove_legacy() {
  local kind label
  for kind in "${LEGACY_KINDS[@]}"; do
    label="$(label_for "$kind")"
    bootout_kind "$kind"
    rm -f "$DEST_DIR/$label.plist"
  done
}

cmd_install() {
  mkdir -p "$DEST_DIR" "$STATE_DIR/daemon-logs" "$STATE_DIR/skill-review" "$STATE_DIR/dreaming"
  touch "$HALT_SWITCH"
  chmod +x "$REPO"/skills/skill-review/scripts/daemon-*.sh \
    "$REPO"/skills/skill-review/scripts/daemon-lock.py \
    "$REPO"/skills/skill-review/scripts/dreaming-*.sh \
    "$REPO"/skills/skill-review/scripts/dreaming-state.py
  backup_previous
  remove_legacy
  for kind in "${KINDS[@]}"; do
    local label
    label="$(label_for "$kind")"
    render "$kind"
    bootout_kind "$kind"
    "$LAUNCHCTL" bootstrap "$DOMAIN" "$DEST_DIR/$label.plist"
    "$LAUNCHCTL" enable "$DOMAIN/$label" 2>/dev/null || true
    echo "loaded  $label"
  done
  echo "installed ${#KINDS[@]} agents; halt remains active until: daemon-install.sh enable"
}

cmd_enable() {
  rm -f "$HALT_SWITCH"
  echo "dreaming daemon enabled"
}

cmd_uninstall() {
  mkdir -p "$STATE_DIR/dreaming"
  backup_previous
  local kind label
  for kind in "${KINDS[@]}" "${LEGACY_KINDS[@]}"; do
    label="$(label_for "$kind")"
    bootout_kind "$kind"
    rm -f "$DEST_DIR/$label.plist"
  done
  echo "uninstalled dreaming and all known legacy agents"
}

cmd_rollback() {
  local backup="${1:-}" kind label plist lock_path
  if [[ -z "$backup" ]]; then
    [[ -f "$STATE_DIR/dreaming/latest-migration-backup" ]] || {
      echo "no migration backup recorded" >&2
      return 1
    }
    backup="$(<"$STATE_DIR/dreaming/latest-migration-backup")"
  fi
  [[ -d "$backup" ]] || { echo "backup directory not found: $backup" >&2; return 1; }
  local legacy_found=0
  for kind in "${LEGACY_KINDS[@]}"; do
    label="$(label_for "$kind")"
    [[ -f "$backup/$label.plist" ]] && legacy_found=$((legacy_found + 1))
  done
  (( legacy_found > 0 )) || {
    echo "backup contains no legacy owner plist; refusing incomplete rollback: $backup" >&2
    return 1
  }
  for kind in "${KINDS[@]}"; do
    label="$(label_for "$kind")"
    bootout_kind "$kind"
    rm -f "$DEST_DIR/$label.plist"
  done
  lock_path="$STATE_DIR/daemon.lock"
  if [[ -f "$lock_path" ]]; then
    mv "$lock_path" "$STATE_DIR/dreaming/daemon.lock.sqlite-before-rollback"
    [[ -f "${lock_path}-wal" ]] && mv "${lock_path}-wal" "$STATE_DIR/dreaming/daemon.lock.sqlite-wal-before-rollback"
    [[ -f "${lock_path}-shm" ]] && mv "${lock_path}-shm" "$STATE_DIR/dreaming/daemon.lock.sqlite-shm-before-rollback"
  fi
  for plist in "$backup"/*.plist; do
    [[ -e "$plist" ]] || continue
    cp "$plist" "$DEST_DIR/"
    label="$(basename "$plist" .plist)"
    "$LAUNCHCTL" bootstrap "$DOMAIN" "$DEST_DIR/$label.plist"
    "$LAUNCHCTL" enable "$DOMAIN/$label" 2>/dev/null || true
    echo "restored $label"
  done
  rm -f "$HALT_SWITCH"
  echo "rollback complete from $backup"
}

cmd_status() {
  local kind label
  for kind in "${KINDS[@]}" "${LEGACY_KINDS[@]}"; do
    label="$(label_for "$kind")"
    echo "--- $label ---"
    "$LAUNCHCTL" print "$DOMAIN/$label" 2>/dev/null |
      grep -E 'state|runs|last exit|program =' || echo "  (not loaded)"
  done
}

cmd_selftest() {
  local label
  label="$(label_for selftest)"
  echo "kickstarting $label under launchd ($DOMAIN)..."
  "$LAUNCHCTL" kickstart -k "$DOMAIN/$label" 2>/dev/null || {
    echo "selftest agent not loaded; run 'daemon-install.sh install' first" >&2
    return 1
  }
  sleep "${SKILLS_SELFTEST_WAIT_SECS:-25}"
  echo "=== $STATE_DIR/daemon-selftest.out ==="
  cat "$STATE_DIR/daemon-selftest.out" 2>/dev/null || echo "(no result file yet)"
}

case "${1:-}" in
  install) cmd_install ;;
  enable) cmd_enable ;;
  uninstall) cmd_uninstall ;;
  rollback) shift; cmd_rollback "${1:-}" ;;
  status) cmd_status ;;
  selftest) cmd_selftest ;;
  *) echo "usage: daemon-install.sh {install|enable|uninstall|rollback [backup]|status|selftest}" >&2; exit 2 ;;
esac
