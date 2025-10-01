#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import requests, aios_db
from bs4 import BeautifulSoup
from datetime import datetime
aios_db.write("scraper", {"urls": ["https://news.ycombinator.com"]})
config = aios_db.read("scraper")
def scrape_url(url):
    soup = BeautifulSoup(requests.get(url).text, 'html.parser')
    return {"url": url, "title": {True: "No title", False: soup.title.string}[soup.title == None], "time": datetime.now().isoformat()}
def print_result(r):
    print(f"{r['url']}: {r['title']}")
results = list(map(scrape_url, config.get("urls", [])))
aios_db.write("scraper_results", results)
list(map(print_result, results))