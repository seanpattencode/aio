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
├── manage_jobs.py           # Job management CLI utility
├── requirements.txt         # Python dependencies (for Docker)
├── Programs/                # Job scripts directory
│   ├── google_drive_backup.py
│   ├── health_check.py
│   ├── idle_task.py
│   ├── llm_tasks.py
│   ├── reports.py
│   ├── stock_monitor.py
│   └── web_server.py
├── docker/                  # Docker configuration
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── manage_jobs_docker.sh
└── README.md
```

## Job Management

### Managing Jobs from Host System

While the orchestrator runs in Docker, you can manage jobs from the host system:

```bash
# List all jobs
python3 manage_jobs.py list

# Enable/disable jobs
python3 manage_jobs.py enable <job_name>
python3 manage_jobs.py disable <job_name>

# Trigger a job immediately
python3 manage_jobs.py trigger <job_name> [key=value...]

# Remove a job
python3 manage_jobs.py remove <job_name>
```

### Docker-Aware Management Script

For better integration with Docker:

```bash
# Use the Docker-aware wrapper
./docker/manage_jobs_docker.sh trigger google_drive_backup

# This script will:
# 1. Execute the job management command
# 2. Show relevant Docker logs
# 3. Confirm job execution
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

### View Container Logs
```bash
# Real-time logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100

# Filter for specific job
docker-compose logs | grep "google_drive_backup"
```

### Check Job Execution History
```bash
# Create a monitoring script
cat > check_jobs.py << 'EOF'
import sqlite3
from datetime import datetime

conn = sqlite3.connect('orchestrator.db')
cursor = conn.execute('''
    SELECT timestamp, level, message
    FROM logs
    WHERE message LIKE '%Job%'
    ORDER BY timestamp DESC
    LIMIT 20
''')

for row in cursor:
    time = datetime.fromtimestamp(row[0]).strftime('%Y-%m-%d %H:%M:%S')
    print(f"{time} [{row[1]}] {row[2]}")

conn.close()
EOF

python3 check_jobs.py
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
# Check if job is enabled
python3 manage_jobs.py list

# Check device tags match job requirements
docker-compose exec orchestrator env | grep DEVICE_TAGS

# Force trigger a job
python3 manage_jobs.py trigger <job_name>
```

### Database Issues
```bash
# Backup database
cp orchestrator.db orchestrator.db.backup

# Check database integrity
sqlite3 orchestrator.db "PRAGMA integrity_check;"

# Reset job status
sqlite3 orchestrator.db "DELETE FROM jobs WHERE job_name='<job_name>';"
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

The Google Drive backup job automatically backs up the database:

```bash
# Trigger manual backup
python3 manage_jobs.py trigger google_drive_backup

# Check backup status
docker-compose logs | grep "Backup completed"

# Restore from backup
cp /path/to/backup/orchestrator_YYYYMMDD_HHMMSS.db orchestrator.db
docker-compose restart
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