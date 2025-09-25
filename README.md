./setup.py all - Complete initial setup
./setup.py minimal - Quick setup only
./setup.py check - Verify installation status
./setup.py reset - Clear all configuration

./smart_todo.py list - Show all tasks
./smart_todo.py add <task> - Add new task
./smart_todo.py done <id> - Mark task complete
./smart_todo.py skip <id> - Skip critical task

./daily_planner.py plan - Generate daily schedule
./daily_planner.py replan - Adjust for changes
./daily_planner.py goals - Display weekly goals
./daily_planner.py status - Show current plan

./parallel_builder.py build <names> - Build components concurrently
./parallel_builder.py status - Show build progress
./parallel_builder.py list - List built components
./parallel_builder.py clean - Remove all builds

./service_manager.py start <name> - Start systemd service
./service_manager.py stop <name> - Stop running service
./service_manager.py status - Check service states
./service_manager.py list - Show available services

./backup_local.py backup - Create daily backup
./backup_local.py restore <date> - Restore from date
./backup_local.py list - Show backup history
./backup_local.py clean - Delete all backups

./web_ui.py start - Launch web interface
./web_ui.py stop - Shutdown web server
./web_ui.py status - Check server status
./web_ui.py restart - Restart web service

./idea_ranker.py rank - Score all ideas
./idea_ranker.py add <idea> - Add new idea
./idea_ranker.py list - Show ranked ideas
./idea_ranker.py pick - Suggest easy wins

./llm_swarm.py ask <question> - Query multiple LLMs
./llm_swarm.py list - Show cached queries
./llm_swarm.py clear - Clear response cache
./llm_swarm.py stats - Display usage statistics

./web_scraper.py scrape - Check all sites
./web_scraper.py add <url> - Monitor new site
./web_scraper.py list - Show monitored sites
./web_scraper.py status - Display scraper status

./backup_gdrive.py sync - Upload to Drive
./backup_gdrive.py restore - Download from Drive
./backup_gdrive.py list - Show synced files
./backup_gdrive.py status - Check sync status

./aios start SERVICE - Start service
./aios status - Show running services
./aios web - Launch web interface
./aios ai PROMPT - Natural language control