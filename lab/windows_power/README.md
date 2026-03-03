# Windows Power Management via SSH

Control Windows hibernate/wake remotely through WSL SSH.

## Prerequisites

- WSL with SSH server running
- SSH access configured in aio: `aio ssh add wslhpomen user@host:port`

## Commands

### Hibernate

```bash
aio ssh wslhpomen '/mnt/c/Windows/System32/shutdown.exe /h'
```

### Sleep

```bash
aio ssh wslhpomen '/mnt/c/Windows/System32/rundll32.exe powrprof.dll,SetSuspendState 0,1,0'
```

### Shutdown

```bash
aio ssh wslhpomen '/mnt/c/Windows/System32/shutdown.exe /s /t 0'
```

### Restart

```bash
aio ssh wslhpomen '/mnt/c/Windows/System32/shutdown.exe /r /t 0'
```

## Scheduled Wake

Windows can wake from hibernate/sleep using Task Scheduler with `WakeToRun` setting.

### Create daily wake task (8am)

```bash
# Create PowerShell script via base64 (avoids escaping issues)
b64=$(echo '$trigger = New-ScheduledTaskTrigger -Daily -At 8:00am
$action = New-ScheduledTaskAction -Execute cmd.exe -Argument "/c echo awake"
$settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName AioWake8am -Trigger $trigger -Action $action -Settings $settings -Force' | base64 -w0)

aio ssh wslhpomen "echo $b64 | base64 -d > ~/wake.ps1"

# Run it
aio ssh wslhpomen 'cat ~/wake.ps1 | /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -ExecutionPolicy Bypass -Command -'
```

### Verify wake task

```bash
# Check task exists and WakeToRun is true
aio ssh wslhpomen '/mnt/c/Windows/System32/schtasks.exe /query /tn "AioWake8am" /xml' | grep -i wake
```

Output should include:
```xml
<WakeToRun>true</WakeToRun>
```

### Modify wake time

```bash
aio ssh wslhpomen '/mnt/c/Windows/System32/schtasks.exe /change /tn AioWake8am /st 07:00'
```

### Delete wake task

```bash
aio ssh wslhpomen '/mnt/c/Windows/System32/schtasks.exe /delete /tn AioWake8am /f'
```

## One-time wake (e.g., 5 minutes from now)

```bash
b64=$(echo '$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5)
$action = New-ScheduledTaskAction -Execute cmd.exe -Argument "/c echo awake"
$settings = New-ScheduledTaskSettingsSet -WakeToRun
Register-ScheduledTask -TaskName AioWakeOnce -Trigger $trigger -Action $action -Settings $settings -Force' | base64 -w0)

aio ssh wslhpomen "echo $b64 | base64 -d | /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -ExecutionPolicy Bypass -Command -"
```

## Check if machine is awake

```bash
timeout 5 aio ssh wslhpomen 'echo alive' || echo "Unreachable - hibernated/off"
```

## Full workflow

```bash
# 1. Setup wake schedule (once)
aio ssh wslhpomen 'cat ~/wake.ps1 | powershell.exe -ExecutionPolicy Bypass -Command -'

# 2. Hibernate
aio ssh wslhpomen '/mnt/c/Windows/System32/shutdown.exe /h'

# 3. Machine wakes at scheduled time

# 4. Verify awake
aio ssh wslhpomen 'echo alive'
```

## Notes

- WSL SSH connection drops immediately when hibernate/shutdown executes
- Wake-to-run requires task in Task Scheduler (not cron/systemd)
- PowerShell escaping over SSH is difficult - use base64 encoding
- Hibernate preserves state, sleep uses more power but wakes faster
