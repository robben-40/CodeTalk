"""
Jalankan dari folder backend/:
    python tests/test_stream_buffer.py                 # tes otomatis
    python tests/test_stream_buffer.py rekaman.wav     # + simulasi streaming dari WAV (16 kHz mono)
"""
import pathlib
import sys
import time
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from app.audio.stream_buffer import AudioRingBuffer


def test_odd_sized_chunks():
    """Potongan WebSocket berukuran ganjil (1, 3, 1001 byte) tidak boleh merusak data."""
    rb = AudioRingBuffer(max_seconds=2)
    original = (np.sin(np.linspace(0, 200, 16000)) * 10000).astype("<i2")
    raw, pos, sizes, i = original.tobytes(), 0, [1, 3, 1001, 7], 0
    while pos < len(raw):
        size = sizes[i % len(sizes)]
        rb.write_bytes(raw[pos:pos + size])
        pos += size
        i += 1
    assert rb.total_samples == 16000
    assert np.array_equal(rb.read(0, 16000), original)
    print("OK  odd-sized chunks")


def test_overflow_wraps():
    """Buffer 1 detik, ditulis 2.5 detik -> hanya 1 detik terakhir yang tersisa."""
    rb = AudioRingBuffer(max_seconds=1)
    ramp = np.arange(40000, dtype=np.int16)
    for s in range(0, 40000, 1000):
        rb.write(ramp[s:s + 1000])
    assert rb.total_samples == 40000
    assert rb.oldest_available == 24000
    assert np.array_equal(rb.read(0, 40000), ramp[24000:])
    print("OK  overflow / wrap-around")


def test_single_huge_write():
    rb = AudioRingBuffer(max_seconds=1)
    ramp = np.arange(40000, dtype=np.int16)
    rb.write(ramp)
    assert rb.oldest_available == 24000
    assert np.array_equal(rb.read(24000, 40000), ramp[24000:])
    print("OK  single write > capacity")


def test_read_last():
    rb = AudioRingBuffer(max_seconds=5)
    rb.write(np.arange(16000, dtype=np.int16))
    assert len(rb.read_last(0.5)) == 8000
    print("OK  read_last")


def simulate_wav(path: str, chunk_ms: int = 32):
    """Pura-pura jadi browser: kirim WAV per 32 ms sesuai kecepatan waktu nyata."""
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, \
            "WAV harus 16 kHz, mono, 16-bit. Konversi dulu: ffmpeg -i in.wav -ar 16000 -ac 1 out.wav"
        rb = AudioRingBuffer(max_seconds=10)
        frames = int(16000 * chunk_ms / 1000)
        t0 = time.perf_counter()
        while True:
            data = w.readframes(frames)
            if not data:
                break
            rb.write_bytes(data)
            time.sleep(chunk_ms / 1000)  # meniru waktu nyata
            if rb.total_samples % 16000 < frames:  # cetak kira-kira tiap 1 detik audio
                print(f"audio={rb.seconds(rb.total_samples):5.2f}s  "
                      f"wall={time.perf_counter() - t0:5.2f}s  "
                      f"buffer_oldest={rb.seconds(rb.oldest_available):5.2f}s")


if __name__ == "__main__":
    test_odd_sized_chunks()
    test_overflow_wraps()
    test_single_huge_write()
    test_read_last()
    print("Semua tes lulus.")
    if len(sys.argv) > 1:
        simulate_wav(sys.argv[1])