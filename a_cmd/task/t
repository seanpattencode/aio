#!/bin/bash
# Task review - supports folders (text_*.txt, prompt_*.txt) and legacy .txt
D=~/a-sync/tasks
DEV=$(cat ~/.local/share/a/.device 2>/dev/null || hostname)

case "$1" in
  -h|--help|h) echo "t - review tasks
d     delete task
n     next task
a     add text candidate
p     add prompt
s     search
l     list all
v     view all candidates
Enter quit"; exit;;
esac

# Get tasks (folders first by mtime, then legacy .txt)
tasks=()
while IFS= read -r -d '' f; do
  if [ -d "$f" ]; then
    latest=$(ls -t "$f"/text_*.txt 2>/dev/null | head -1)
    [ -n "$latest" ] && tasks+=("$f"$'\t'"$(head -1 "$latest")")
  elif [ -f "$f" ] && [[ "$f" == *.txt ]]; then
    tasks+=("$f"$'\t'"$(head -1 "$f")")
  fi
done < <(find "$D" -maxdepth 1 \( -type d -o -name "*.txt" \) ! -name "." ! -name "*.txt" -print0 2>/dev/null; find "$D" -maxdepth 1 -name "*.txt" -print0 2>/dev/null)

n=${#tasks[@]}; i=0
while [ $i -lt $n ]; do
  IFS=$'\t' read -r f t <<< "${tasks[$i]}"

  # Show task
  echo -e "\n━━━ Task $((i+1))/$n ━━━"
  if [ -d "$f" ]; then
    pc=$(ls "$f"/prompt_*.txt 2>/dev/null | wc -l)
    tc=$(ls "$f"/text_*.txt 2>/dev/null | wc -l)
    echo -e "[$tc texts, $pc prompts]\n"
    for tf in $(ls -t "$f"/text_*.txt 2>/dev/null); do
      echo "• $(head -1 "$tf")"
    done
  else
    echo -e "\n$t"
  fi

  echo
  read -sn1 -p "[d]el [n]ext [a]dd text [p]rompt [v]iew [s]earch [l]ist [Enter=quit]: " c; echo
  case $c in
    d)
      mkdir -p "$D/.archive"
      mv "$f" "$D/.archive/"
      echo "✓ archived to .archive/$(basename "$f")"
      unset 'tasks[i]'; tasks=("${tasks[@]}"); ((n--));;
    n) ((i++));;
    a)
      read -p "New text: " newt
      if [ -n "$newt" ]; then
        if [ ! -d "$f" ]; then
          # Migrate legacy to folder
          td="$D/$(basename "${f%.txt}")"
          mkdir -p "$td"
          mv "$f" "$td/text_00000000_migrated.txt"
          f="$td"
        fi
        echo "$newt" > "$f/text_$(date +%m%d%H%M%S)_${DEV}.txt"
        echo "✓ text added"
      fi;;
    p)
      read -p "Prompt: " newp
      if [ -n "$newp" ]; then
        if [ ! -d "$f" ]; then
          td="$D/$(basename "${f%.txt}")"
          mkdir -p "$td"
          mv "$f" "$td/text_00000000_migrated.txt"
          f="$td"
        fi
        echo "$newp" > "$f/prompt_$(date +%m%d%H%M%S)_${DEV}.txt"
        echo "✓ prompt added"
      fi;;
    v)
      if [ -d "$f" ]; then
        echo -e "\n=== $(basename "$f") ==="
        for tf in $(ls "$f"/*.txt 2>/dev/null | sort); do
          echo -e "\n[$(basename "$tf" .txt)]"
          cat "$tf"
        done
      else
        echo -e "\n$t"
      fi
      read -sn1 -p "Press any key..." ;;
    s) read -p "/" q; printf '%s\n' "${tasks[@]}" | cut -f2 | grep -i "$q"; exit;;
    l) printf '%s\n' "${tasks[@]}" | cut -f2; exit;;
    *) exit;;
  esac
done
echo "Done - reviewed all tasks"
