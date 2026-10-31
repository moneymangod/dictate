"""Speech-to-text check without a microphone (ported from jarvis's stt-selftest.mjs):
Windows text-to-speech (or espeak-ng on Linux: sudo dnf install espeak-ng) says a phrase into a WAV, then the
transcriber transcribes and cleans it up.

    .venv\\Scripts\\python.exe scripts\\selftest.py ["phrase"]      (Windows)
    .venv/bin/python scripts/selftest.py ["phrase"]                 (Linux)
"""
import os
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dictate.session import IS_WINDOWS  # noqa: E402
from dictate.transcriber import SAMPLE_RATE, Transcriber, resample  # noqa: E402

phrase = sys.argv[1] if len(sys.argv) > 1 else "Please send the quarterly report to Sarah before Friday afternoon."
wav = os.path.join(tempfile.gettempdir(), f"dictate-selftest-{os.getpid()}.wav")
script = """Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($env:DICTATE_WAV, $f)
$s.Speak($env:DICTATE_TEXT)
$s.Dispose()"""
if IS_WINDOWS:
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "DICTATE_WAV": wav, "DICTATE_TEXT": phrase},
        check=True,
    )
else:
    subprocess.run(["espeak-ng", "-w", wav, phrase], check=True)
with wave.open(wav) as f:
    rate = f.getframerate()
    pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
pcm = resample(pcm, rate)
os.remove(wav)

print(f'Said:  "{phrase}" ({pcm.size / SAMPLE_RATE:.1f} s of audio)')
started = time.perf_counter()
transcriber = Transcriber()
transcriber.load()
print(f"Groq connection ready in {time.perf_counter() - started:.1f} s")
for run in (1, 2, 3):
    started = time.perf_counter()
    text = transcriber.transcribe(pcm)
    print(f'Heard: "{text}" in {(time.perf_counter() - started) * 1000:.0f} ms (run {run})')
started = time.perf_counter()
print(f'Clean: "{transcriber.correct(text)}" in {(time.perf_counter() - started) * 1000:.0f} ms')
