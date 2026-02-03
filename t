#!/bin/bash
D=~/projects/a-sync/tasks
C=~/.local/share/a/t_cache

case "$1" in
  --time) echo "Startup+cache:"; time (readarray -t L < "$C")
          readarray -t L < "$C"
          echo -e "\nNext (in-process):"; time { IFS=$'\t' read -r f t <<< "${L[0]}"; echo "${t:0:30}"; }
          echo -e "\nList:"; time (cut -f2 "$C" | wc -l)
          exit;;
  -h|--help|h) echo "t        - review tasks one by one
d        - delete current
n        - next task
s        - search
l        - list all
q/Enter  - quit
t --time - benchmark"; exit;;
esac

# Rebuild cache if stale (>1s old or missing)
if [ ! -f "$C" ] || [ $(( $(date +%s) - $(stat -c %Y "$C" 2>/dev/null || echo 0) )) -gt 1 ]; then
  (for f in "$D"/*.txt; do [ -f "$f" ] && printf '%s\t%s\n' "$f" "$(head -1 "$f")"; done > "$C") &
fi

# Read cache
[ -f "$C" ] || exit
readarray -t L < "$C"
n=${#L[@]}; i=0
while [ $i -lt $n ]; do
  IFS=$'\t' read -r f t <<< "${L[$i]}"
  echo -e "\n$t\n"
  read -sn1 -p "[d]elete [n]ext [s]earch [l]ist [Enter=quit]: " c; echo
  case $c in
    d) rm "$f" 2>/dev/null; sed -i "$((i+1))d" "$C"; ((n--));;
    n) ((i++));;
    s) read -p "/" q; cut -f2 "$C" | grep -i "$q"; exit;;
    l) cut -f2 "$C"; exit;;
    *) exit;;
  esac
done
