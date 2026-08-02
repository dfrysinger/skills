#!/usr/bin/env bash
# mem-extract.sh — dump all currently-visible Copilot memories as JSON.
#
# The memory page (github.com/settings/copilot/memory) is a capped, rotating
# window of 100. This extracts whatever 100 are visible right now as
#   [{"body": "...", "subject": "..."} , ...]
# Over successive weekly runs the hidden ones surface as deletable ones are
# removed, so the curator drains the full (~200) store across runs.
#
# Login state is detected INSIDE the single browse call, so an expired session
# is distinguished from a transient browse/lock failure.
#
# Exit codes: 0 ok (JSON on stdout), 5 = not logged in (session expired),
#             3/4 = helper/browse failure.
#
# Usage: mem-extract.sh            # JSON array to stdout
#        mem-extract.sh -o FILE    # write to FILE instead

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/mem-lib.sh"

OUT=""
[ "${1:-}" = "-o" ] && OUT="${2:-}"

read -r -d '' JS <<'JSEOF' || true
(() => {
  const LI = "li[class*=ListItem-module__listItem]";
  const DEL = 'button[aria-label="Delete memory"]';
  function ready(tries){return new Promise(r=>{const t=setInterval(()=>{
    const b=document.querySelectorAll(DEL).length, h=document.querySelectorAll(LI+" h4").length;
    if((b>=5 && h>=5) || tries--<=0){clearInterval(t);r();}},400);});}
  return ready(30).then(()=>{
    const rows=[];
    document.querySelectorAll(LI).forEach(li=>{
      const del=li.querySelector(DEL); if(!del) return;
      const h4=li.querySelector("h4");
      const body=(h4?h4.textContent:"").replace(/\s+/g," ").trim();
      if(!body) return;
      let subject="";
      const chip=li.querySelector('[class*=Label], [class*=chip], [class*=Token]');
      if(chip) subject=chip.textContent.replace(/\s+/g," ").trim().slice(0,40);
      rows.push({body, subject});
    });
    if(rows.length>0) return JSON.stringify({status:"ok", rows});
    const signedOut = /sign in to github|sign in \u00b7 github/i.test(document.title)
      || !!document.querySelector('input[name="password"], a[href*="/login"]');
    return JSON.stringify({status: signedOut ? "loggedout" : "empty", rows:[]});
  });
})()
JSEOF

RAW="$(mem_browse_eval "$JS")" || exit $?
JSON="$(printf '%s' "$RAW" | mem_unwrap)" || { echo "MEM_ERR: could not parse extract output" >&2; exit 4; }

STATUS="$(/usr/bin/python3 -c 'import sys,json;print(json.loads(sys.stdin.read()).get("status","?"))' <<<"$JSON")"
case "$STATUS" in
  loggedout)
    echo "MEM_ERR: browse session signed out — run: authenticated-browse auth $MEM_PROFILE $MEM_URL" >&2
    mem_notify "memory-curator: browse session expired; needs manual re-auth"
    exit 5 ;;
  ok) : ;;
  *) echo "MEM_ERR: extract returned status=$STATUS (empty/mid-hydration)" >&2; exit 4 ;;
esac

ROWS="$(/usr/bin/python3 -c 'import sys,json;print(json.dumps(json.loads(sys.stdin.read())["rows"]))' <<<"$JSON")"
N="$(/usr/bin/python3 -c 'import sys,json;print(len(json.loads(sys.stdin.read())))' <<<"$ROWS")"

if [ -n "$OUT" ]; then printf '%s\n' "$ROWS" > "$OUT"; echo "wrote $N memories to $OUT" >&2
else printf '%s\n' "$ROWS"; fi
