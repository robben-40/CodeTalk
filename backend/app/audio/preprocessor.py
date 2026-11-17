"""
preprocessor.py  (Orang 2)

Membersihkan SATU jendela audio sebelum masuk ke ASR (engine Orang 1).
Prinsip: pembersihan RINGAN. Whisper dilatih pada audio apa adanya; pembersihan
agresif (mis. noise reduction keras) justru bisa merusak huruf konsonan dan
menaikkan WER. Karena itu setiap langkah di sini bisa dimatikan satu per satu,
supaya Anda bisa membuktikan dengan data langkah mana yang membantu.

Urutan langkah (masing-masing punya alasan):
  1. int16 -> float32 (-1..1)   : format standar model.
  2. Hapus DC offset            : mikrofon murah sering "menggeser" garis nol; ini
                                  memboroskan rentang dan mengacaukan filter.
  3. High-pass ~100 Hz          : membuang dengung AC/kipas/getaran meja (< 100 Hz).
                                  Suara manusia dimulai di sekitar 85-100 Hz ke atas,
                                  jadi hampir tidak ada ucapan yang terbuang.
  4. Normalisasi puncak         : menyamakan level agar dosen yang jauh dari mikrofon
                                  tidak terlalu pelan. Dibatasi (max_gain) supaya
                                  jendela yang isinya hanya noise tidak diperkeras.
  5. Clip ke [-1, 1]            : pengaman.

Catatan desain: fungsi ini STATELESS (tiap jendela diproses sendiri-sendiri).
Konsekuensinya ada transien filter sangat singkat di awal jendela (beberapa ms),
dan gain bisa berbeda antar-jendela. Itu trade-off yang sengaja dipilih demi
kesederhanaan; ring buffer tetap menyimpan audio ASLI (mentah) sehingga Anda
bisa membandingkan dengan/tanpa preprocessing pada eksperimen.
"""
from math import gcd

import numpy as np
from scipy.signal import butter, lfilter, resample_poly

from app.audio.stream_buffer import SAMPLE_RATE, int16_to_float32


def resample_to_16k(samples: np.ndarray, sample_rate_in: int) -> np.ndarray:
    """
    CADANGAN saja. Kontrak tim: frontend (Orang 3) yang resampling ke 16 kHz.
    Fungsi ini hanya jaring pengaman kalau ternyata audio datang di 44.1/48 kHz.
    """
    if sample_rate_in == SAMPLE_RATE:
        return samples
    g = gcd(sample_rate_in, SAMPLE_RATE)
    return resample_poly(samples, SAMPLE_RATE // g, sample_rate_in // g).astype(samples.dtype)


class Preprocessor:
    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        remove_dc: bool = True,
        highpass_hz: float = 100.0,   # 0 = matikan
        highpass_order: int = 2,
        normalize: bool = True,
        target_peak: float = 0.7,     # puncak yang dituju setelah normalisasi
        max_gain: float = 8.0,        # batas penguatan (~18 dB)
        min_peak: float = 0.01,       # di bawah ini dianggap hening: jangan diperkeras
    ):
        self.remove_dc = remove_dc
        self.normalize = normalize
        self.target_peak = target_peak
        self.max_gain = max_gain
        self.min_peak = min_peak
        self.highpass_hz = highpass_hz
        if highpass_hz > 0:
            # Frekuensi cutoff dinyatakan relatif terhadap Nyquist (= sample_rate / 2)
            self._b, self._a = butter(highpass_order, highpass_hz / (sample_rate / 2), btype="highpass")

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        # 1. Samakan format -> float32 (-1..1)
        if audio.dtype == np.int16:
            x = int16_to_float32(audio)
        else:
            x = audio.astype(np.float32, copy=True)
        if x.size == 0:
            return x

        # 2. Hapus DC offset
        if self.remove_dc:
            x = x - x.mean()

        # 3. High-pass
        if self.highpass_hz > 0:
            x = lfilter(self._b, self._a, x).astype(np.float32)

        # 4. Normalisasi puncak (dengan batas)
        if self.normalize:
            peak = float(np.abs(x).max())
            if peak >= self.min_peak:
                gain = min(self.target_peak / peak, self.max_gain)
                x = x * gain

        # 5. Pengaman
        return np.clip(x, -1.0, 1.0).astype(np.float32)