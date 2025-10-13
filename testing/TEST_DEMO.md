# Testing AIOS Demo

This document contains copy-pasteable commands to test AIOS functionality.

## Basic Demo (Copy these exactly)

Start AIOS:
```bash
./aios.py
```

In the AIOS prompt, enter these commands one at a time (WITHOUT the ❯ character):

```
demo: Create file | echo 'Hello World' > test.txt
demo: Show content | cat test.txt
demo: List files | ls -la
run demo
```

## Attach Demo (Interactive Terminal)

Start AIOS:
```bash
./aios.py
```

In the AIOS prompt:
```
demo: Start shell | bash
run demo
attach demo
```

Your browser will open with an interactive terminal connected to the bash session.

## Simple Mode Demo

Run a task in simple (non-interactive) mode:
```bash
./aios.py --simple tasks/test_task.json
```

## Important Notes

1. **Do NOT include the ❯ prompt character** when copy-pasting commands
2. The ❯ character is just to show what the prompt looks like
3. Copy only the actual command text
4. Each command should be on its own line

## Working Example

If you see this in documentation:
```
❯ demo: Test | echo "hello"
❯ run demo
```

You should type/paste:
```
demo: Test | echo "hello"
run demo
```

(Notice: NO ❯ character)
