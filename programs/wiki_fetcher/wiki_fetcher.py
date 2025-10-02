#!/usr/bin/env python3
import sys, json, urllib.request
sys.path.append("/home/seanpatten/projects/AIOS/core")
import aios_db
data = json.loads(urllib.request.urlopen(urllib.request.Request("https://en.wikipedia.org/api/rest_v1/page/random/summary", headers={'User-Agent': 'Mozilla/5.0'})).read().decode())
output, job_id = f"{data.get('title', 'Unknown')}: {data.get('extract', 'No extract available')[:200]}...", (sys.argv + [None])[1]
(job_id and aios_db.execute("jobs", "UPDATE jobs SET output=?, status='review' WHERE id=?", (output, job_id))) or print(output)