#!/bin/sh
# Installs autostart.sh so the pipeline starts at boot. Run once on the Pi as root: sudo sh install_autostart.sh
# Backs up the settings file first and only ever adds one line. Undo with: sudo sh install_autostart.sh --remove
set -e
SETTINGS=/data/var/etc/settings/network
LINE='[ -x /data/home/qnxuser/hc-edge/autostart.sh ] && /data/home/qnxuser/hc-edge/autostart.sh > /dev/null 2>&1 &  # holy-crap autostart'

if [ "$1" = "--remove" ]; then
  grep -v "holy-crap autostart" $SETTINGS > $SETTINGS.tmp && cat $SETTINGS.tmp > $SETTINGS && rm $SETTINGS.tmp
  echo "removed"
  exit 0
fi
[ -f $SETTINGS.before-holy-crap ] || cp -p $SETTINGS $SETTINGS.before-holy-crap
grep -q "holy-crap autostart" $SETTINGS || echo "$LINE" >> $SETTINGS
chmod 755 /data/home/qnxuser/hc-edge/autostart.sh
echo "installed, backup at $SETTINGS.before-holy-crap"
