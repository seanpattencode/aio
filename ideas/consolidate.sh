#!/bin/bash
# Consolidate all idea docs into one markdown file
cd "$(dirname "$0")"
out="ALL.md"
echo "# Ideas" > "$out"
for f in *.md; do
    [[ "$f" == "$out" ]] && continue
    echo -e "\n---\n" >> "$out"
    cat "$f" >> "$out"
done
echo "$out"
