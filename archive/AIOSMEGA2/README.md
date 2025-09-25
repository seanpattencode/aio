# AIOS - AI Operating System

## Setup
```bash
# Install dependencies
pip install flask requests beautifulsoup4

# Initialize AIOS
python setup_aios.py
```

## Components

### 1. smart_todo.py - Task management
```bash
python smart_todo.py list
python smart_todo.py add "Task description" -p high
python smart_todo.py done 1
python smart_todo.py skip 2
```

### 2. daily_planner.py - AI daily planning (requires OpenAI API)
```bash
export OPENAI_API_KEY='your-key'
python daily_planner.py plan
python daily_planner.py energy low
```

### 3. parallel_builder.py - Build multiple components
```bash
python parallel_builder.py build comp1 comp2
python parallel_builder.py status
```

### 4. service_manager.py - Background services
```bash
python service_manager.py status
python service_manager.py start backup
python service_manager.py stop backup
```

### 5. backup_local.py - Local backups
```bash
python backup_local.py now
python backup_local.py list
python backup_local.py restore 2025-01-23
```

### 6. web_ui.py - Web interface
```bash
python web_ui.py
# Visit http://localhost:8080
```

### 7. idea_ranker.py - Idea prioritization
```bash
python idea_ranker.py add "New idea"
python idea_ranker.py rank
python idea_ranker.py pick --easy
```

### 8. llm_swarm.py - Multi-LLM queries (requires API keys)
```bash
export OPENAI_API_KEY='your-key'
export ANTHROPIC_API_KEY='your-key'
export GOOGLE_API_KEY='your-key'
python llm_swarm.py ask "Your question"
```

### 9. web_scraper.py - Website monitoring
```bash
python web_scraper.py run
python web_scraper.py add-site https://example.com
python web_scraper.py list
```

### 10. backup_gdrive.py - Google Drive sync (requires credentials)
```bash
export GOOGLE_APPLICATION_CREDENTIALS='path/to/service-account.json'
python backup_gdrive.py sync
python backup_gdrive.py restore
```

## Data Location
All data stored in `~/.aios/`