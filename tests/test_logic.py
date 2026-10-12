import json

import httpx
import numpy as np
import pytest

from dictate.transcriber import SAMPLE_RATE, Transcriber, api_key, clean_transcript, resample, rms, too_short


def test_clean_transcript_removes_non_speech_markers():
    assert clean_transcript(" [BLANK_AUDIO] ") == ""
    assert clean_transcript(" Hello (music)  world [NOISE]. ") == "Hello world ."
    assert clean_transcript("  Open   VS Code.\n") == "Open VS Code."


def test_silence_gate_skips_the_model():
    # Not loaded: silence must return "" without touching it.
    assert Transcriber().transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32)) == ""
    assert rms(np.full(100, 0.5, dtype=np.float32)) == 0.5
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_short_presses_are_discarded():
    assert too_short(np.zeros(int(SAMPLE_RATE * 0.29), dtype=np.float32))
    assert not too_short(np.zeros(int(SAMPLE_RATE * 0.3), dtype=np.float32))


def test_resample_to_16k():
    one_second_44k = np.sin(np.linspace(0, 2 * np.pi * 440, 44_100)).astype(np.float32)
    out = resample(one_second_44k, 44_100)
    assert out.dtype == np.float32
    assert out.size == SAMPLE_RATE
    assert abs(out[0] - one_second_44k[0]) < 1e-6 and abs(out[-1] - one_second_44k[-1]) < 1e-6
    same = np.ones(10, dtype=np.float32)
    assert resample(same, SAMPLE_RATE) is same


def speech(seconds: float = 1.0) -> np.ndarray:
    return (0.3 * np.sin(np.linspace(0, 2 * np.pi * 200 * seconds, int(SAMPLE_RATE * seconds)))).astype(np.float32)


def loaded(handler) -> Transcriber:
    transcriber = Transcriber(transport=httpx.MockTransport(handler))
    transcriber.load()
    return transcriber


def test_audio_is_sent_to_groq_and_the_text_cleaned(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    seen = []

    def handler(request):
        if request.url.path.endswith("/audio/transcriptions"):
            seen.append(request)
            return httpx.Response(200, json={"text": " Hello [noise] world. "})
        return httpx.Response(200, json={})

    assert loaded(handler).transcribe(speech()) == "Hello world."
    request = seen[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert request.headers["authorization"] == "Bearer gsk_test"
    assert b'name="model"\r\n\r\nwhisper-large-v3-turbo' in request.content
    assert b"RIFF" in request.content  # a WAV file


def test_api_errors_carry_groq_s_message(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    error = {"error": {"message": "Invalid API Key"}}
    transcriber = loaded(lambda r: httpx.Response(401, json=error))
    with pytest.raises(RuntimeError, match="Groq 401: Invalid API Key"):
        transcriber.transcribe(speech())


def test_missing_key_is_reported(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("dictate.transcriber.KEY_FILE", str(tmp_path / "missing.txt"))
    with pytest.raises(RuntimeError, match="No Groq API key"):
        Transcriber().load()
    assert (tmp_path / "missing.txt").read_text() == ""  # created empty, ready for the key
    (tmp_path / "key.txt").write_text("gsk_from_file\n")
    monkeypatch.setattr("dictate.transcriber.KEY_FILE", str(tmp_path / "key.txt"))
    assert api_key() == "gsk_from_file"


def test_going_offline_at_startup_is_not_fatal(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    def offline(request):
        raise httpx.ConnectError("no network")

    assert loaded(offline).ready


def test_cleanup_sends_the_transcript_to_the_llm(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    seen = []

    def handler(request):
        if request.url.path.endswith("/chat/completions"):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": " Meet me at 7. "}}]})
        return httpx.Response(200, json={})

    assert loaded(handler).correct("Meet me at 8, no sorry, 7.") == "Meet me at 7."
    body = seen[0]
    assert body["model"] == "qwen/qwen3.8-27b"
    assert body["messages"][-1]["content"] == "<transcript>Meet me at 8, no sorry, 7.</transcript>"


def test_cleanup_failure_keeps_the_raw_transcript(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert loaded(lambda r: httpx.Response(500, json={})).correct("Hello world.") == "Hello world."

    def offline(request):
        raise httpx.ReadTimeout("slow")

    assert loaded(offline).correct("Hello world.") == "Hello world."
