#!/usr/bin/env python3
import json
import sqlite3
import hashlib
import argparse
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

class WebScraper:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.aios_dir.mkdir(exist_ok=True)
        self.config_file = self.aios_dir / "scraper_config.json"
        self.data_dir = self.aios_dir / "scraped_data"
        self.data_dir.mkdir(exist_ok=True)
        self.events_db = self.aios_dir / "events.db"
        self.init_db()
        self.load_config()

    def init_db(self):
        conn = sqlite3.connect(self.events_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY,
                source TEXT, target TEXT, type TEXT, data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_by TEXT
            )
        """)
        conn.close()

    def emit_event(self, event_type, data):
        conn = sqlite3.connect(self.events_db)
        conn.execute(
            "INSERT INTO events(source, target, type, data) VALUES (?, ?, ?, ?)",
            ("web_scraper", "ALL", event_type, json.dumps(data))
        )
        conn.commit()
        conn.close()

    def load_config(self):
        if not self.config_file.exists():
            default_config = {
                "sites": [
                    {"url": "https://news.ycombinator.com", "selector": ".titleline", "check_interval": 3600},
                    {"url": "https://example.com", "selector": "h1", "check_interval": 7200}
                ]
            }
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)

        with open(self.config_file) as f:
            self.config = json.load(f)

    def get_content_hash(self, content):
        return hashlib.md5(content.encode()).hexdigest()

    def scrape_site(self, site_config):
        url = site_config['url']
        selector = site_config.get('selector', 'body')

        try:
            response = requests.get(url, timeout=10, headers={'User-Agent': 'AIOS Scraper 1.0'})
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            elements = soup.select(selector)

            content = []
            for elem in elements[:10]:  # Limit to 10 items
                text = elem.get_text(strip=True)
                if text:
                    content.append(text)

            return {'status': 'success', 'content': content, 'timestamp': datetime.now().isoformat()}

        except Exception as e:
            return {'status': 'error', 'error': str(e), 'timestamp': datetime.now().isoformat()}

    def run_scraper(self):
        print("\n🕷️ Running web scraper...")
        changes_detected = 0

        for site in self.config['sites']:
            url = site['url']
            domain = url.replace('https://', '').replace('http://', '').replace('/', '_')
            data_file = self.data_dir / f"{domain}.json"

            print(f"📡 Scraping {url}...")
            result = self.scrape_site(site)

            # Load previous data
            previous_hash = None
            if data_file.exists():
                with open(data_file) as f:
                    previous = json.load(f)
                    if 'content' in previous:
                        previous_hash = self.get_content_hash(json.dumps(previous['content']))

            # Check for changes
            if result['status'] == 'success':
                current_hash = self.get_content_hash(json.dumps(result['content']))

                if previous_hash != current_hash:
                    changes_detected += 1
                    print(f"  ✓ Changes detected!")
                    self.emit_event('content_changed', {'url': url, 'items': len(result['content'])})
                else:
                    print(f"  - No changes")

                # Save new data
                with open(data_file, 'w') as f:
                    json.dump(result, f, indent=2)
            else:
                print(f"  ✗ Error: {result.get('error', 'Unknown')}")

        print(f"\n📊 Summary: {changes_detected} sites with changes")

    def add_site(self, url, selector=None):
        self.load_config()
        new_site = {
            'url': url,
            'selector': selector or 'h1, h2, p',
            'check_interval': 3600
        }

        # Check if already exists
        for site in self.config['sites']:
            if site['url'] == url:
                print(f"Site {url} already exists")
                return

        self.config['sites'].append(new_site)
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)

        print(f"✅ Added site: {url}")
        print(f"   Selector: {new_site['selector']}")

    def list_sites(self):
        print("\n📋 Monitored Sites:")
        for i, site in enumerate(self.config['sites'], 1):
            print(f"{i}. {site['url']}")
            print(f"   Selector: {site['selector']}")
            print(f"   Interval: {site['check_interval']}s")

def main():
    parser = argparse.ArgumentParser(description='Web Scraper')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('run', help='Run scraper now')

    add_parser = subparsers.add_parser('add-site', help='Add site to monitor')
    add_parser.add_argument('url', help='Site URL')
    add_parser.add_argument('--selector', help='CSS selector', default='h1, h2, p')

    subparsers.add_parser('list', help='List monitored sites')

    args = parser.parse_args()
    scraper = WebScraper()

    if args.command == 'run':
        scraper.run_scraper()
    elif args.command == 'add-site':
        scraper.add_site(args.url, args.selector)
    elif args.command == 'list':
        scraper.list_sites()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()