"""Speech-to-text through Groq's Whisper API. Silence gate and cleanup ported from jarvis's whisper.ts."""
import io
import os
import re
import wave

import httpx
import numpy as np

SAMPLE_RATE = 16_000
MIN_SECONDS = 0.3  # Shorter holds are normal Shift+letter presses.
MAX_SECONDS = 120
SILENCE_RMS = 0.002
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Dictate")
KEY_FILE = os.path.join(DATA_DIR, "groq_key.txt")
BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "whisper-large-v3-turbo"  # Groq has decommissioned distil-whisper-large-v3-en.


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


def api_key() -> str:
    """The Groq API key: GROQ_API_KEY, else the first line of KEY_FILE."""
    if key := os.environ.get("GROQ_API_KEY", "").strip():
        return key
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def wav_bytes(pcm: np.ndarray) -> bytes:
    """Mono 16 kHz float PCM as a 16-bit WAV file."""
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
    return out.getvalue()


class Transcriber:
    def __init__(self, model: str = MODEL, base_url: str = BASE_URL, transport: httpx.BaseTransport | None = None):
        self.model_name = model
        self._base_url = base_url
        self._transport = transport
        self._client: httpx.Client | None = None

    def load(self) -> None:
        """Reads the API key and opens the connection early so the first dictation skips the TLS handshake."""
        key = api_key()
        if not key:
            raise RuntimeError(f"No Groq API key. Set GROQ_API_KEY or put the key in {KEY_FILE}")
        self._client = httpx.Client(
            base_url=self._base_url, headers={"Authorization": f"Bearer {key}"}, timeout=30, transport=self._transport
        )
        try:
            self._client.get("/models")
        except httpx.HTTPError:  # Offline right now; dictating will report it.
            pass

    @property
    def ready(self) -> bool:
        return self._client is not None

    def transcribe(self, pcm: np.ndarray) -> str:
        """Mono 16 kHz float PCM in, cleaned text out ("" for silence)."""
        if rms(pcm) < SILENCE_RMS:
            return ""
        response = self._client.post(
            "/audio/transcriptions",
            files={"file": ("speech.wav", wav_bytes(pcm), "audio/wav")},
            data={"model": self.model_name, "language": "en", "temperature": "0"},
        )
        if response.is_error:
            try:
                detail = response.json()["error"]["message"]
            except Exception:
                detail = response.text[:200]
            raise RuntimeError(f"Groq {response.status_code}: {detail}")
        return clean_transcript(response.json()["text"])
