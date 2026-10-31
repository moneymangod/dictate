# Dictate

Hold **Right Shift** and speak; release it and the text is pasted into whatever textbox has focus.
Speech is transcribed by Groq's Whisper API (`whisper-large-v3-turbo`; `distil-whisper-large-v3-en` has been decommissioned by Groq).
The transcript then goes through a Groq-hosted LLM (`qwen/qwen3.8-27b`) that applies your self-corrections
("meet me at 8, no sorry, 7" → "Meet me at 7."), drops fillers like "um", and fixes punctuation. If that step fails or
takes over 5 s, the raw transcript is pasted instead. (Groq has decommissioned `llama3-8b-8192` and `llama-3.1-8b-instant`.)
Each recording and its transcript are sent to Groq, so you need an internet connection.

## Run

### Windows

Double-click **`run.bat`**. The first run creates `.venv`, installs dependencies.
Put your Groq API key in the `GROQ_API_KEY` environment variable or in `%LOCALAPPDATA%\Dictate\groq_key.txt`
(the first launch creates that file empty if it's missing; paste the key into it and restart).
Dictate then lives in the system tray: left-click opens the window, right-click → Quit.

To have it start by itself, hidden in the tray, whenever you log in: run **`startup.bat`** (undo with `startup.bat off`).

### Fedora KDE Plasma (Wayland or X11)

1. Run once: `./install-linux.sh` (installs packages, lets your user read the keyboard and type), then **log out and back in**.
2. Run **`./run.sh`**. Same API key rules as above, but the file is `~/.local/share/Dictate/groq_key.txt`.
3. To start it at login: `./startup.sh` (undo with `./startup.sh off`).

Plasma 6 uses Wayland, which blocks normal apps from watching keys or typing. So on Wayland Dictate reads the keyboard
through `/dev/input` (evdev) and types through a virtual keyboard (`/dev/uinput`), and uses `wl-copy` / `wl-paste` for the
clipboard. The glow and pill run through XWayland so they can sit on top. On an X11 session it uses the same code as Windows.
If the permissions are missing, Dictate says so in the tray, and if it can't type it just copies the text: press Ctrl+V.

## How it behaves

- Recording starts the moment Right Shift goes down. Holds under 300 ms are ignored, so Shift+letter typing is unaffected.
- The mic opens only while the key is held. Recordings are capped at 120 s.
- While you hold the key, the screen edges glow and a small pill at the bottom of the screen dances with your voice.
  The glow shimmers and the pill's bars roll while transcribing; a cyan ring sweeps in when the text is pasted.
  A red pulse means an error; the reason appears in the window and as a tray notification.
- Pasting uses the clipboard. Your previous clipboard contents are restored 250 ms later.
- The window shows the last 20 transcriptions (kept in memory only) with Copy buttons.

Logs (timings and character counts only, never text) go to `%LOCALAPPDATA%\Dictate\dictate.log`
(Linux: `~/.local/share/Dictate/dictate.log`).

## Develop

```
.venv\Scripts\python.exe -m pytest              # unit tests
.venv\Scripts\python.exe scripts\selftest.py    # Windows TTS says a phrase, Groq transcribes and cleans it (no mic needed)
.venv\Scripts\python.exe -m dictate             # run with a console
```

On Linux use `.venv/bin/python` in place of `.venv\Scripts\python.exe` (the selftest needs `espeak-ng`).

## Known limitations

- Linux: being in the `input` group lets your programs read all keystrokes. Wayland has no safer way to do hold-to-talk on Shift.
- Linux: paste sends the Ctrl+V key code, so on a non-QWERTY layout (e.g. Dvorak) it may press another shortcut.
- Linux: the glow may not show above full-screen native Wayland apps. Untested on real hardware so far; please report problems.

- Windows doesn't let a normal app see keys pressed in, or paste into, apps running as administrator.
- The mic takes ~100–150 ms to open, so a word spoken the instant you press can lose its first syllable.
- Holding Right Shift for over 300 ms while typing (e.g. a word in capitals) records keyboard noise; it is usually
  rejected as silence but can occasionally produce a stray word.
- If a transcription finishes while you're already holding Right Shift for the next one, the paste is sent as
  Ctrl+Shift+V (paste as plain text in most apps).
- Clipboard managers will see each dictation as a new clipboard entry.
