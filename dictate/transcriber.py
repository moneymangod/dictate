"""Local Whisper speech-to-text (faster-whisper). Silence gate and cleanup ported from jarvis's whisper.ts."""
import os
import re

import numpy as np

SAMPLE_RATE = 16_000
MIN_SECONDS = 0.3  # Shorter holds are normal Shift+letter presses.
MAX_SECONDS = 120
SILENCE_RMS = 0.002
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Dictate")
MODEL_DIR = os.path.join(DATA_DIR, "models")


def rms(pcm: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(pcm)))) if pcm.size else 0.0


def too_short(pcm: np.ndarray) -> bool:
    return pcm.size < SAMPLE_RATE * MIN_SECONDS


def clean_transcript(text: str) -> str:
    """Whisper emits markers like [BLANK_AUDIO] or (music) on silence or noise; they are not speech."""
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)).strip()


def resample(pcm: np.ndarray, rate: int) -> np.ndarray:
    """Linear resample of mono float PCM to 16 kHz."""
    if rate == SAMPLE_RATE or not pcm.size:
        return pcm.astype(np.float32, copy=False)
    n = max(1, round(pcm.size * SAMPLE_RATE / rate))
    return np.interp(np.linspace(0, pcm.size - 1, n), np.arange(pcm.size), pcm).astype(np.float32)


class Transcriber:
    def __init__(self, model: str = "base.en", threads: int = 4):
        self.model_name = model
        self.threads = threads
        self._model = None

    def load(self, on_download=lambda: None) -> None:
        """Loads the model (downloading it once), then warms it up so the first dictation is fast."""
        from faster_whisper import WhisperModel

        opts = dict(device="cpu", compute_type="int8", cpu_threads=self.threads, download_root=MODEL_DIR)
        try:
            model = WhisperModel(self.model_name, local_files_only=True, **opts)
        except Exception:
            on_download()
            model = WhisperModel(self.model_name, **opts)
        self._run(model, np.zeros(SAMPLE_RATE, dtype=np.float32))
        self._model = model

    @property
    def ready(self) -> bool:
        return self._model is not None

    def transcribe(self, pcm: np.ndarray) -> str:
        """Mono 16 kHz float PCM in, cleaned text out ("" for silence)."""
        if rms(pcm) < SILENCE_RMS:
            return ""
        return clean_transcript(self._run(self._model, pcm))

    @staticmethod
    def _run(model, pcm: np.ndarray) -> str:
        segments, _ = model.transcribe(
            pcm,
            language="en",
            beam_size=1,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
        )
        return " ".join(s.text for s in segments)
