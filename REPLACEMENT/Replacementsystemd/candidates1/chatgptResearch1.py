#!/usr/bin/env python3
"""
AIOS Systemd Task Manager - runs tasks under systemd supervision.
Requires: python-dbus library. Must run with root privileges or proper PolicyKit rights.
"""

import dbus, os, sys, shlex, time
from dbus.exceptions import DBusException

# Connect to the system bus and get systemd manager interface
SYSTEMD_BUS = 'org.freedesktop.systemd1'
SYSTEMD_PATH = '/org/freedesktop/systemd1'
MANAGER_IFACE = 'org.freedesktop.systemd1.Manager'

try:
    bus = dbus.SystemBus()
    systemd_obj = bus.get_object(SYSTEMD_BUS, SYSTEMD_PATH)
    systemd_mgr = dbus.Interface(systemd_obj, dbus_interface=MANAGER_IFACE)
except DBusException as e:
    sys.exit(f"Failed to connect to systemd: {e}")

def run_task(command, run_at=None, use_realtime=False, unit_name=None):
    """
    Run a command under systemd. If run_at is provided (datetime or timestamp), schedule it using a transient timer.
    use_realtime=True will run with real-time scheduling (FIFO policy with high priority).
    Returns the systemd unit name that was started.
    """
    # Determine unique unit name
    base_name = unit_name or f"aios_task_{int(time.time())}"
    service_name = base_name + ".service"
    # Parse command into executable and args
    if isinstance(command, str):
        cmd_list = shlex.split(command)
    else:
        cmd_list = list(command)
    if not cmd_list:
        raise ValueError("Command is empty")
    exec_path = cmd_list[0]
    args_list = cmd_list[:]  # include the executable as arg0
    # Build service properties for StartTransientUnit
    service_properties = [
        ("Description", f"AIOS Task - {command}"),
        ("ExecStart", [(exec_path, args_list, False)]),  # False -> don't ignore failures
    ]
    # If the task is expected to finish and we want to capture its status, use oneshot
    service_properties.append(("Type", "oneshot"))
    # Apply real-time scheduling if requested
    if use_realtime:
        service_properties.append(("CPUSchedulingPolicy", "rr"))
        service_properties.append(("CPUSchedulingPriority", dbus.Int32(99)))
    # If scheduling for future run
    if run_at:
        # Convert run_at (datetime or timestamp or str) to systemd time string
        if isinstance(run_at, (int, float)):  # timestamp
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(run_at))
        elif hasattr(run_at, "strftime"):     # datetime/date
            ts = run_at.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(run_at, str):
            ts = run_at  # assume already a valid time spec string
        else:
            raise ValueError("Unsupported run_at format")
        timer_name = base_name + ".timer"
        timer_properties = [
            ("Description", f"Timer for {base_name}"),
            ("OnCalendar", ts),
            ("Persistent", False),           # do not run if missed (adjust as needed)
            ("RemainAfterElapse", False)
        ]
        try:
            # Create transient timer + service. The second parameter is "replace" mode.
            systemd_mgr.StartTransientUnit(timer_name, "replace", 
                                           timer_properties, 
                                           [(service_name, service_properties)])
            print(f"Scheduled task '{command}' as transient unit '{service_name}' at {ts}")
        except DBusException as e:
            sys.exit(f"Failed to schedule task: {e}")
        return service_name  # return the service unit name
    else:
        try:
            # Start a transient service immediately
            systemd_mgr.StartTransientUnit(service_name, "replace", service_properties, [])
            print(f"Started task '{command}' as transient service '{service_name}'")
        except DBusException as e:
            sys.exit(f"Failed to start task: {e}")
        return service_name

# Example usage (uncomment for testing purposes):
# run_task("python3 /path/to/script.py")                      # run immediately
# run_task("ls -l /", run_at=time.time()+60)                  # schedule 60 seconds from now
# run_task("my_realtime_app", use_realtime=True)              # run with realtime priority
