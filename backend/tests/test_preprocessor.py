"""
Jalankan dari folder backend/:
    python tests/test_preprocessor.py                  # tes otomatis
    python tests/test_preprocessor.py rekaman.wav      # + tulis hasil "sesudah" agar bisa DIDENGAR
"""
import pathlib
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from app.audio.preprocessor import Preprocessor, resample_to_16k
from app.audio.stream_buffer import SAMPLE_RATE

T = np.arange(SAMPLE_RATE) / SAMPLE_RATE  # 1 detik


def amp_at(x: np.ndarray, freq_hz: int) -> float:
    """Amplitudo komponen sinus pada frekuensi tertentu (lewat FFT; 1 detik -> 1 bin = 1 Hz)."""
    return float(np.abs(np.fft.rfft(x))[freq_hz] * 2 / len(x))


def test_dc_removed():
    x = (0.3 + 0.2 * np.sin(2 * np.pi * 1000 * T)).astype(np.float32)
    y = Preprocessor(highpass_hz=0, normalize=False)(x)
    assert abs(float(y.mean())) < 1e-4
    print("OK  DC offset hilang (mean sebelum 0.30 -> sesudah ~0)")


def test_highpass_kills_hum_keeps_speech_band():
    hum = 0.5 * np.sin(2 * np.pi * 50 * T)      # dengung AC/kipas
    tone = 0.3 * np.sin(2 * np.pi * 1000 * T)   # mewakili pita ucapan
    x = (hum + tone).astype(np.float32)
    y = Preprocessor(normalize=False)(x)
    hum_ratio = amp_at(y, 50) / amp_at(x, 50)
    tone_ratio = amp_at(y, 1000) / amp_at(x, 1000)
    print(f"    50 Hz tersisa {hum_ratio:.2f}x | 1000 Hz tersisa {tone_ratio:.2f}x")
    assert hum_ratio < 0.4, "dengung 50 Hz harus berkurang jelas"
    assert 0.95 < tone_ratio < 1.05, "pita ucapan tidak boleh banyak berubah"
    print("OK  high-pass meredam 50 Hz, 1000 Hz nyaris utuh")


def test_normalize_and_gain_cap():
    pre = Preprocessor(highpass_hz=0, remove_dc=False)
    quiet = (0.2 * np.sin(2 * np.pi * 1000 * T)).astype(np.float32)
    y = pre(quiet)
    assert abs(float(np.abs(y).max()) - 0.7) < 0.02
    very_quiet = (0.02 * np.sin(2 * np.pi * 1000 * T)).astype(np.float32)  # butuh gain 35x
    y2 = pre(very_quiet)
    assert abs(float(np.abs(y2).max()) - 0.02 * 8) < 0.01, "gain harus dibatasi 8x"
    print("OK  normalisasi ke puncak 0.7, dan gain dibatasi 8x")


def test_silence_not_amplified():
    noise = (0.002 * np.random.default_rng(0).standard_normal(SAMPLE_RATE)).astype(np.float32)
    y = Preprocessor(highpass_hz=0, remove_dc=False)(noise)
    assert float(np.abs(y).max()) < 0.02, "noise sangat kecil tidak boleh diperkeras"
    print("OK  jendela hampir-hening tidak diperkeras")


def test_format_and_length():
    x16 = (np.sin(2 * np.pi * 440 * T) * 8000).astype(np.int16)
    y = Preprocessor()(x16)
    assert y.dtype == np.float32 and len(y) == len(x16)
    assert float(np.abs(y).max()) <= 1.0
    assert Preprocessor()(np.zeros(0, dtype=np.int16)).size == 0
    print("OK  output float32, panjang sama, dalam [-1, 1], input kosong aman")


def test_resample_fallback():
    t48 = np.arange(48000) / 48000
    x = (np.sin(2 * np.pi * 440 * t48) * 8000).astype(np.int16)
    y = resample_to_16k(x, 48000)
    assert len(y) == 16000
    print("OK  resample 48 kHz -> 16 kHz (1 detik = 16000 sampel)")


def before_after(path: str):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        sig = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    out = Preprocessor()(sig)
    rms = lambda a: float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))
    print(f"\n{path}")
    print(f"  puncak : sebelum {np.abs(sig).max() / 32768:.3f} -> sesudah {np.abs(out).max():.3f}")
    print(f"  RMS    : sebelum {rms(sig / 32768):.4f} -> sesudah {rms(out):.4f}")
    dst = pathlib.Path(path).with_name(pathlib.Path(path).stem + "_preprocessed.wav")
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((out * 32767).astype("<i2").tobytes())
    print(f"  hasil 'sesudah' ditulis ke {dst}  <- DENGARKAN dan bandingkan dengan aslinya")


if __name__ == "__main__":
    test_dc_removed()
    test_highpass_kills_hum_keeps_speech_band()
    test_normalize_and_gain_cap()
    test_silence_not_amplified()
    test_format_and_length()
    test_resample_fallback()
    print("Semua tes preprocessor lulus.")
    if len(sys.argv) > 1:
        before_after(sys.argv[1])