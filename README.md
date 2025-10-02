# AIOS - AI Operating System

## Core Commands
- `aios start` - launch web interface
- `aios stop` - shutdown system
- `aios status` - show processes
- `aios <cmd>` - run any command

## Testing

### Automated Testing
```bash
# Test all programs automatically
python3 testing/test_programs.py

# Test programs with sample output for verification
python3 testing/test_with_examples.py

# Test web interface with Playwright
python3 testing/playwright/test_all.py

# Test interactions
python3 testing/playwright/test_interactions.py
```

### Individual Program Testing
```bash
# Todo Manager
python3 programs/todo/todo.py list
python3 programs/todo/todo.py add "New task"
python3 programs/todo/todo.py done 1
python3 programs/todo/todo.py clear

# Services
python3 services/service.py list
python3 services/service.py start service_name
python3 services/service.py stop service_name
python3 services/service.py status

# Feed Messages
python3 services/feed.py list
python3 services/feed.py add "Message text"
python3 services/feed.py view
python3 services/feed.py clear

# Jobs
python3 services/jobs.py list
python3 services/jobs.py summary
python3 services/jobs.py running
python3 services/jobs.py review
python3 services/jobs.py done

# Processes
python3 services/processes.py json
python3 services/processes.py list
python3 services/processes.py start script.py
python3 services/processes.py stop script.py

# Settings
python3 programs/settings/settings.py get theme
python3 programs/settings/settings.py set theme light
python3 programs/settings/settings.py set time_format 24h

# AutoLLM
python3 programs/autollm/autollm.py status
python3 programs/autollm/autollm.py run /path/to/repo 1 model "task"
python3 programs/autollm/autollm.py clean
python3 programs/autollm/autollm.py output job_id
python3 programs/autollm/autollm.py accept job_id

# Workflow
python3 programs/workflow/workflow.py list
python3 programs/workflow/workflow.py add 0 "Task text"
python3 programs/workflow/workflow.py expand node_id "instruction"
python3 programs/workflow/workflow.py branch node_id
python3 programs/workflow/workflow.py exec node_id

# Worktree Manager
python3 programs/worktree/worktree_manager.py list
python3 programs/worktree/worktree_manager.py create /repo/path branch_name
python3 programs/worktree/worktree_manager.py remove /worktree/path
```

## Context Generation
```bash
# Generate project context (excludes testing folder)
python3 -c "from services import context_generator; context_generator.generate()"

# Files created:
# - projectContext.txt (production code only)
# - projectContextWithTests.txt (includes testing code)
```