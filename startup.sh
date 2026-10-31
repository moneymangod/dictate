#!/usr/bin/env bash
# Starts Dictate hidden in the tray every time you log in (KDE Plasma and other desktops).
#   ./startup.sh       turn it on
#   ./startup.sh off   turn it off
DIR="$(dirname "$(readlink -f "$0")")"
FILE="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/dictate.desktop"
if [ "$1" = "off" ]; then
  rm -f "$FILE"
  echo "Dictate will no longer start when you log in."
  exit 0
fi
[ -x "$DIR/.venv/bin/python" ] || { echo "Run ./run.sh once first to set up Dictate."; exit 1; }
mkdir -p "$(dirname "$FILE")"
cat > "$FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Dictate
Comment=Hold Right Shift to dictate
Path=$DIR
Exec=$DIR/.venv/bin/python -m dictate --hidden
Terminal=false
DESKTOP
echo "Dictate will now start hidden in the tray when you log in. To undo: ./startup.sh off"
