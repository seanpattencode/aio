import dbus
import subprocess
import os
import sys
import time

SYSTEMD_BUSNAME = 'org.freedesktop.systemd1'
SYSTEMD_PATH = '/org/freedesktop/systemd1'
SYSTEMD_MANAGER_INTERFACE = 'org.freedesktop.systemd1.Manager'
SYSTEMD_UNIT_INTERFACE = 'org.freedesktop.systemd1.Unit'

bus = dbus.SystemBus()
proxy = bus.get_object('org.freedesktop.PolicyKit1', '/org/freedesktop/PolicyKit1/Authority')
authority = dbus.Interface(proxy, dbus_interface='org.freedesktop.PolicyKit1.Authority')
system_bus_name = bus.get_unique_name()
subject = ('system-bus-name', {'name' : system_bus_name})
action_id = 'org.freedesktop.systemd1.manage-units'
details = {}
flags = 1  # AllowUserInteraction flag
cancellation_id = ''  # No cancellation id
result = authority.CheckAuthorization(subject, action_id, details, flags, cancellation_id)

if result[1] != 0:
    sys.exit("Need administrative privilege")

systemd_object = bus.get_object(SYSTEMD_BUSNAME, SYSTEMD_PATH)
systemd_manager = dbus.Interface(systemd_object, SYSTEMD_MANAGER_INTERFACE)