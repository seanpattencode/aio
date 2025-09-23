#!/usr/bin/env python3
import signal
import time
import logging
from systemd import journal

# Configure journal logging
journal_handler = journal.JournalHandler(SYSLOG_IDENTIFIER='my_service')
journal_handler.setLevel(logging.INFO)
logging.root.addHandler(journal_handler)
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

class ServiceManager:
    def __init__(self):
        self.shutdown = False
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        
    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully")
        self.shutdown = True
        
    def run(self):
        logger.info("Starting the service")
        total_duration = 0
        
        while not self.shutdown:
            # Your service logic here
            time.sleep(60)
            total_duration += 60
            logger.info(f"Total duration: {total_duration}")
            
            # Simulate crash after 5 minutes for demo
            if total_duration >= 300:
                raise Exception("Service crash simulation")

if __name__ == "__main__":
    service = ServiceManager()
    try:
        service.run()
    except Exception as e:
        logger.error(f"Service crashed: {e}")
        exit(1)