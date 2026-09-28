import numpy as np

from dictate.transcriber import SAMPLE_RATE, Transcriber, clean_transcript, resample, rms, too_short


def test_clean_transcript_removes_non_speech_markers():
    assert clean_transcript(" [BLANK_AUDIO] ") == ""
    assert clean_transcript(" Hello (music)  world [NOISE]. ") == "Hello world ."
    assert clean_transcript("  Open   VS Code.\n") == "Open VS Code."


def test_silence_gate_skips_the_model():
    # No model loaded: silence must return "" without touching it.
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
