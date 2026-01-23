import subprocess
cmd = 'Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation | % { $c=$_.Temperature-273; Write-Host "$($_.Name): $c C" }'
subprocess.run(['powershell.exe', '-Command', cmd])
