# SUBAGENTS.md Feature (Deprecated)

Logic removed from sess.py. Previously prepended SUBAGENTS.md content to CLI prompts:

```python
if prompt and (sf := os.path.join(wd, 'SUBAGENTS.md')) and os.path.exists(sf):
    prompt = open(sf).read().strip() + ' ' + prompt
```
