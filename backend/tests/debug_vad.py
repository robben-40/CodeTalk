"""
Diagnosis: apa yang sebenarnya dilihat Silero pada WAV Anda?
Jalankan dari folder backend/:
    python tests/debug_vad_probs.py tests/rekaman.wav
"""
import pathlib
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from app.audio.stream_buffer import SAMPLE_RATE, int16_to_float32
from app.audio.vad_processor import CHUNK, make_silero_prob_fn

path = sys.argv[1]
with wave.open(path, "rb") as w:
    print(f"format: {w.getframerate()} Hz, {w.getnchannels()} ch, {w.getsampwidth() * 8}-bit, {w.getnframes()} frames")
    sig = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")

print(f"durasi        : {len(sig) / SAMPLE_RATE:.1f} s")
print(f"amplitudo maks: {np.abs(sig).max()} dari 32767  (< ~500 berarti SANGAT pelan)")
print(f"RMS rata-rata : {np.sqrt(np.mean(int16_to_float32(sig) ** 2)):.4f}")

prob_fn = make_silero_prob_fn()
prob_fn.reset()
probs = []
for s in range(0, len(sig) - CHUNK + 1, CHUNK):
    probs.append(prob_fn(int16_to_float32(sig[s:s + CHUNK])))
probs = np.array(probs)

print(f"\nprobabilitas bicara: maks={probs.max():.3f}  rata-rata={probs.mean():.3f}")
print(f"chunk dengan prob >= 0.5: {(probs >= 0.5).sum()} dari {len(probs)}")
per_sec = int(SAMPLE_RATE / CHUNK)  # ~31 chunk per detik
print("\nprob maksimum per detik:")
for i in range(0, len(probs), per_sec):
    m = probs[i:i + per_sec].max()
    print(f"  detik {i // per_sec:3d}: {m:.2f} {'#' * int(m * 30)}")