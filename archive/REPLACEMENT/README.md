# AIOS Systemd Orchestrator

## Commands
```bash
python3 systemdOrchestrator.py         # Show status
python3 systemdOrchestrator.py start   # Start all services
python3 systemdOrchestrator.py stop    # Stop all services
python3 systemdOrchestrator.py restart # Restart all services
python3 systemdOrchestrator.py status  # JSON status output
python3 systemdOrchestrator.py cleanup # Remove all services
```

Services auto-start when script runs without args.