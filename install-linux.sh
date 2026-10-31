#!/usr/bin/env bash
# One-time setup for Fedora (KDE Plasma, Wayland or X11). Run it, then log out and back in.
# It installs the system packages and gives your user permission to read the keyboard (for the Right Shift
# hold) and to type (to paste). Needs sudo.
set -e
sudo dnf install -y python3 python3-devel gcc portaudio wl-clipboard xcb-util-cursor
sudo usermod -aG input "$USER"
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/80-dictate-uinput.rules >/dev/null
echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
sudo modprobe uinput
sudo udevadm control --reload
sudo udevadm trigger
echo
echo "Done. Log out and back in (or reboot) so the 'input' group applies, then run ./run.sh"
