#!/usr/bin/env bash
# daemon-install.sh — install/uninstall the skills self-learning LaunchAgents.
#
#   daemon-install.sh install     # render templates, load, enable all 3 agents
#   daemon-install.sh uninstall   # bootout + remove all 3 agents
#   daemon-install.sh status      # show load state + next-run info
#   daemon-install.sh selftest    # run the self-test UNDER launchd context
#
# Portability: the LaunchAgent label prefix defaults to com.${USER}.skills, so
# a forker on a different macOS account gets unique labels with no edits.
# Override via SKILLS_LAUNCHD_PREFIX. Repo path defaults to ~/code/skills,
# override via SKILLS_REPO_ROOT.
#
# LaunchAgents installed (kind suffix appended to the prefix):
#   ${PREFIX}.sweep     daily 09:15  (autonomous skill creation)
#   ${PREFIX}.curator   daily 09:30  (dry-run consolidation report)
#   ${PREFIX}.selftest  manual       (kickstart-only preflight)

set -u
REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
TPL_DIR="$REPO/skills/skill-review/assets/launchd"
DEST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
LABEL_PREFIX="${SKILLS_LAUNCHD_PREFIX:-com.${USER}.skills}"
KINDS=(sweep curator selftest watchdog)

label_for() { echo "${LABEL_PREFIX}.$1"; }

render() {  # render one template -> $DEST_DIR/<label>.plist
  local kind="$1"
  local label
  label="$(label_for "$kind")"
  sed -e "s#__HOME__#$HOME#g" \
      -e "s#__REPO__#$REPO#g" \
      -e "s#__LABEL__#$label#g" \
      "$TPL_DIR/$kind.plist.tpl" > "$DEST_DIR/$label.plist"
}

cmd_install() {
  mkdir -p "$DEST_DIR" "$HOME/.copilot/skill-state/daemon-logs"
  chmod +x "$REPO"/skills/skill-review/scripts/daemon-*.sh
  for kind in "${KINDS[@]}"; do
    local label
    label="$(label_for "$kind")"
    render "$kind"
    launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$DEST_DIR/$label.plist" \
      && echo "loaded  $label" || { echo "FAILED to load $label" >&2; return 1; }
    launchctl enable "$DOMAIN/$label" 2>/dev/null || true
  done
  echo "installed 4 agents (prefix: $LABEL_PREFIX). Run: daemon-install.sh selftest"
}

cmd_uninstall() {
  for kind in "${KINDS[@]}"; do
    local label
    label="$(label_for "$kind")"
    launchctl bootout "$DOMAIN/$label" 2>/dev/null && echo "booted out $label" || echo "not loaded: $label"
    rm -f "$DEST_DIR/$label.plist"
  done
  echo "uninstalled."
}

cmd_status() {
  for kind in "${KINDS[@]}"; do
    local label
    label="$(label_for "$kind")"
    echo "--- $label ---"
    launchctl print "$DOMAIN/$label" 2>/dev/null | grep -E 'state|runs|last exit|program =' || echo "  (not loaded)"
  done
}

cmd_selftest() {
  local label
  label="$(label_for selftest)"
  echo "kickstarting $label under launchd ($DOMAIN)..."
  launchctl kickstart -k "$DOMAIN/$label" 2>/dev/null || {
    echo "selftest agent not loaded; run 'daemon-install.sh install' first" >&2; return 1; }
  sleep 25
  echo "=== $HOME/.copilot/skill-state/daemon-selftest.out ==="
  cat "$HOME/.copilot/skill-state/daemon-selftest.out" 2>/dev/null || echo "(no result file yet)"
}

case "${1:-}" in
  install)   cmd_install ;;
  uninstall) cmd_uninstall ;;
  status)    cmd_status ;;
  selftest)  cmd_selftest ;;
  *) echo "usage: daemon-install.sh {install|uninstall|status|selftest}" >&2; exit 2 ;;
esac
