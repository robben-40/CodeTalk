"""
stream_buffer.py  (Orang 2)

Ring buffer = "papan tulis melingkar" untuk audio.
Audio dari browser datang terus-menerus. Kita simpan N detik terakhir saja;
kalau penuh, data paling lama ditimpa. Memori jadi tetap (tidak membengkak
walau dosen bicara 2 jam).

Konsep kunci: ABSOLUTE SAMPLE INDEX.
Setiap sampel punya nomor urut sejak rekaman mulai (0, 1, 2, ...), tidak
peduli posisi fisiknya di array. Modul lain (VAD, sliding window, latency
tracker) cukup bilang "beri saya sampel nomor 32000 sampai 48000".
Nomor ini juga yang dipakai untuk menghitung waktu: detik = index / 16000.
"""
import threading

import numpy as np

SAMPLE_RATE = 16000  # kontrak: 16 kHz, mono, Int16 PCM


class AudioRingBuffer:
    def __init__(self, max_seconds: float = 30.0, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.capacity = int(max_seconds * sample_rate)  # jumlah sampel maksimum
        self._buf = np.zeros(self.capacity, dtype=np.int16)
        self._total_written = 0  # total sampel yang pernah masuk (absolute)
        self._leftover = b""     # sisa 1 byte jika potongan WebSocket berukuran ganjil
        # Lock: WebSocket (penulis) dan loop ASR (pembaca) bisa jalan bersamaan.
        self._lock = threading.Lock()

    # ---------- info ----------
    @property
    def total_samples(self) -> int:
        return self._total_written

    @property
    def oldest_available(self) -> int:
        """Index absolut sampel tertua yang masih ada (yang lebih lama sudah tertimpa)."""
        return max(0, self._total_written - self.capacity)

    def seconds(self, n_samples: int) -> float:
        return n_samples / self.sample_rate

    # ---------- tulis ----------
    def write_bytes(self, data: bytes) -> int:
        """Terima bytes mentah Int16 little-endian dari WebSocket."""
        # Satu sampel Int16 = 2 byte. Jaringan bisa memotong di tengah sampel,
        # jadi byte sisa disimpan dan disambung dengan kiriman berikutnya.
        data = self._leftover + data
        usable = len(data) - (len(data) % 2)
        self._leftover = data[usable:]
        if usable == 0:
            return 0
        samples = np.frombuffer(data[:usable], dtype="<i2")  # "<i2" = little-endian int16
        return self.write(samples)

    def write(self, samples: np.ndarray) -> int:
        """Tulis array int16. Return jumlah sampel yang diterima."""
        n = len(samples)
        if n == 0:
            return 0
        with self._lock:
            # Kalau satu kiriman lebih besar dari seluruh buffer, hanya ekor-nya
            # yang muat. Sampel yang dibuang tetap dihitung agar index absolut benar.
            if n > self.capacity:
                self._total_written += n - self.capacity
                samples = samples[-self.capacity:]
            m = len(samples)
            start = self._total_written % self.capacity  # posisi fisik di array
            first = min(m, self.capacity - start)        # muat sampai ujung array
            self._buf[start:start + first] = samples[:first]
            if m > first:                                # sisanya "membelok" ke awal
                self._buf[:m - first] = samples[first:]
            self._total_written += m
        return n

    # ---------- baca ----------
    def read(self, start: int, end: int) -> np.ndarray:
        """Ambil sampel [start, end) memakai index absolut. Hasil berupa salinan."""
        with self._lock:
            start = max(start, self.oldest_available)  # jangan minta data yang sudah tertimpa
            end = min(end, self._total_written)         # jangan minta data dari masa depan
            if end <= start:
                return np.zeros(0, dtype=np.int16)
            idx = np.arange(start, end) % self.capacity  # absolut -> posisi fisik
            return self._buf[idx]  # fancy indexing = salinan, aman dari penimpaan

    def read_last(self, seconds: float) -> np.ndarray:
        n = int(seconds * self.sample_rate)
        return self.read(self._total_written - n, self._total_written)


def int16_to_float32(samples: np.ndarray) -> np.ndarray:
    """Int16 (-32768..32767) -> float32 (-1.0..1.0). Format inilah yang dimakan Silero VAD & Whisper."""
    return samples.astype(np.float32) / 32768.0