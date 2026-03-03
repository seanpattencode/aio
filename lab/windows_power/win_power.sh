#!/bin/bash
# Windows power management via aio ssh
# Usage: ./win_power.sh <host> <command> [args]

HOST="${1:-wslhpomen}"
CMD="${2:-status}"
ARG="$3"

PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
SYS="/mnt/c/Windows/System32"

case "$CMD" in
  hibernate|h)
    aio ssh "$HOST" "$SYS/shutdown.exe /h"
    ;;
  sleep|s)
    aio ssh "$HOST" "$SYS/rundll32.exe powrprof.dll,SetSuspendState 0,1,0"
    ;;
  shutdown|off)
    aio ssh "$HOST" "$SYS/shutdown.exe /s /t 0"
    ;;
  restart|r)
    aio ssh "$HOST" "$SYS/shutdown.exe /r /t 0"
    ;;
  wake-daily)
    TIME="${ARG:-8:00am}"
    b64=$(echo "\$trigger = New-ScheduledTaskTrigger -Daily -At $TIME
\$action = New-ScheduledTaskAction -Execute cmd.exe -Argument \"/c echo awake\"
\$settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName AioWakeDaily -Trigger \$trigger -Action \$action -Settings \$settings -Force" | base64 -w0)
    aio ssh "$HOST" "echo $b64 | base64 -d | $PS -ExecutionPolicy Bypass -Command -"
    ;;
  wake-once)
    MINS="${ARG:-5}"
    b64=$(echo "\$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes($MINS)
\$action = New-ScheduledTaskAction -Execute cmd.exe -Argument \"/c echo awake\"
\$settings = New-ScheduledTaskSettingsSet -WakeToRun
Register-ScheduledTask -TaskName AioWakeOnce -Trigger \$trigger -Action \$action -Settings \$settings -Force" | base64 -w0)
    aio ssh "$HOST" "echo $b64 | base64 -d | $PS -ExecutionPolicy Bypass -Command -"
    ;;
  wake-list)
    aio ssh "$HOST" "$SYS/schtasks.exe /query /tn AioWake* /fo list 2>/dev/null" | grep -E "TaskName|Next Run|Status"
    ;;
  wake-rm)
    aio ssh "$HOST" "$SYS/schtasks.exe /delete /tn AioWakeDaily /f 2>/dev/null"
    aio ssh "$HOST" "$SYS/schtasks.exe /delete /tn AioWakeOnce /f 2>/dev/null"
    ;;
  status|st)
    timeout 5 aio ssh "$HOST" 'echo alive' 2>/dev/null && echo "✓ $HOST awake" || echo "x $HOST unreachable"
    ;;
  *)
    echo "Usage: $0 <host> <command> [args]"
    echo "Commands:"
    echo "  status        Check if awake"
    echo "  hibernate     Hibernate"
    echo "  sleep         Sleep"
    echo "  shutdown      Shutdown"
    echo "  restart       Restart"
    echo "  wake-daily    Set daily wake (arg: time, default 8:00am)"
    echo "  wake-once     Set one-time wake (arg: minutes, default 5)"
    echo "  wake-list     List wake tasks"
    echo "  wake-rm       Remove wake tasks"
    ;;
esac
