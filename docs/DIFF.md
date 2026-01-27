# aio diff

Shows what will be pushed, not what git technically considers a "diff".

## Philosophy

Most users workflow:
```
aio diff    → see everything
aio push    → adds all, commits, pushes
```

Untracked files in the repo = "I made this, will commit it, just haven't `git add`ed yet". They get added with everything else on push. The diff tool reflects what will actually be pushed.

**aio diff answers:** "What's the total size of what I'm about to push?"

**Not:** "What does `git diff` technically show right now?"

## Output

```
2 files (diff.py test.txt), +10/-4 lines (incl. 1 untracked) | Net: +6 lines, +179 tokens
```

- **files**: All changed + untracked files, basenames truncated to 5
- **lines**: Insertions/deletions including untracked file contents
- **tokens**: Estimated using tiktoken (cl100k_base), falls back to len/4
- **incl. N untracked**: Notes when untracked files are counted

## Design decisions

- Pragmatic over pure: Shows real commit size, not git staging state
- Untracked files count as additions: User will add them anyway
- Token counting: Useful for estimating PR review effort and LLM context usage
- Truncated file list: Keeps output scannable for large changesets
