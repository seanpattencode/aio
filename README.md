# AIOS - Automated Intelligence Operating System

⚠️ **IMPORTANT: This application MUST be run using Docker. Do not run orchestrator.py directly with Python.**

## Overview
AIOS (Automated Intelligence Operating System) is an extensible, modular system for running automation workflows, AI tasks, and scheduled jobs. It provides a unified platform for managing various automated processes with proper isolation and dependency management through Docker.

This project aims to create a seamless bridge between human capabilities and technological advancement, making automation accessible to everyone while maintaining sophisticated extensibility for advanced users.

## 🐳 Docker-Only Deployment

**This application is designed to run exclusively in Docker containers for:**
- **Security isolation** - Prevents jobs from affecting the host system
- **Dependency management** - All requirements are containerized
- **Consistency** - Same environment across all deployments
- **Data persistence** - Managed volumes for database and programs

### Quick Start (Docker Required)

```bash
# Clone the repository
git clone <repository-url>
cd AIOS

# Build and run with Docker Compose (RECOMMENDED)
cd docker
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Alternative Docker Run Command

```bash
# Build image
docker build -t aios-orchestrator -f docker/Dockerfile .

# Run container
docker run -d --name aios \
  -v $(pwd)/Programs:/app/Programs \
  -v $(pwd)/orchestrator.db:/app/orchestrator.db \
  -v $(pwd)/orchestrator.py:/app/orchestrator.py:ro \
  -v $(pwd)/requirements.txt:/app/requirements.txt:ro \
  -e DEVICE_TAGS=gpu,storage,browser \
  aios-orchestrator
```

## System Requirements

- **Docker** 20.10+ and **Docker Compose** 1.29+
- Python 3.11+ (included in Docker image)
- 1GB+ available disk space for container and data

## Project Architecture

```
AIOS/
├── orchestrator.py          # Main orchestrator (DO NOT RUN DIRECTLY)
├── orchestrator.db          # SQLite database (auto-created)
├── manage_jobs.py           # Comprehensive management utility (ALL commands)
├── requirements.txt         # Python dependencies (for Docker)
├── Programs/                # Job scripts directory
│   ├── google_drive_backup.py
│   ├── health_check.py
│   ├── idle_task.py
│   ├── llm_tasks.py
│   ├── reports.py
│   ├── stock_monitor.py
│   └── web_server.py
└── docker/                  # Docker configuration
    ├── Dockerfile
    ├── docker-compose.yml
    └── manage_jobs_docker.sh
```

## Management Utility

The `manage_jobs.py` script provides comprehensive management capabilities for the AIOS system. All functionality is consolidated into this single utility.

### Quick Command Reference

```bash
# Show all available commands
python3 manage_jobs.py

# System overview
python3 manage_jobs.py status

# Job management
python3 manage_jobs.py list                          # List all jobs
python3 manage_jobs.py enable <job_name>             # Enable a job
python3 manage_jobs.py disable <job_name>            # Disable a job
python3 manage_jobs.py trigger <job_name> [args...]  # Trigger a job
python3 manage_jobs.py check <job_name>              # Detailed job info
python3 manage_jobs.py reset <job_name>              # Reset job state
python3 manage_jobs.py remove <job_name>             # Remove a job

# Monitoring
python3 manage_jobs.py logs                          # View recent logs
python3 manage_jobs.py logs --job backup --limit 50  # Filtered logs
python3 manage_jobs.py logs --follow                 # Real-time logs
python3 manage_jobs.py docker-logs 100               # Docker container logs

# Database
python3 manage_jobs.py db-info                       # Database statistics
python3 manage_jobs.py backup                        # Backup database
```

### System Status Command

Get a complete overview of your AIOS system:

```bash
python3 manage_jobs.py status
```

This shows:
- Docker container status
- Number of enabled/disabled jobs
- Running and failed jobs
- Pending triggers
- Recent job executions

### Advanced Log Viewing

The consolidated log viewer supports multiple options:

```bash
# Filter by job name
python3 manage_jobs.py logs --job google_drive_backup

# Filter by log level
python3 manage_jobs.py logs --level ERROR

# Combine filters
python3 manage_jobs.py logs --job backup --level INFO --limit 100

# Follow logs in real-time (like tail -f)
python3 manage_jobs.py logs --follow
```

### Job Inspection

Get detailed information about any job:

```bash
python3 manage_jobs.py check google_drive_backup
```

This shows:
- Complete job configuration
- Current execution status
- Recent log entries
- Trigger history

### Docker Integration

While the orchestrator runs in Docker, the management utility seamlessly integrates:

```bash
# View Docker container logs directly
python3 manage_jobs.py docker-logs 50

# The utility automatically checks Docker container status
python3 manage_jobs.py status
```

For enhanced Docker integration, use the wrapper script:

```bash
./docker/manage_jobs_docker.sh trigger google_drive_backup
```

## Job Types

The system supports various job scheduling patterns:

- **`always`** - Continuously running daemons (e.g., web servers)
- **`interval`** - Fixed interval execution (e.g., backups every 2 hours)
- **`daily`** - Runs once at specified time
- **`random_daily`** - Random execution within time window
- **`trigger`** - Database-triggered on-demand execution
- **`idle`** - Runs when system is idle

### Triggering Different Job Types

The enhanced `manage_jobs.py` intelligently handles different job types:

- **Trigger jobs**: Adds to trigger queue for immediate processing
- **Interval/Daily jobs**: Resets last run time to force execution on next check
- **Always jobs**: Cannot be manually triggered (already running)

## Database Structure

All data is stored in `orchestrator.db`:

- **`scheduled_jobs`** - Job configurations and schedules
- **`jobs`** - Job execution status and last run times
- **`logs`** - All system and job logs
- **`triggers`** - On-demand job execution queue
- **`config`** - System configuration

### Direct Database Management

```bash
# View all scheduled jobs
sqlite3 orchestrator.db "SELECT * FROM scheduled_jobs;"

