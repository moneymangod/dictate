# Dictate

Hold **Right Shift** and speak; release it and the text is pasted into whatever textbox has focus.
Speech is transcribed on this PC with Whisper (`faster-whisper`, `base.en`, CPU int8). No audio leaves the machine.

## Run

Double-click **`run.bat`**. The first run creates `.venv`, installs dependencies and downloads the model (~140 MB).
Dictate then lives in the system tray: left-click opens the window, right-click → Quit.

To have it start by itself, hidden in the tray, whenever you log in: run **`startup.bat`** (undo with `startup.bat off`).

## How it behaves

- Recording starts the moment Right Shift goes down. Holds under 300 ms are ignored, so Shift+letter typing is unaffected.
- The mic opens only while the key is held. Recordings are capped at 120 s.
- The screen edges glow while listening (following your voice), shimmer while transcribing, and flash when text is pasted.
  A red pulse means an error; the reason appears in the window and as a tray notification.
- Pasting uses the clipboard. Your previous clipboard contents are restored 250 ms later.
- The window shows the last 20 transcriptions (kept in memory only) with Copy buttons.

Logs (timings and character counts only, never text) go to `%LOCALAPPDATA%\Dictate\dictate.log`; the model is in
`%LOCALAPPDATA%\Dictate\models`.

## Develop

```
.venv\Scripts\python.exe -m pytest              # unit tests
.venv\Scripts\python.exe scripts\selftest.py    # Windows TTS says a phrase, Whisper transcribes it (no mic needed)
.venv\Scripts\python.exe -m dictate             # run with a console
```

## Known limitations

- Windows doesn't let a normal app see keys pressed in, or paste into, apps running as administrator.
- The mic takes ~100–150 ms to open, so a word spoken the instant you press can lose its first syllable.
- Holding Right Shift for over 300 ms while typing (e.g. a word in capitals) records keyboard noise; it is usually
  rejected as silence but can occasionally produce a stray word.
- If a transcription finishes while you're already holding Right Shift for the next one, the paste is sent as
  Ctrl+Shift+V (paste as plain text in most apps).
- Clipboard managers will see each dictation as a new clipboard entry.
