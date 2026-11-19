"""
Jalankan dari folder backend/:
    python tests/test_vad.py                # tes logika (tanpa torch/model)
    python tests/test_vad.py rekaman.wav    # + Silero ASLI pada WAV 16 kHz mono 16-bit
"""
import pathlib
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from app.audio.stream_buffer import SAMPLE_RATE, AudioRingBuffer
from app.audio.vad_processor import VADProcessor, make_silero_prob_fn


def fake_prob(chunk_f32: np.ndarray) -> float:
    """VAD palsu: 'bersuara' bila energi (RMS) cukup besar. Hanya untuk menguji LOGIKA."""
    rms = float(np.sqrt(np.mean(chunk_f32 ** 2)))
    return 1.0 if rms > 0.05 else 0.0


def seg(seconds: float, loud: bool) -> np.ndarray:
    n = int(seconds * SAMPLE_RATE)
    if not loud:
        return np.zeros(n, dtype=np.int16)
    t = np.arange(n) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * t) * 12000).astype(np.int16)


def run(signal: np.ndarray, prob_fn, feed_ms=32, **params):
    rb = AudioRingBuffer(max_seconds=60)
    vp = VADProcessor(rb, prob_fn, **params)
    events, step = [], int(feed_ms * SAMPLE_RATE / 1000)
    for s in range(0, len(signal), step):
        rb.write(signal[s:s + step])
        events += vp.process_available()
    events += vp.flush()
    return [(e.kind, e.sample_index / SAMPLE_RATE) for e in events]


def test_synthetic_timeline():
    # 0-1 hening | 1-2 bicara | 2-3 hening | 3-3.1 KLIK | 3.1-4.1 hening | 4.1-4.6 bicara | 4.6-5.6 hening
    sig = np.concatenate([seg(1, 0), seg(1, 1), seg(1, 0), seg(0.1, 1),
                          seg(1, 0), seg(0.5, 1), seg(1, 0)])
    ev = run(sig, fake_prob)
    print("events:", [(k, round(t, 2)) for k, t in ev])
    assert [k for k, _ in ev] == ["speech_start", "speech_end", "speech_start", "speech_end"], \
        "klik 100 ms harus diabaikan -> hanya 2 segmen"
    expected = [0.9, 2.1, 4.0, 4.7]  # sudah termasuk pad 100 ms
    for (_, t), e in zip(ev, expected):
        assert abs(t - e) < 0.1, f"waktu {t:.2f}s terlalu jauh dari {e}s"
    print("OK  timeline sintetis (klik diabaikan, 2 segmen terdeteksi)")


def test_odd_feed_sizes():
    """Hasil tidak boleh berubah walau audio datang dalam potongan berukuran aneh."""
    sig = np.concatenate([seg(1, 0), seg(1, 1), seg(1, 0)])
    a = run(sig, fake_prob, feed_ms=32)
    b = run(sig, fake_prob, feed_ms=7)
    c = run(sig, fake_prob, feed_ms=250)
    assert a == b == c
    print("OK  hasil sama untuk feed 7 / 32 / 250 ms")


def test_flush_closes_open_segment():
    sig = np.concatenate([seg(0.5, 0), seg(1, 1)])  # berhenti saat masih bicara
    ev = run(sig, fake_prob)
    assert [k for k, _ in ev] == ["speech_start", "speech_end"]
    print("OK  flush menutup segmen yang masih terbuka")


def run_wav_with_silero(path: str):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, \
            "WAV harus 16 kHz mono 16-bit: ffmpeg -i in.wav -ar 16000 -ac 1 out.wav"
        sig = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    prob_fn = make_silero_prob_fn()
    prob_fn.reset()
    print(f"\nSilero pada {path} ({len(sig) / SAMPLE_RATE:.1f} s):")
    for kind, t in run(sig, prob_fn):
        print(f"  {kind:12s} @ {t:7.2f} s")


if __name__ == "__main__":
    test_synthetic_timeline()
    test_odd_feed_sizes()
    test_flush_closes_open_segment()
    print("Semua tes logika lulus.")
    if len(sys.argv) > 1:
        run_wav_with_silero(sys.argv[1])