# Hermes curator config — defaults

Lifted from `agent/curator.py` upstream constants. Override by editing
`~/.copilot/skill-state/curator.json` (the same file the skill writes its
own state to).

| Field | Default | Meaning |
|---|---|---|
| `interval_hours` | 168 (7 days) | How often the weekly schedule fires `/skill-curator --dry-run`. |
| `min_idle_hours` | 2 | (Hermes-only) idle requirement before background trigger. N/A in Copilot CLI — we use `manage_schedule` instead. |
| `stale_after_days` | 30 | A skill marked `stale` after this many days without activity. Stale skills surface in `status` output but are not auto-archived. |
| `archive_after_days` | 90 | A skill becomes archive-eligible after this many days. The curator's live mode will archive it unless pinned. |
| `prune_builtins` | N/A | Hermes-only — distinguishes built-in vs agent-created. In Copilot CLI all skills in `~/code/skills/` are user-controlled; treat the whole repo as eligible. |

## Override file shape

`~/.copilot/skill-state/curator.json`:

```json
{
  "last_run_at": "2026-06-02T20:55:00-06:00",
  "last_run_duration_seconds": 42,
  "last_run_summary": "0 consolidations, 0 prunings (library small)",
  "last_report_path": "/Users/dfrysinger/.copilot/skill-state/reports/20260602-205500-curator-report.md",
  "paused": false,
  "run_count": 1,
  "config_overrides": {
    "interval_hours": 168,
    "stale_after_days": 30,
    "archive_after_days": 90
  }
}
```

`paused: true` halts both the weekly schedule (via a guard at the top of
the curator workflow) and any manual `/skill-curator --live` run. Manual
`/skill-curator status` and `--dry-run` still work, mirroring
`hermes curator pause`.

## Setting it up

The state file is created on first run with all defaults; you only need
to override if you want different thresholds. To pause:

```bash
~/code/skills/skills/skill-curator/scripts/curator-state.sh set paused true
```

To resume:

```bash
~/code/skills/skills/skill-curator/scripts/curator-state.sh set paused false
```
