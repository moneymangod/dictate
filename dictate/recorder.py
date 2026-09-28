"""Microphone capture: opened on press, closed on release. Nothing records outside that."""
import numpy as np
import sounddevice as sd

from .transcriber import SAMPLE_RATE, resample, rms


def mic_error_message(err: Exception) -> str:
    text = str(err)
    if "-9996" in text or "Error querying device" in text:
        return "No microphone found. Connect one and set it as the default input device in Windows."
    if "-9985" in text or "unavailable" in text.lower():
        return "The microphone is busy or unavailable (another app may be using it)."
    if "-9999" in text or "Unanticipated host error" in text:
        return "Microphone access was denied. Allow microphone access in Windows Settings → Privacy & security → Microphone."
    return f"Microphone error: {text}"


class MicError(Exception):
    pass


class Recorder:
    def __init__(self):
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._rate = SAMPLE_RATE
        self.level = 0.0  # RMS of the latest block, read by the glow animation.

    def start(self) -> None:
        self._chunks = []
        self.level = 0.0
        try:
            try:
                self._stream = self._open(SAMPLE_RATE)
            except sd.PortAudioError:
                # Device refuses 16 kHz: record at its own rate and resample on stop.
                self._stream = self._open(int(sd.query_devices(kind="input")["default_samplerate"]))
            self._stream.start()
        except Exception as err:
            self._close()
            raise MicError(mic_error_message(err)) from err

    def stop(self) -> np.ndarray:
        """Stops recording and returns 16 kHz mono float32 PCM (empty if nothing was recorded)."""
        if not self._stream:
            return np.zeros(0, dtype=np.float32)
        self._close()
        pcm = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
        self._chunks = []
        return resample(pcm, self._rate)

    def _open(self, rate: int) -> sd.InputStream:
        self._rate = rate
        return sd.InputStream(samplerate=rate, channels=1, dtype="float32", callback=self._on_block)

    def _on_block(self, block, _frames, _time, _status) -> None:
        mono = block[:, 0].copy()
        self._chunks.append(mono)
        self.level = rms(mono)

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        self.level = 0.0
        if stream:
            stream.stop()
            stream.close()
