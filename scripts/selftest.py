"""Speech-to-text check without a microphone (ported from jarvis's stt-selftest.mjs):
Windows text-to-speech says a phrase into a 16 kHz WAV, then the transcriber transcribes it.

    .venv\\Scripts\\python.exe scripts\\selftest.py ["phrase"]
"""
import os
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dictate.transcriber import SAMPLE_RATE, Transcriber  # noqa: E402

phrase = sys.argv[1] if len(sys.argv) > 1 else "Please send the quarterly report to Sarah before Friday afternoon."
wav = os.path.join(tempfile.gettempdir(), f"dictate-selftest-{os.getpid()}.wav")
script = """Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($env:DICTATE_WAV, $f)
$s.Speak($env:DICTATE_TEXT)
$s.Dispose()"""
subprocess.run(
    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
    env={**os.environ, "DICTATE_WAV": wav, "DICTATE_TEXT": phrase},
    check=True,
)
with wave.open(wav) as f:
    pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
os.remove(wav)

print(f'Said:  "{phrase}" ({pcm.size / SAMPLE_RATE:.1f} s of audio)')
started = time.perf_counter()
transcriber = Transcriber()
transcriber.load(on_download=lambda: print("Downloading the Whisper model (first run only)…"))
print(f"Model loaded + warmed up in {time.perf_counter() - started:.1f} s")
for run in (1, 2, 3):
    started = time.perf_counter()
    text = transcriber.transcribe(pcm)
    print(f'Heard: "{text}" in {(time.perf_counter() - started) * 1000:.0f} ms (run {run})')
