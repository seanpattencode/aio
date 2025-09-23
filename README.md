# AIOS - All-In-One Scheduler

Simplified systemd-based service manager for Python applications.

## Files

- **chatgpt2AIOSE.py** - Main AIOSE service manager (systemd-only mode)
- **hybridTODO.py** - Example TODO web application
- **GUIDE.txt** - Quick start guide and usage instructions
- **data/** - Database storage for applications
- **logs/** - Application log files
- **archive/** - Previous implementations and unused files

## Quick Start

```bash
# Add a service
python3 chatgpt2AIOSE.py add --name myapp "python3 /full/path/to/app.py"

# Manage service
python3 chatgpt2AIOSE.py start myapp
python3 chatgpt2AIOSE.py stop myapp
python3 chatgpt2AIOSE.py status myapp

# List all services
python3 chatgpt2AIOSE.py list
```

See GUIDE.txt for detailed instructions.