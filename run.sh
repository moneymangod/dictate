#!/usr/bin/env bash
# Starts Dictate in the tray. The first run creates the venv and installs dependencies;
# if that was interrupted or failed, the next run picks up where it left off.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
if [ ! -f .venv/.installed ]; then
  if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv || { echo "Python 3.12+ with venv is required (sudo dnf install python3)"; exit 1; }
  fi
  .venv/bin/python -m pip install -r requirements.txt || { echo "Installing the dependencies failed. Fix the error above and run again."; exit 1; }
  echo done > .venv/.installed
fi
exec .venv/bin/python -m dictate "$@"
