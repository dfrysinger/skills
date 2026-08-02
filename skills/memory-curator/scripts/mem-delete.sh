#!/usr/bin/env bash
# mem-delete.sh — signature-matched deletion of specific Copilot memories.
#
# SAFETY: never blind-deletes. Reads a JSON array of memory bodies to delete
# (stdin or -f FILE), computes a normalized 160-char signature for each,
# and clicks the per-row Delete button ONLY for rows whose text starts with a
# matching signature. Uncatalogued memories are never touched.
#
# The caller is responsible for the hard rule: only pass bodies that were
# (a) exact-duplicate, or (b) already rolled into a skill AND committed to git.
#
# Runs multiple passes because deleting reveals previously-hidden rows and the
# DOM re-hydrates. Stops when a pass deletes 0.
#
# Exit codes: 0 ok, 5 = not logged in, 3/4 = helper/browse failure.
#
# Usage: mem-delete.sh -f bodies.json
#        cat bodies.json | mem-delete.sh

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/mem-lib.sh"

IN=""
[ "${1:-}" = "-f" ] && IN="${2:-}"
if [ -n "$IN" ]; then BODIES="$(cat "$IN")"; else BODIES="$(cat)"; fi

# Build the newline-delimited signature allowlist (160 chars, ws-normalized,
# lowercased). The signature must be long enough that two distinct memories
# cannot share one; a short prefix silently widens every delete.
SIGS="$(/usr/bin/python3 - "$BODIES" <<'PY'
import sys,json,re
arr=json.loads(sys.argv[1])
def sig(s): return re.sub(r"\s+"," ",s).strip().lower()[:160]
seen=set()
for b in arr:
    s=sig(b if isinstance(b,str) else b.get("body",""))
    if len(s)>=40 and s not in seen:
        seen.add(s); print(s)
PY
)"
NSIG="$(printf '%s\n' "$SIGS" | grep -c . || true)"
[ "$NSIG" -gt 0 ] || { echo "MEM_ERR: no valid signatures to delete (>=40 chars)" >&2; exit 4; }
echo "delete allowlist: $NSIG signatures" >&2

# JS: given the signature list, delete ALL matching rows in ONE page load
# (clicking sequentially with a short delay so the server keeps up), then
# report how many it removed. Loop passes in bash because deleting reveals
# previously-hidden rows and the DOM re-hydrates between page loads.
del_pass() {
  local sigs_json="$1"
  local js
  js="(() => {
    const SIGS = $sigs_json;
    const LI='$MEM_LI_SEL', DEL='$MEM_DEL_SEL';
    const norm=s=>s.replace(/\\s+/g,' ').trim().toLowerCase();
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    return (async () => {
      const sel=()=>[...document.querySelectorAll(LI)];
      for (let w=0; w<30; w++){
        const b=document.querySelectorAll(DEL).length, h=document.querySelectorAll(LI+' h4').length;
        if (b>=5 && h>=5) break;
        await sleep(400);
      }
      const done=[]; const ambiguous=[];
      for (let n=0; n<60; n++){
        const lis=sel();
        let hit=null;
        // A signature must identify exactly one memory. If it matches several,
        // deleting either one is a guess, so skip it and report the ambiguity
        // rather than destroying a memory the operator did not name.
        for (const sig of SIGS){
          const matches=[];
          for (const li of lis){
            const del=li.querySelector(DEL); if(!del) continue;
            const h4=li.querySelector('h4'); const body=norm(h4?h4.textContent:'');
            if(!body) continue;
            if (body.startsWith(sig)) matches.push({del,body});
          }
          if (matches.length===1){ hit=matches[0]; break; }
          if (matches.length>1) ambiguous.push(sig.slice(0,70));
        }
        if(!hit) break;
        hit.del.click();
        done.push(hit.body.slice(0,70));
        await sleep(700);
      }
      return JSON.stringify({count:done.length, bodies:done, ambiguous:[...new Set(ambiguous)]});
    })();
  })()"
  mem_browse_eval "$js"
}

SIGS_JSON="$(/usr/bin/python3 -c 'import sys,json;print(json.dumps([l for l in sys.stdin.read().splitlines() if l]))' <<<"$SIGS")"

TOTAL=0
for pass in $(seq 1 12); do
  RAW="$(del_pass "$SIGS_JSON")" || exit $?
  VAL="$(printf '%s' "$RAW" | mem_unwrap)" || { echo "MEM_ERR: parse delete result" >&2; exit 4; }
  C="$(/usr/bin/python3 -c 'import sys,json;print(json.loads(sys.stdin.read())["count"])' <<<"$VAL")"
  /usr/bin/python3 -c 'import sys,json
d=json.loads(sys.stdin.read())
for b in d["bodies"]: print("  deleted:",b)
for a in d.get("ambiguous",[]): print("  SKIPPED (matches >1 memory):",a)' <<<"$VAL" >&2
  TOTAL=$((TOTAL+C))
  echo "pass $pass: removed $C (running $TOTAL)" >&2
  [ "$C" -eq 0 ] && break
  sleep 3
done

echo "mem-delete: removed $TOTAL memories" >&2
echo "$TOTAL"
