# Termux RunCommandService - Sources

## Official Documentation
- [RUN_COMMAND Intent Wiki](https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent) - Main documentation for sending commands to Termux

## Source Code References
- [TermuxConstants.java](https://raw.githubusercontent.com/termux/termux-app/master/termux-shared/src/main/java/com/termux/shared/termux/TermuxConstants.java) - Intent extra key constants

## Key Implementation Details

### Permission
```xml
<uses-permission android:name="com.termux.permission.RUN_COMMAND" />
```

### Termux Setup (run in Termux)
```bash
mkdir -p ~/.termux
echo "allow-external-apps = true" >> ~/.termux/termux.properties
termux-reload-settings
```

### Intent Structure
```kotlin
Intent().apply {
    setClassName("com.termux", "com.termux.app.RunCommandService")
    action = "com.termux.RUN_COMMAND"
    putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash")
    putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arrayOf("-c", "your command"))
    putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home")
    putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)
    putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", pendingIntent)  // FLAG_MUTABLE required
}
```

### Result Bundle Structure
Results returned in nested Bundle with key `"result"`:
```kotlin
val bundle = intent.getBundleExtra("result")
val stdout = bundle.getString("stdout")
val stderr = bundle.getString("stderr")
val exitCode = bundle.getInt("exitCode")
```

### Requirements
- Termux app version >= 0.109
- PendingIntent must use `FLAG_MUTABLE` (Termux modifies it to add results)
- Max 100KB combined stdout/stderr (truncated from start if larger)
