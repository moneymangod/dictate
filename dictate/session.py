"""Which OS and display session we run on, plus the few paths and texts that differ between them."""
import os
import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
# Wayland blocks global key hooks and fake keystrokes for normal apps, so Linux needs different code there.
IS_WAYLAND = IS_LINUX and (
    os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
)

def data_dir() -> str:
    """Where the log, lock file and API key live."""
    if IS_WINDOWS:
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Dictate")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Dictate")


def mic_settings_hint() -> str:
    if IS_WINDOWS:
        return "Windows Settings → Privacy & security → Microphone"
    return "System Settings → Sound (pick the right input device)"
