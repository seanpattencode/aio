#!/usr/bin/env python3
"""Simple test service for AIOSE demonstration"""
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

def main():
    logging.info("Test service started")
    counter = 0
    while True:
        counter += 1
        logging.info(f"Service heartbeat #{counter} at {datetime.now()}")
        time.sleep(10)  # Heartbeat every 10 seconds

if __name__ == "__main__":
    main()