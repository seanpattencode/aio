# TermuxBridge APK vs localhost:1111 — Evaluation

## Finding
The TermuxBridge APK approach should be abandoned in favor of the existing localhost UI server (`a ui` / `ui_full.py` on port 1111).

## Why

### TermuxBridge APK problems
- Two separate permission layers: Android `RUN_COMMAND` permission + `allow-external-apps=true` in `~/.termux/termux.properties`
- Users hit "Permission Granted" in app but commands still fail — confusing UX
- adb can't fix it (Termux's `/data/data/com.termux/` is app-private)
- Requires Gradle + JDK + Android SDK + adb to build/deploy
- 290 lines Kotlin + build.py + gradle config — separate codebase to maintain
- No interactive terminal, only single command → output
- No job management

### localhost:1111 already exists and does more
- `lib/ui/ui_full.py` runs on Termux as runit service
- Full interactive terminal via xterm.js + WebSocket PTY
- Job runner with tmux + SQLite tracking
- Zero permissions needed — it's localhost
- Same Python codebase as everything else
- Accessible via browser bookmark or PWA home screen shortcut

## Action
Use `a ui` on Termux. Bookmark `localhost:1111`. No APK needed.
