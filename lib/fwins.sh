#!/bin/sh
# a fwins — fleet windows for /fw: device<TAB>target<TAB>label<TAB>pane-tail per line (target = local
# idx or ssh:<dev>:<idx>). pane-tail = flattened tail of the window's .0 pane — the find box searches
# it (convo words) and idle rows show it; 3 fields before = find saw names only (Sean 2026-09-10).
# Stable order: local first then fleet.txt, per-device files so ssh races never reorder; unreachable
# device keeps LAST-KNOWN rows; same-hostname alias dropped as dup. serve.c rate-limits (/fwins).
# Args: $1=DEV $2=DDIR. Run bare to debug.
DEV="${1:-$(hostname)}"; D="${2:-$HOME/a/adata/local}"; OUT="$D/fleetwins.txt"
command -v flock >/dev/null 2>&1 && { exec 9>"$D/.fwins.lock"; flock -n 9 || exit 0; }  # singleton: never stampede the fanout
TD=$(mktemp -d "${TMPDIR:-/tmp}/fwins.XXXXXX") || exit 0
HN=$(hostname)
RQ='tmux list-windows -t a -F "#I|#W" 2>/dev/null | while IFS="|" read -r i w; do printf "%s\t%s\t%s\n" "$i" "$w" "$(tmux capture-pane -pJt a:$i.0 -S -200 2>/dev/null | tr -cs "[:alnum:]" " " | tail -c 1500)"; done'
sh -c "$RQ" | awk -v d="$DEV" '{print d"\t"$0}' > "$TD/.local"
devs=$(awk 'NR>1 && $2=="ssh"{print $1}' "$D/fleet.txt" 2>/dev/null)
for h in $devs; do   # hostname first: proves the ssh answered (vs "answered but has no tmux") and unmasks self-routes
  ( timeout 12 a ssh "$h" "hostname; $RQ" </dev/null 2>/dev/null \
      | awk -v d="$h" -v hn="$HN" \
          'NR==1{if($0==hn){print "#DUP";exit}print "#OK";next}{print d"\tssh:"d":"$0}' ) > "$TD/$h" &
done
wait
{ cat "$TD/.local"
  for h in $devs; do
    case "$(head -1 "$TD/$h" 2>/dev/null)" in
      "") awk -F'\t' -v h="$h" '$1==h' "$OUT" 2>/dev/null;;   # unreachable: keep last-known
      '#DUP') ;;                                              # this box under another name
      *) tail -n +2 "$TD/$h";;                                # drop the #OK marker
    esac
  done
} > "$TD/.out"
[ -s "$TD/.out" ] && mv "$TD/.out" "$OUT"
rm -rf "$TD"
