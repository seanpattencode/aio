#!/usr/bin/env python3
from http.server import ThreadingHTTPServer as HTTPServer, BaseHTTPRequestHandler
import subprocess, json, os, urllib.request, threading

INSTALL_LOG = {'output': '', 'running': False, 'ver': 0, 'app_id': ''}

# Pre-build icon index at startup for fast lookup
ICON_DIRS = ['/usr/share/icons/hicolor', '/var/lib/flatpak/exports/share/icons/hicolor',
             os.path.expanduser('~/.local/share/flatpak/exports/share/icons/hicolor'),
             os.path.expanduser('~/.local/share/icons/hicolor')]
SIZES = ['scalable', '512x512', '256x256', '128x128', '96x96', '64x64', '48x48']
ICON_INDEX = {}

def build_icon_index():
    for d in ICON_DIRS:
        for sz in SIZES:
            p = f"{d}/{sz}/apps"
            if os.path.isdir(p):
                for f in os.listdir(p):
                    name = os.path.splitext(f)[0]
                    if name not in ICON_INDEX:
                        ICON_INDEX[name] = f"{p}/{f}"

def find_icon(name):
    if name in ICON_INDEX: return ICON_INDEX[name]
    # Fallback: check pixmaps
    for ext in ['png', 'svg', 'xpm']:
        p = f"/usr/share/pixmaps/{name}.{ext}"
        if os.path.exists(p): return p
    return None

build_icon_index()
APP_VER, APP_EVT = [0], threading.Event()
def watch_apps():
    import ctypes; libc = ctypes.CDLL('libc.so.6'); fd = libc.inotify_init(); dirs = [os.path.expanduser('~/.local/share/applications')] + [f"{d}/{sz}/apps" for d in ICON_DIRS for sz in SIZES]
    for p in dirs:
        if os.path.isdir(p): libc.inotify_add_watch(fd, p.encode(), 0x300)
    while os.read(fd, 4096): build_icon_index(); APP_VER[0] += 1; APP_EVT.set()
threading.Thread(target=watch_apps, daemon=True).start()

