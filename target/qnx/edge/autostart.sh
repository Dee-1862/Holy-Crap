#!/bin/sh
# Starts the Holy-Crap edge pipeline when the Pi boots, so it runs with no laptop and no ssh session.
#
# QNX Everywhere has no user startup hook, but post_startup.sh sources /data/var/etc/settings/network as root at
# its networking step. install_autostart.sh adds one guarded line there that runs this file in the background.
# It waits for the rest of the boot, gives the clock a chance to sync over Wi-Fi, then starts the supervisor as
# qnxuser, unless it is already running.

HOME_DIR=/data/home/qnxuser
LOG=$HOME_DIR/hc-edge.log

sleep 25                                         # let Wi-Fi, dhcpcd, ntpdate and the camera service come up
# read only the time servers, never source the settings file: it holds the line that starts this script
TIME_SERVERS=$(grep '^TIME_SERVERS=' /data/var/etc/settings/network | cut -d= -f2)
[ -n "$TIME_SERVERS" ] && ntpdate -u $(echo "$TIME_SERVERS" | sed 's/:/ /g') >/dev/null 2>&1

if pidin -F "%A" | grep -q "python3 supervisor[.]py"; then      # the brackets keep grep from matching itself
  exit 0
fi
cd $HOME_DIR/hc-edge || exit 1
# the Camera Module 3 when the sensor service found it at boot (unit 4, the second camera port), recorded footage otherwise
CAMERA="--camera replay"
[ -e /dev/sensor/camera4 ] && [ -x cam/hccam ] && CAMERA="--camera live --unit 4"
on -u "$(id -u qnxuser):$(id -g qnxuser)" sh -c "export HOME=$HOME_DIR USER=qnxuser; cd $HOME_DIR/hc-edge && nohup python3 supervisor.py $CAMERA > $LOG 2>&1 < /dev/null &"
