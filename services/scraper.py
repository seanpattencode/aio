#!/usr/bin/env python3
import sys, requests
[sys.path.append(p) for p in ["/home/seanpatten/projects/AIOS/core", "/home/seanpatten/projects/AIOS"]]
import aios_db
from bs4 import BeautifulSoup
from datetime import datetime
aios_db.write("scraper", {"urls": ["https://news.ycombinator.com"]})
results = [{"url": u, "title": (s := BeautifulSoup(requests.get(u, timeout=0.01).text, 'html.parser')).title.string or "No title", "time": datetime.now().isoformat()} for u in aios_db.read("scraper").get("urls", [])]
[aios_db.write("scraper_results", results), list(map(lambda r: print(f"{r['url']}: {r['title']}"), results))]