# NEXT

Two projects. App first, then day.

## 1. a-app: Termux fork → single integrated app

Fork Termux. Add native GUI layer. Compile with NDK -march=native.
One app, no bridge, full Linux environment + GUI views on top.

### Why
- Termux gets killed by Android → foreground service with persistent notification keeps it alive
- Bridge IPC is slow and fragile — in-process is instant
- End users get one APK, not "install Termux then install bridge then grant permissions"
- Need mobile UI for notes (replacing Google Keep), gates, day view
- Can self-build on phone from within the app itself

### Steps

1. Clone Termux repo (https://github.com/termux/termux-app)
2. Rebrand: com.aios.a (or similar), change app name/icon
3. NDK recompile with -march=native for target device (Tensor G5 / ARM64)
4. Add foreground service + persistent notification
   - Notification shows gate status (nootropics taken? y/n)
   - Action buttons on notification run `a` commands directly
   - Keeps app alive, Android won't kill it
5. Add native GUI view alongside terminal view (toggle between them)
   - Notes view: simple EditText, reads/writes adata/git/notes/ — Google Keep replacement
   - Day view: shows `a day` output — gates + activity patterns
   - Inbox view: agent outputs, notifications, reply capability
6. Internal function calls: GUI buttons → run `a` commands in Termux environment
   - Option A: subprocess `a <cmd>` within Termux's own env (simple, fast enough)
   - Option B: JNI to a.c functions directly (fastest, a is already C)
   - Start with A, move to B if latency matters
7. Auto-install `a` on first launch: `sh a.c install` runs in the built-in terminal
8. adata/ directory shared between terminal and GUI — same files, two views
9. Git sync works as-is (git already installed via Termux packages)

### Existing assets
- feature_tests/android/TermuxBridge/ — working Kotlin app with Termux IPC, permission handling, command input/output UI. Scavenge the GUI patterns.
- a.c install — already handles Termux detection (`pkg install -y clang tmux nodejs git...`)
- Shell function in .bashrc already works in Termux

### Build
- Can build on Ubuntu server with Android SDK + NDK
- Can self-build on phone once bootstrapped (gradle in Termux works, slow but works)
- CI: build APK on push, download to phone

## 2. a day: daily gate + activity pattern view

Backend for the app's day view. Also works standalone in terminal.

### Why
- Hard dependency: nootropics. Skip them → entire day wasted + cascading loss until resumed.
- Previous habit app failed: too many mandatory items → logging burden → missed days → lost predictive power → abandoned.
- Fix: max 3 gates (hard prerequisites) + passive activity pattern display (zero logging burden).

### Design
- Gates: 1-3 hard prerequisites (enforced limit). Stored in adata/git/day/gates.txt.
- Day file: adata/git/day/YYYY-MM-DD.txt. Just gate completion timestamps.
- Activity patterns: read existing activity logs (14k+ entries), filter hub spam, group by hour, show what past same-weekdays looked like. Zero manual input.
- Degrades gracefully: if you don't interact, it still works next time. Data comes from activity logs, not self-reports.

### Steps
1. Create lib/day.c (~80-100 lines)
   - `a day` — show today's gates + activity patterns
   - `a day gate <name>` — add gate (refuse if already 3)
   - `a day done <gate>` — mark gate done, write timestamp to day file
   - `a day rm <gate>` — remove gate
2. Activity pattern reader:
   - Scan adata/git/activity/ for files matching same weekday
   - Filter out hub:* spam entries
   - Group by hour blocks (morning 6-12, afternoon 12-18, evening 18-24, night 0-6)
   - Show: "past Tuesdays you did X at Y time"
3. Add to dispatch table in a.c: {"day",cmd_day},{"da",cmd_day}
4. Hub job for morning reminder: `a hub add morning *-*-*07:00 a day`
   - On phone (via app): persistent notification with gate buttons
   - On desktop: terminal output or email via existing send()
5. Git sync: day files sync across devices via existing adata/git mechanism

### Data layout
```
adata/git/day/
  gates.txt          one gate name per line, max 3
  2026-02-17.txt     gate:nootropics 08:30
  2026-02-18.txt     gate:nootropics 09:15
```

## Order of operations
1. App first — fork Termux, add foreground service + persistent notification, basic GUI toggle
2. a day — build the C command while app is being set up
3. Integrate — app's day view calls `a day`, notification actions call `a day done <gate>`
4. Iterate — add notes view, inbox view as usage reveals needs

## What NOT to build
- Google activity scraping (auth complexity, breaks, separate project)
- Calendar integration (gcal API is scope creep)
- Energy estimation (no data yet — add as a field in day file later if useful)
- Separate habit tracker app (that's what failed before)