def run_install(app_id):
    INSTALL_LOG['output'], INSTALL_LOG['running'], INSTALL_LOG['app_id'] = f'$ flatpak install -y --user {app_id}\n', True, app_id
    INSTALL_LOG['ver'] += 1
    proc = subprocess.Popen(['flatpak', 'install', '-y', '--user', app_id], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout: INSTALL_LOG['output'] += line; INSTALL_LOG['ver'] += 1
    proc.wait()
    INSTALL_LOG['output'] += f'\n[Exit code: {proc.returncode}]\n'
    INSTALL_LOG['running'] = False
    INSTALL_LOG['ver'] += 1

def run_apt_install(pkg):
    INSTALL_LOG['output'], INSTALL_LOG['running'], INSTALL_LOG['app_id'] = f'$ pkexec apt install -y {pkg}\n', True, pkg
    INSTALL_LOG['ver'] += 1
    proc = subprocess.Popen(['pkexec', 'apt', 'install', '-y', pkg], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout: INSTALL_LOG['output'] += line; INSTALL_LOG['ver'] += 1
    proc.wait()
    INSTALL_LOG['output'] += f'\n[Exit code: {proc.returncode}]\n'
    INSTALL_LOG['running'] = False
    INSTALL_LOG['ver'] += 1

def get_apt_package(app_id):
    """Map desktop file ID to apt package name"""
    try: return subprocess.check_output(['dpkg', '-S', f'/usr/share/applications/{app_id}.desktop'], text=True, stderr=subprocess.DEVNULL).split(':')[0]
    except: return app_id  # fallback to app_id if not found

def run_apt_uninstall(app_id):
    pkg = get_apt_package(app_id)
    INSTALL_LOG['output'], INSTALL_LOG['running'], INSTALL_LOG['app_id'] = f'$ pkexec apt remove -y {pkg}\n', True, app_id
    INSTALL_LOG['ver'] += 1
    proc = subprocess.Popen(['pkexec', 'apt', 'remove', '-y', pkg], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout: INSTALL_LOG['output'] += line; INSTALL_LOG['ver'] += 1
    proc.wait()
    INSTALL_LOG['output'] += f'\n[Exit code: {proc.returncode}]\n'
    INSTALL_LOG['running'] = False
    INSTALL_LOG['ver'] += 1

def run_snap_install(snap):
    INSTALL_LOG['output'], INSTALL_LOG['running'], INSTALL_LOG['app_id'] = f'$ pkexec snap install {snap}\n', True, snap
    INSTALL_LOG['ver'] += 1
    proc = subprocess.Popen(['pkexec', 'snap', 'install', snap], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout: INSTALL_LOG['output'] += line; INSTALL_LOG['ver'] += 1
    proc.wait()
    INSTALL_LOG['output'] += f'\n[Exit code: {proc.returncode}]\n'
    INSTALL_LOG['running'] = False
    INSTALL_LOG['ver'] += 1

def run_snap_uninstall(snap):
    INSTALL_LOG['output'], INSTALL_LOG['running'], INSTALL_LOG['app_id'] = f'$ pkexec snap remove {snap}\n', True, snap
    INSTALL_LOG['ver'] += 1
    proc = subprocess.Popen(['pkexec', 'snap', 'remove', snap], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout: INSTALL_LOG['output'] += line; INSTALL_LOG['ver'] += 1
    proc.wait()
    INSTALL_LOG['output'] += f'\n[Exit code: {proc.returncode}]\n'
    INSTALL_LOG['running'] = False
    INSTALL_LOG['ver'] += 1

def search_flathub(query):
    req = urllib.request.Request('https://flathub.org/api/v2/search', json.dumps({'query': query}).encode(), {'Content-Type': 'application/json'})
    data = json.loads(urllib.request.urlopen(req, timeout=5).read())
    return [{'id': h['app_id'], 'name': h['name'], 'summary': h.get('summary',''), 'icon': h.get('icon',''), 'downloads': h.get('installs_last_month',0), 'source': 'flatpak'} for h in data.get('hits', [])[:20]]

def get_installed_apt():
    try: return set(subprocess.check_output(['dpkg-query', '-W', '-f=${Package}\n'], text=True, timeout=5).strip().split('\n'))
    except: return set()

def search_apt(query):
    installed, q = get_installed_apt(), query.lower()
    try:
        out = subprocess.check_output(['apt-cache', 'search', query], text=True, timeout=5)
        pkgs = {line.split(' - ')[0]: line.split(' - ', 1)[1] if ' - ' in line else '' for line in out.strip().split('\n') if line}
        # Add exact match if installed but not in search (happens with transitional packages)
        if q in installed and q not in pkgs:
            pkgs[q] = subprocess.check_output(['dpkg-query', '-W', '-f=${Description}', q], text=True, timeout=2).split('\n')[0] if q in installed else ''
        results = []
        for pkg, desc in pkgs.items():
            is_installed = pkg in installed
            results.append({'id': pkg, 'name': pkg, 'summary': f"{'✓ Installed - ' if is_installed else ''}{desc}", 'icon': '', 'downloads': 0, 'source': 'apt', 'installed': is_installed})
        return sorted(results, key=lambda x: (-x['installed'], x['id']))[:15]
    except: return []

def search_local(query):
    q = query.lower()
    return [{'id': a['id'], 'name': a['name'], 'summary': '✓ Installed (source build)', 'icon': '', 'downloads': 0, 'source': 'local', 'installed': True} for a in get_desktop_apps('/usr/local/share/applications', 'local') if q in a['name'].lower() or q in a['id'].lower()]

def search_snap(query):
    installed = {line.split()[0] for line in subprocess.check_output(['snap', 'list'], text=True).strip().split('\n')[1:] if line.split()}
    try:
        out = subprocess.check_output(['snap', 'find', query], text=True, timeout=10)
        results = []
        for line in out.strip().split('\n')[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 5:  # Name Version Publisher Notes Summary...
                name, desc = parts[0], ' '.join(parts[4:])  # skip name/ver/pub/notes
                is_installed = name in installed
                results.append({'id': name, 'name': name, 'summary': f"{'✓ Installed - ' if is_installed else ''}{desc}", 'icon': '', 'downloads': 0, 'source': 'snap', 'installed': is_installed})
        return sorted(results, key=lambda x: -x['installed'])[:15]
    except: return []

def search_all(query, sources=None):
    results = []
    if not sources or 'local' in sources: results += search_local(query)
    if not sources or 'apt' in sources: results += search_apt(query)
    if not sources or 'snap' in sources: results += search_snap(query)
    if not sources or 'flatpak' in sources: results += search_flathub(query)
    seen = set()
    # Dedupe by id+source so same app from different sources both show
    return [r for r in results if not ((r['id'], r['source']) in seen or seen.add((r['id'], r['source'])))][:40]

def get_popular_flathub():
    data = json.loads(urllib.request.urlopen('https://flathub.org/api/v2/collection/popular', timeout=10).read())
    return [{'id': h['app_id'], 'name': h['name'], 'summary': h.get('summary',''), 'icon': h.get('icon',''), 'downloads': h.get('installs_last_month',0)} for h in data.get('hits', [])[:24]]

def get_pwas():
    apps, desktop_dir = [], os.path.expanduser('~/.local/share/applications')
    for f in os.listdir(desktop_dir) if os.path.isdir(desktop_dir) else []:
        if f.startswith('chrome-') and f.endswith('.desktop'):
            try:
                content = open(f"{desktop_dir}/{f}").read()
                name = next((l.split('=',1)[1] for l in content.split('\n') if l.startswith('Name=')), None)
                icon_id = f[:-8]  # remove .desktop
                if name and icon_id in ICON_INDEX: apps.append({'name': name, 'id': icon_id, 'source': 'pwa', 'icon': True})
            except: pass
    return apps

def get_desktop_apps(desktop_dir, source):
    apps = []
    for f in os.listdir(desktop_dir) if os.path.isdir(desktop_dir) else []:
        if f.endswith('.desktop') and not f.startswith('chrome-'):
            try:
                content = open(f"{desktop_dir}/{f}").read()
                if 'NoDisplay=true' in content: continue
                name = next((l.split('=',1)[1] for l in content.split('\n') if l.startswith('Name=') and '=' in l), None)
                app_id = f[:-8]
                if name and app_id in ICON_INDEX:
                    apps.append({'name': name, 'id': app_id, 'source': source, 'icon': True})
            except: pass
    return apps

def get_installed_apps(show_all=False):
    apps = get_pwas()
    apps += get_desktop_apps('/usr/local/share/applications', 'local')
    apps += get_desktop_apps('/usr/share/applications', 'apt')
    # Flatpak apps (may override apt entries with same id)
    try:
        out = subprocess.check_output(['flatpak', 'list', '--app', '--columns=name,application'], text=True)
        flatpak_ids = set()
        for line in out.strip().split('\n'):
            if '\t' in line:
                name, app_id = line.split('\t', 1)
                flatpak_ids.add(app_id)
                apps.append({'name': name, 'id': app_id, 'source': 'flatpak', 'icon': app_id in ICON_INDEX})
        # Remove apt entries that are actually flatpak
        apps = [a for a in apps if not (a['source'] == 'apt' and a['id'] in flatpak_ids)]
    except: pass
    # Snap apps
    try:
        snap_ids = set()
        for line in subprocess.check_output(['snap', 'list'], text=True).strip().split('\n')[1:]:
            parts = line.split()
            if parts:
                name = parts[0]
                snap_ids.add(name)
                apps.append({'name': name.title(), 'id': name, 'source': 'snap', 'icon': name in ICON_INDEX})
        apps = [a for a in apps if not (a['source'] == 'apt' and a['id'] in snap_ids)]
    except: pass
    # Raw dpkg packages (only if show_all)
    if show_all:
        seen = {a['id'] for a in apps}
        try:
            for pkg in subprocess.check_output(['dpkg-query', '-W', '-f=${Package}\n'], text=True).strip().split('\n'):
                if pkg not in seen: apps.append({'name': pkg, 'id': pkg, 'source': 'apt', 'icon': False})
        except: pass
    return apps

HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Universal App Store</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #f1f1f1; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
        .app-card { transition: transform 0.2s, box-shadow 0.2s; }
        .app-card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); }
        @keyframes shimmer { 0% { background-position: -1000px 0; } 100% { background-position: 1000px 0; } }
        .loading { animation: shimmer 2s infinite linear; background: linear-gradient(to right, #eff6ff 4%, #e0f2fe 25%, #eff6ff 36%); background-size: 1000px 100%; }
        .platform-badge { font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
    </style>
</head>
<body class="bg-gray-50 text-gray-800 font-sans h-screen flex flex-col overflow-hidden">
    <header class="bg-white border-b border-gray-200 z-10 flex-none relative">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3 cursor-pointer" onclick="resetView()">
                <div class="bg-blue-600 text-white p-2 rounded-xl shadow-sm"><i class="fa-solid fa-cube text-xl"></i></div>
                <h1 class="text-xl font-bold tracking-tight text-gray-900">OmniStore</h1>
            </div>
            <div class="flex-1 max-w-2xl mx-8 hidden sm:flex gap-2">
                <div class="relative group flex-1">
                    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <i class="fa-solid fa-search text-gray-400 group-focus-within:text-blue-500 transition-colors"></i>
                    </div>
                    <input type="text" id="searchInput" class="block w-full pl-10 pr-3 py-2 border border-gray-200 rounded-lg leading-5 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:bg-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 sm:text-sm transition-all shadow-inner" placeholder="Search apps, tools, and games...">
                </div>
            </div>
            <div class="flex items-center gap-3">
                <div id="connStatus" class="flex items-center gap-1.5 text-xs text-gray-400"><span class="w-2 h-2 rounded-full bg-gray-400"></span><span>...</span></div>
            </div>
        </div>
    </header>
    <div class="flex flex-1 overflow-hidden max-w-7xl mx-auto w-full">
        <aside class="w-64 hidden lg:flex flex-col border-r border-gray-200 bg-white py-6">
            <nav class="space-y-1 px-4">
                <button onclick="setSidebarView('all')" id="nav-all" class="nav-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium bg-blue-50 text-blue-700 flex items-center gap-3"><i class="fa-solid fa-fire w-5 text-center text-orange-500"></i> Popular</button>
                <button onclick="setSidebarView('installed')" id="nav-installed" class="nav-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 flex items-center gap-3"><i class="fa-solid fa-hard-drive w-5 text-center"></i> Installed</button>
            </nav>
        </aside>
        <main class="flex-1 overflow-y-auto p-4 sm:p-8 scroll-smooth" id="mainContainer">
            <div id="featuredSection" class="mb-10">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-2xl font-bold text-gray-900" id="heroTitle">Featured Apps</h2>
                    <div class="flex gap-2">
                        <button class="p-2 rounded-full hover:bg-gray-100 text-gray-400"><i class="fa-solid fa-chevron-left"></i></button>
                        <button class="p-2 rounded-full hover:bg-gray-100 text-gray-400"><i class="fa-solid fa-chevron-right"></i></button>
                    </div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6" id="heroGrid"></div>
            </div>
            <div class="mb-4">
                <h2 id="sectionTitle" class="text-xl font-bold text-gray-900 mb-4">Recommended for You</h2>
                <div id="appGrid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6"></div>
            </div>
             <div id="installedSection" class="hidden">
                 <div class="flex items-center justify-between mb-4 gap-4 flex-wrap">
                     <h2 class="text-xl font-bold text-gray-900">Installed Apps</h2>
                     <div class="flex gap-1" id="sourceFilters">
                        <button onclick="filterBySource('all')" class="px-3 py-1 text-xs font-medium rounded-full bg-gray-900 text-white">All</button>
                        <button onclick="filterBySource('pwa')" class="px-3 py-1 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600 hover:bg-purple-50 hover:text-purple-700">PWA</button>
                        <button onclick="filterBySource('flatpak')" class="px-3 py-1 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600 hover:bg-blue-50 hover:text-blue-700">Flatpak</button>
                        <button onclick="filterBySource('local')" class="px-3 py-1 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600 hover:bg-green-50 hover:text-green-700">Local</button>
                        <button onclick="filterBySource('snap')" class="px-3 py-1 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600 hover:bg-orange-50 hover:text-orange-700">Snap</button>
                        <button onclick="filterBySource('apt')" class="px-3 py-1 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600 hover:bg-red-50 hover:text-red-700">Apt</button>
                     </div>
                     <input type="text" id="installedSearch" oninput="filterInstalled()" placeholder="Search..." class="px-3 py-1.5 text-sm border border-gray-200 rounded-lg w-48 focus:outline-none focus:border-blue-500">
                     <button id="showAllToggle" onclick="toggleShowAll()" class="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 whitespace-nowrap">Show All System Packages</button>
                 </div>
                 <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                     <table class="min-w-full divide-y divide-gray-200">
                         <thead class="bg-gray-50">
                             <tr>
                                 <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">App</th>
                                 <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Platform</th>
                                 <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Downloads</th>
                                 <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                             </tr>
                         </thead>
                         <tbody class="bg-white divide-y divide-gray-200" id="installedTableBody"></tbody>
                     </table>
                 </div>
             </div>
        </main>
    </div>
    <!-- Terminal Panel -->
    <div id="termPanel" class="fixed bottom-0 left-0 right-0 bg-gray-900 text-green-400 font-mono text-xs transition-all duration-300 z-50" style="height:0">
        <div onclick="toggleTerm()" class="flex items-center justify-between px-4 py-2 bg-gray-800 cursor-pointer border-t border-gray-700">
            <span><i class="fa-solid fa-terminal mr-2"></i>Terminal <span id="termStatus" class="text-gray-500"></span></span>
            <i id="termArrow" class="fa-solid fa-chevron-up"></i>
        </div>
        <pre id="termOutput" class="p-4 overflow-auto" style="height:calc(100% - 36px)"></pre>
    </div>
    <script>
        let termOpen = false, evtSrc = null;
        function toggleTerm() { termOpen = !termOpen; document.getElementById('termPanel').style.height = termOpen ? '250px' : '0'; document.getElementById('termArrow').className = termOpen ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-up'; }
        function doInstall(appId, btn) {
            fetch('/install/' + appId); btn.innerText = 'Installing...'; btn.disabled = true; btn.className = 'w-full py-2 rounded-lg font-bold text-sm bg-gray-400 text-white';
            termOpen = true; document.getElementById('termPanel').style.height = '250px'; document.getElementById('termArrow').className = 'fa-solid fa-chevron-down';
            if(evtSrc) evtSrc.close();
            evtSrc = new EventSource('/api/events');
            evtSrc.onmessage = (e) => { const d = JSON.parse(e.data); document.getElementById('termOutput').innerText = d.output; document.getElementById('termStatus').innerText = d.running ? '(running...)' : '(done)'; document.getElementById('termOutput').scrollTop = 999999; if(!d.running) { evtSrc.close(); btn.innerText = 'Open'; btn.disabled = false; btn.className = 'w-full py-2 rounded-lg font-bold text-sm bg-green-600 text-white hover:bg-green-700'; btn.onclick = () => fetch('/launch/' + appId); }};
        }
        function doAptInstall(pkg, btn) {
            fetch('/install-apt/' + pkg); btn.innerText = 'Installing...'; btn.disabled = true; btn.className = 'w-full py-2 rounded-lg font-bold text-sm bg-gray-400 text-white';
            termOpen = true; document.getElementById('termPanel').style.height = '250px'; document.getElementById('termArrow').className = 'fa-solid fa-chevron-down';
            if(evtSrc) evtSrc.close();
            evtSrc = new EventSource('/api/events');
            evtSrc.onmessage = (e) => { const d = JSON.parse(e.data); document.getElementById('termOutput').innerText = d.output; document.getElementById('termStatus').innerText = d.running ? '(running...)' : '(done)'; document.getElementById('termOutput').scrollTop = 999999; if(!d.running) { evtSrc.close(); btn.innerText = 'Installed'; btn.disabled = false; btn.className = 'w-full py-2 rounded-lg font-bold text-sm bg-green-600 text-white'; }};
        }
        let apps = [];
        let currentFilterState = { search: '', sortBy: 'popular' };
        let showAllPackages = false;
        let installedAppsCache = [];
        let connected = false;
        function setConnected(c) { connected = c; const el = document.getElementById('connStatus'); el.className = 'flex items-center gap-1.5 text-xs ' + (c ? 'text-green-600' : 'text-red-500'); el.innerHTML = `<span class="w-2 h-2 rounded-full ${c ? 'bg-green-500' : 'bg-red-500'}"></span><span>${c ? 'Live' : 'Offline'}</span>`; }
        document.addEventListener('DOMContentLoaded', async () => {
            try { apps = await (await fetch('/api/popular')).json(); setConnected(true); } catch(e) { setConnected(false); }
            renderGrid(apps); renderHero(apps);
            document.getElementById('searchInput').addEventListener('input', (e) => { currentFilterState.search = e.target.value; renderGrid(apps.filter(a => a.name.toLowerCase().includes(e.target.value.toLowerCase()))); });
            document.getElementById('searchInput').addEventListener('keydown', (e) => { if(e.key==='Enter' && e.target.value.length > 1) searchFlathub(e.target.value); });
            const es = new EventSource('/api/app-events'); es.onmessage = () => { setConnected(true); if(!document.getElementById('installedSection').classList.contains('hidden')) showInstalledSection(); }; es.onerror = () => setConnected(false); es.onopen = () => setConnected(true);
        });
        async function doUninstall(appId, source, btn) {
            btn.innerText = 'Removing...'; btn.disabled = true;
            const res = await fetch('/uninstall/' + source + '/' + encodeURIComponent(appId));
            const data = await res.json();
            if(data.async) {
                if(evtSrc) evtSrc.close();
                evtSrc = new EventSource('/api/events');
                evtSrc.onmessage = (e) => { const d = JSON.parse(e.data); document.getElementById('termOutput').innerText = d.output; document.getElementById('termStatus').innerText = d.running ? '(running...)' : '(done)'; if(!d.running) { evtSrc.close(); const ok = d.output.includes('Exit code: 0'); if(ok) { btn.innerText = 'Removed'; setTimeout(() => showInstalledSection(), 500); } else { btn.innerText = 'Failed'; btn.disabled = false; termOpen = true; document.getElementById('termPanel').style.height = '250px'; }}};
            } else if(data.ok) { btn.innerText = 'Removed'; setTimeout(() => showInstalledSection(), 500); }
            else { btn.innerText = 'Failed'; btn.disabled = false; }
        }
        function setSidebarView(view) {
            document.querySelectorAll('.nav-btn').forEach(b => { b.classList.remove('bg-blue-50', 'text-blue-700'); b.classList.add('text-gray-600', 'hover:bg-gray-50'); });
            if(view === 'installed') { document.getElementById('nav-installed').classList.add('bg-blue-50', 'text-blue-700'); showInstalledSection(); return; }
            document.getElementById('installedSection').classList.add('hidden');
            document.getElementById('featuredSection').classList.remove('hidden');
            document.getElementById('appGrid').classList.remove('hidden');
            document.getElementById('nav-all').classList.add('bg-blue-50', 'text-blue-700');
            renderGrid(apps); renderHero(apps);
        }
        function formatDownloads(num) { if(num >= 1000000000) return (num/1000000000).toFixed(1) + 'B'; if(num >= 1000000) return (num/1000000).toFixed(0) + 'M'; if(num >= 1000) return (num/1000).toFixed(1) + 'K'; return num; }
        function renderHero(filteredApps) {
            const heroGrid = document.getElementById('heroGrid'); heroGrid.innerHTML = '';
            filteredApps.slice(0, 2).forEach((app, i) => {
                heroGrid.innerHTML += i === 0
                    ? `<div class="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl p-6 text-white shadow-lg cursor-pointer hover:shadow-xl" onclick="doInstall('${app.id}',this.querySelector('button'))"><div class="flex items-center gap-2 mb-2"><span class="px-2 py-0.5 rounded bg-white/20 text-xs font-semibold">#1 Popular</span><span class="px-2 py-0.5 rounded bg-white/20 text-xs font-semibold"><i class="fa-brands fa-linux"></i> Flatpak</span></div><h3 class="text-3xl font-bold mb-2">${app.name}</h3><p class="text-indigo-100 text-sm mb-4 line-clamp-2">${app.summary}</p><div class="flex items-center gap-4"><button class="bg-white text-indigo-600 px-6 py-2 rounded-lg font-bold text-sm">Install</button><span class="text-xs text-indigo-200">${formatDownloads(app.downloads)} Downloads</span></div></div>`
                    : `<div class="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm cursor-pointer hover:border-blue-300"><div class="flex items-start gap-4 mb-4"><img src="${app.icon}" class="w-16 h-16 rounded-2xl" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%236366f1%22 width=%2240%22 height=%2240%22 rx=%228%22/></svg>'"><div><h3 class="text-xl font-bold text-gray-900">${app.name}</h3><p class="text-gray-500 text-sm">${app.id}</p></div></div><p class="text-sm text-gray-600 mb-4 line-clamp-2">${app.summary}</p><div class="flex items-center justify-between border-t border-gray-100 pt-4"><span class="text-xs text-gray-400">${formatDownloads(app.downloads)} Downloads</span><button onclick="doInstall('${app.id}',this)" class="text-blue-600 font-bold text-sm">Install</button></div></div>`;
            });
        }
        function renderGrid(filteredApps) {
            document.getElementById('appGrid').innerHTML = filteredApps.map(app => `
                <div class="app-card bg-white rounded-xl p-5 border border-gray-100 shadow-sm flex flex-col h-full hover:border-blue-200">
                    <div class="flex items-start gap-3 mb-3">
                        <img src="${app.icon}" class="w-14 h-14 rounded-2xl" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%236366f1%22 width=%2240%22 height=%2240%22 rx=%228%22/></svg>'">
                        <div class="flex-1 min-w-0"><h3 class="font-bold text-gray-900 truncate">${app.name}</h3><p class="text-xs text-gray-500 truncate">${app.id}</p><span class="text-xs text-gray-400">${formatDownloads(app.downloads)} downloads</span></div>
                    </div>
                    <p class="text-sm text-gray-600 mb-4 line-clamp-2 flex-1">${app.summary}</p>
                    <button onclick="doInstall('${app.id}',this)" class="w-full py-2 rounded-lg font-bold text-sm bg-blue-600 text-white hover:bg-blue-700">Install</button>
                </div>`).join('');
        }
        async function showInstalledSection() {
            document.getElementById('featuredSection').classList.add('hidden'); document.getElementById('appGrid').classList.add('hidden'); document.getElementById('installedSection').classList.remove('hidden'); document.getElementById('sectionTitle').innerText = 'My Library';
            const btn = document.getElementById('showAllToggle');
            btn.innerText = showAllPackages ? 'Show Apps Only' : 'Show All System Packages';
            btn.className = showAllPackages ? 'px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap' : 'px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 whitespace-nowrap';
            document.getElementById('installedTableBody').innerHTML = '<tr><td colspan="4" class="px-6 py-4 text-center text-gray-400">Loading...</td></tr>';
            document.getElementById('installedSearch').value = '';
            const res = await fetch('/api/installed' + (showAllPackages ? '?all=1' : ''));
            installedAppsCache = await res.json();
            renderInstalledTable(installedAppsCache);
        }
        let installedSourceFilter = 'all';
        function filterBySource(src) {
            installedSourceFilter = src;
            document.querySelectorAll('#sourceFilters button').forEach((b,i) => { const active = (src==='all'&&i===0)||(src==='pwa'&&i===1)||(src==='flatpak'&&i===2)||(src==='local'&&i===3)||(src==='snap'&&i===4)||(src==='apt'&&i===5); b.className = active ? 'px-3 py-1 text-xs font-medium rounded-full bg-gray-900 text-white' : 'px-3 py-1 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600'; });
            filterInstalled();
        }
        function filterInstalled() { const q = document.getElementById('installedSearch').value.toLowerCase(); renderInstalledTable(installedAppsCache.filter(a => (installedSourceFilter==='all'||a.source===installedSourceFilter) && (!q||a.name.toLowerCase().includes(q)||a.id.toLowerCase().includes(q)))); }
        function renderInstalledTable(apps) {
            const srcStyle = { 'pwa': { bg: 'bg-purple-50', text: 'text-purple-700' }, 'flatpak': { bg: 'bg-blue-50', text: 'text-blue-700' }, 'apt': { bg: 'bg-red-50', text: 'text-red-700' }, 'local': { bg: 'bg-green-50', text: 'text-green-700' }, 'snap': { bg: 'bg-orange-50', text: 'text-orange-700' } };
            document.getElementById('installedTableBody').innerHTML = apps.slice(0,200).map(app => { const s = srcStyle[app.source] || srcStyle.apt; const iconHtml = app.icon ? `<img src="/icon/${app.id}" class="h-10 w-10 rounded-lg object-contain" onerror="this.outerHTML='<div class=\\'flex-shrink-0 h-10 w-10 bg-gray-400 rounded-lg flex items-center justify-center text-white\\'><i class=\\'fa-solid fa-cube\\'></i></div>'">` : `<div class="flex-shrink-0 h-10 w-10 bg-gray-400 rounded-lg flex items-center justify-center text-white"><i class="fa-solid fa-cube"></i></div>`; return `<tr><td class="px-6 py-4 whitespace-nowrap"><div class="flex items-center"><div class="flex-shrink-0">${iconHtml}</div><div class="ml-4"><div class="text-sm font-medium text-gray-900">${app.name}</div><div class="text-sm text-gray-500 truncate max-w-xs">${app.id}</div></div></div></td><td class="px-6 py-4 whitespace-nowrap"><span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${s.bg} ${s.text}">${app.source}</span></td><td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">-</td><td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium"><button onclick="fetch('/launch/'+encodeURIComponent('${app.id}'))" class="text-blue-600 hover:text-blue-800 font-medium mr-3">Open</button><button onclick="doUninstall('${app.id}','${app.source}',this)" class="text-gray-400 hover:text-red-600">${['pwa','flatpak','apt','snap'].includes(app.source)?'Uninstall':''}</button></td></tr>`; }).join('') + (apps.length > 200 ? `<tr><td colspan="4" class="px-6 py-4 text-center text-gray-400 text-sm">${apps.length - 200} more... (refine search)</td></tr>` : '');
        }
        function toggleShowAll() { showAllPackages = !showAllPackages; showInstalledSection(); }
        let searchQuery = '', searchSources = ['apt','snap','flatpak'];
        async function searchFlathub(q, sources) {
            if(q) searchQuery = q;
            if(sources) searchSources = sources;
            document.getElementById('featuredSection').classList.add('hidden'); document.getElementById('installedSection').classList.add('hidden'); document.getElementById('appGrid').classList.remove('hidden');
            document.getElementById('sectionTitle').innerHTML = `<div class="flex items-center gap-4 flex-wrap"><span>Results for "${searchQuery}"</span><div class="flex gap-1">${['apt','snap','flatpak'].map(s => `<button onclick="toggleSearchSource('${s}')" class="px-2 py-1 text-xs font-medium rounded ${searchSources.includes(s) ? (s==='apt'?'bg-red-600 text-white':s==='snap'?'bg-orange-500 text-white':'bg-blue-600 text-white') : 'bg-gray-200 text-gray-600'}">${s}</button>`).join('')}</div></div>`;
            const res = await fetch('/api/search?q=' + encodeURIComponent(searchQuery) + '&sources=' + searchSources.join(','));
            const apps = await res.json();
            const srcColor = {apt: 'bg-red-100 text-red-700', flatpak: 'bg-blue-100 text-blue-700', pwa: 'bg-purple-100 text-purple-700', local: 'bg-green-100 text-green-700', snap: 'bg-orange-100 text-orange-700'};
            document.getElementById('appGrid').innerHTML = apps.map(app => { const isInstalled = app.installed || app.summary.startsWith('✓'); return `<div class="app-card bg-white rounded-xl p-5 border border-gray-100 shadow-sm flex flex-col h-full hover:border-blue-200"><div class="flex items-start gap-3 mb-3">${app.icon ? `<img src="${app.icon.startsWith('http')?app.icon:'/icon/'+app.id}" class="w-14 h-14 rounded-2xl" onerror="this.outerHTML='<div class=\\'w-14 h-14 rounded-2xl bg-gray-200 flex items-center justify-center\\'><i class=\\'fa-solid fa-cube text-gray-400\\'></i></div>'">` : `<div class="w-14 h-14 rounded-2xl bg-gray-200 flex items-center justify-center"><i class="fa-solid fa-cube text-gray-400"></i></div>`}<div class="flex-1 min-w-0"><h3 class="font-bold text-gray-900 leading-tight truncate">${app.name}</h3><p class="text-xs text-gray-500 truncate">${app.id}</p><span class="text-xs px-1.5 py-0.5 rounded ${srcColor[app.source]||'bg-gray-100 text-gray-600'}">${app.source||'flatpak'}</span></div></div><p class="text-sm text-gray-600 mb-4 line-clamp-2 flex-1">${app.summary.replace('✓ Installed - ','')}</p><button onclick="${isInstalled ? `fetch('/launch/'+encodeURIComponent('${app.id}'))` : (app.source==='snap'?`doSnapInstall('${app.id}',this)`:app.source==='apt'?`doAptInstall('${app.id}',this)`:`doInstall('${app.id}',this)`)}" class="w-full py-2 rounded-lg font-bold text-sm ${isInstalled?'bg-green-600':'bg-blue-600'} text-white hover:opacity-90">${isInstalled?'Open':'Install'}</button></div>`; }).join('') || '<p class="text-gray-400 col-span-4">No results found</p>';
        }
        function toggleSearchSource(s) { searchSources = searchSources.includes(s) ? searchSources.filter(x=>x!==s) : [...searchSources,s]; if(searchSources.length) searchFlathub(); }
        function doSnapInstall(snap, btn) { fetch('/install-snap/' + snap); btn.innerText = 'Installing...'; btn.disabled = true; termOpen = true; document.getElementById('termPanel').style.height = '250px'; if(evtSrc) evtSrc.close(); evtSrc = new EventSource('/api/events'); evtSrc.onmessage = (e) => { const d = JSON.parse(e.data); document.getElementById('termOutput').innerText = d.output; document.getElementById('termStatus').innerText = d.running ? '(running...)' : '(done)'; document.getElementById('termOutput').scrollTop = 999999; if(!d.running) { evtSrc.close(); btn.innerText = 'Open'; btn.disabled = false; btn.className = 'w-full py-2 rounded-lg font-bold text-sm bg-green-600 text-white hover:bg-green-700'; btn.onclick = () => fetch('/launch/' + snap); }}; }
        function resetView() { setSidebarView('all'); }
    </script>
</body>
</html>'''

class Handler(BaseHTTPRequestHandler):
    def json(self, data, code=200): self.send_response(code); self.send_header('Content-type', 'application/json'); self.end_headers(); self.wfile.write(json.dumps(data).encode())
    def do_GET(self):
        if self.path.startswith('/api/installed'): return self.json(get_installed_apps('all=1' in self.path))
        elif self.path.startswith('/api/search?'):
            params = {k: v for k, v in [p.split('=') for p in self.path.split('?')[1].split('&') if '=' in p]}
            query = urllib.request.unquote(params.get('q', ''))
            sources = params.get('sources', '').split(',') if params.get('sources') else None
            return self.json(search_all(query, sources))
        elif self.path.startswith('/api/flathub?q='): return self.json(search_all(urllib.request.unquote(self.path[15:])))
        elif self.path == '/api/popular': return self.json(get_popular_flathub())
        elif self.path.startswith('/install/'): threading.Thread(target=run_install, args=(self.path[9:],), daemon=True).start(); self.send_response(204); self.end_headers()
        elif self.path.startswith('/install-apt/'): threading.Thread(target=run_apt_install, args=(self.path[13:],), daemon=True).start(); self.send_response(204); self.end_headers()
        elif self.path.startswith('/install-snap/'): threading.Thread(target=run_snap_install, args=(self.path[14:],), daemon=True).start(); self.send_response(204); self.end_headers()
        elif self.path == '/api/installlog': return self.json(INSTALL_LOG)
        elif self.path == '/api/app-events':
            self.send_response(200); self.send_header('Content-type', 'text/event-stream'); self.send_header('Cache-Control', 'no-cache'); self.end_headers(); v = APP_VER[0]
            while True:
                APP_EVT.wait(30); APP_EVT.clear()
                if APP_VER[0] != v: v = APP_VER[0]; self.wfile.write(b"data: r\n\n"); self.wfile.flush()
        elif self.path == '/api/events':
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            last_ver = 0
            while True:
                if INSTALL_LOG['ver'] != last_ver:
                    last_ver = INSTALL_LOG['ver']
                    self.wfile.write(f"data: {json.dumps(INSTALL_LOG)}\n\n".encode())
                    self.wfile.flush()
                    if not INSTALL_LOG['running']: break
                import time; time.sleep(0.1)
        elif self.path.startswith('/uninstall/'):
            parts = self.path[11:].split('/', 1)
            source, app_id = (parts[0], parts[1]) if len(parts) == 2 else ('', parts[0])
            ok = False
            # Check explicit source first, then fall back to heuristics
            if source == 'apt':
                threading.Thread(target=run_apt_uninstall, args=(app_id,), daemon=True).start()
                return self.json({'ok': True, 'async': True})
            elif source == 'snap':
                threading.Thread(target=run_snap_uninstall, args=(app_id,), daemon=True).start()
                return self.json({'ok': True, 'async': True})
            elif source == 'pwa' or app_id.startswith('chrome-'):
                try: os.remove(os.path.expanduser(f'~/.local/share/applications/{app_id}.desktop')); ok = True
                except: pass
            elif source == 'flatpak' or '.' in app_id:
                is_user = subprocess.run(['flatpak', 'info', '--user', app_id], capture_output=True).returncode == 0
                ok = subprocess.run(['flatpak', 'uninstall', '-y', '--user', app_id] if is_user else ['pkexec', 'flatpak', 'uninstall', '-y', app_id]).returncode == 0
            return self.json({'ok': ok}, 200 if ok else 500)
        elif self.path.startswith('/launch/'):
            app = self.path[8:]
            # Try gtk-launch with app id, then search for matching .desktop file
            for dirs in ['/usr/share/applications', os.path.expanduser('~/.local/share/applications')]:
                for f in os.listdir(dirs) if os.path.isdir(dirs) else []:
                    if f.endswith('.desktop') and app.lower() in f.lower():
                        subprocess.Popen(['gtk-launch', f[:-8]], start_new_session=True)
                        break
                else: continue
                break
            else:
                subprocess.Popen(['gtk-launch', app], start_new_session=True)
            self.send_response(204)
            self.end_headers()
        elif self.path.startswith('/icon/'):
            name = self.path[6:]
            icon_path = find_icon(name)
            if icon_path and os.path.exists(icon_path):
                ext = icon_path.rsplit('.', 1)[-1]
                ctype = {'png': 'image/png', 'svg': 'image/svg+xml', 'xpm': 'image/x-xpixmap'}.get(ext, 'image/png')
                self.send_response(200)
                self.send_header('Content-type', ctype)
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                with open(icon_path, 'rb') as f: self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), Handler)
    print('Server running at http://localhost:8080')
    server.serve_forever()