# Check job status
sqlite3 orchestrator.db "SELECT * FROM jobs;"

# View recent logs
sqlite3 orchestrator.db "SELECT * FROM logs ORDER BY timestamp DESC LIMIT 20;"

# Check pending triggers
sqlite3 orchestrator.db "SELECT * FROM triggers WHERE processed IS NULL;"
```

## Environment Variables

Configure the container behavior through environment variables:

- **`DEVICE_ID`** - Unique device identifier (default: container ID)
- **`DEVICE_TAGS`** - Comma-separated capabilities (e.g., "gpu,storage,browser")
  - `gpu` - For AI/ML workloads
  - `storage` - For backup and file operations
  - `browser` - For web-based services

Jobs are only executed if their required tags match the device's capabilities.

## Adding Custom Jobs

1. Create a Python script in `Programs/` directory:

```python
# Programs/my_custom_job.py
def my_function(*args, **kwargs):
    print("Running custom job")
    # Your code here
    return "Job completed"
```

2. Add job to database (container will auto-restart to pick up changes):

```bash
python3 manage_jobs.py add my_job my_custom_job.py my_function interval \
  --interval_minutes=60 --tags=storage
```

3. Verify job is scheduled:

```bash
python3 manage_jobs.py list
```

## Monitoring and Logs

All monitoring functionality is now available through `manage_jobs.py`:

### System Monitoring
```bash
# Complete system status overview
python3 manage_jobs.py status

# Check specific job details
python3 manage_jobs.py check google_drive_backup

# View database statistics
python3 manage_jobs.py db-info
```

### Log Viewing
```bash
# View recent logs (default: last 20)
python3 manage_jobs.py logs

# Filter logs by job
python3 manage_jobs.py logs --job google_drive_backup

# Filter by log level (ERROR, WARNING, INFO)
python3 manage_jobs.py logs --level ERROR

# View more logs
python3 manage_jobs.py logs --limit 100

# Follow logs in real-time
python3 manage_jobs.py logs --follow

# Combine multiple filters
python3 manage_jobs.py logs --job backup --level INFO --limit 50
```

### Docker Container Logs
```bash
# View Docker container logs
python3 manage_jobs.py docker-logs

# View last 100 lines of Docker logs
python3 manage_jobs.py docker-logs 100

# Alternative: Direct docker-compose (from docker directory)
cd docker && docker-compose logs --tail=50
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs for errors
docker-compose logs

# Ensure database has correct permissions
chmod 664 orchestrator.db

# Rebuild container
docker-compose build --no-cache
docker-compose up -d
```

### Jobs Not Running
```bash
# Check system status
python3 manage_jobs.py status

# Check if specific job is enabled
python3 manage_jobs.py check <job_name>

# Reset a stuck job
python3 manage_jobs.py reset <job_name>

# Force trigger a job
python3 manage_jobs.py trigger <job_name>

# Check device tags in container
docker exec aios-orchestrator env | grep DEVICE_TAGS
```

### Database Issues
```bash
# Check database health
python3 manage_jobs.py db-info

# Backup database
python3 manage_jobs.py backup

# Backup to specific location
python3 manage_jobs.py backup /path/to/backup.db

# Reset a specific job's state
python3 manage_jobs.py reset <job_name>
```

### Dependency Errors
```bash
# Ensure requirements.txt exists
ls -la requirements.txt

# Rebuild container with dependencies
docker-compose build --no-cache
docker-compose up -d

# Verify dependencies in container
docker exec aios-orchestrator pip list
```

## Security Considerations

- **Always run through Docker** for proper isolation
- Never expose database directly to network
- Use environment variables for sensitive configuration
- Regularly backup `orchestrator.db`
- Review job scripts before adding to `Programs/`
- Monitor logs for suspicious activity

## Backup and Recovery

### Database Backup

```bash
# Create local backup with timestamp
python3 manage_jobs.py backup

# Backup to specific location
python3 manage_jobs.py backup /backups/aios_backup.db

# Trigger Google Drive backup
python3 manage_jobs.py trigger google_drive_backup

# Check backup job status
python3 manage_jobs.py check google_drive_backup

# View backup-related logs
python3 manage_jobs.py logs --job backup
```

### Recovery

```bash
# Restore from backup
cp /path/to/backup/orchestrator_YYYYMMDD_HHMMSS.db orchestrator.db

# Restart container to load restored database
cd docker && docker-compose restart

# Verify restoration
python3 manage_jobs.py status
python3 manage_jobs.py db-info
```

## Development Guidelines

1. **Never run orchestrator.py directly** - Always use Docker
2. Test jobs in isolation before adding to scheduler
3. Use appropriate job types for different workloads
4. Tag jobs properly for device capability matching
5. Monitor logs regularly for errors
6. Keep database backups

## Future Enhancements

- Web UI for job management
- Distributed job execution across multiple devices
- Advanced scheduling with cron expressions
- Job dependency management
- Resource usage monitoring
- Automatic failure recovery
- Plugin system for external integrations

## License

[Specify your license here]

## Contributing

Contributions welcome! Please ensure:
1. All code runs properly in Docker
2. Tests pass in containerized environment
3. Documentation is updated
4. Security best practices are followed

---

**Remember: This system MUST be run using Docker. Direct Python execution is not supported and will show a warning.**