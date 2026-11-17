import math
from typing import Callable, List, NamedTuple

import numpy as np

from app.audio.stream_buffer import SAMPLE_RATE, AudioRingBuffer, int16_to_float32

# Silero VAD (16 kHz) hanya menerima potongan TEPAT 512 sampel = 32 ms.
CHUNK = 512


class VADEvent(NamedTuple):
    kind: str          # "speech_start" atau "speech_end"
    sample_index: int  # index ABSOLUT di ring buffer (detik = index / 16000)


class VADStateMachine:
    def __init__(self, threshold=0.5, min_silence_ms=500, min_speech_ms=250,
                 speech_pad_ms=100, sample_rate=SAMPLE_RATE):
        self.threshold = threshold
        # Hysteresis: untuk MEMULAI butuh prob >= threshold, tapi untuk TETAP bicara
        # cukup prob > neg_threshold (lebih rendah). Mencegah "kedip-kedip" di batas.
        self.neg_threshold = max(threshold - 0.15, 0.01)
        self.min_silence_chunks = math.ceil(min_silence_ms * sample_rate / 1000 / CHUNK)
        self.min_speech_chunks = math.ceil(min_speech_ms * sample_rate / 1000 / CHUNK)
        self.pad = int(speech_pad_ms * sample_rate / 1000)

        self.in_speech = False
        self._speech_run = 0          # berapa chunk bersuara berturut-turut (saat belum "in_speech")
        self._candidate_start = 0     # di mana suara kandidat itu mulai
        self._silence_run = 0         # berapa chunk hening berturut-turut (saat "in_speech")
        self._last_speech_end = 0     # ujung chunk terakhir yang bersuara

    def update(self, prob: float, chunk_start: int) -> List[VADEvent]:
        chunk_end = chunk_start + CHUNK
        events: List[VADEvent] = []

        if not self.in_speech:
            if prob >= self.threshold:
                if self._speech_run == 0:
                    self._candidate_start = chunk_start
                self._speech_run += 1
                if self._speech_run >= self.min_speech_chunks:
                    self.in_speech = True
                    self._silence_run = 0
                    self._last_speech_end = chunk_end
                    # Start "diputar mundur" ke awal kandidat (+ pad), jadi tidak ada audio hilang
                    events.append(VADEvent("speech_start", max(0, self._candidate_start - self.pad)))
            else:
                self._speech_run = 0  # terlalu pendek -> dianggap bukan ucapan
        else:
            if prob > self.neg_threshold:
                self._silence_run = 0
                self._last_speech_end = chunk_end
            else:
                self._silence_run += 1
                if self._silence_run >= self.min_silence_chunks:
                    self.in_speech = False
                    self._speech_run = 0
                    events.append(VADEvent("speech_end", min(self._last_speech_end + self.pad, chunk_end)))
        return events

    def flush(self, position: int) -> List[VADEvent]:
        if self.in_speech:
            self.in_speech = False
            return [VADEvent("speech_end", min(self._last_speech_end + self.pad, position))]
        return []


class VADProcessor:
    def __init__(self, ring: AudioRingBuffer, prob_fn: Callable[[np.ndarray], float], **vad_params):
        self.ring = ring
        self.prob_fn = prob_fn
        self.sm = VADStateMachine(sample_rate=ring.sample_rate, **vad_params)
        self._cursor = 0  # index absolut chunk berikutnya yang belum diperiksa

    def process_available(self) -> List[VADEvent]:
        events: List[VADEvent] = []
        # Kalau kita terlalu lambat dan audio lama sudah tertimpa, lompat ke yang tersedia
        if self._cursor < self.ring.oldest_available:
            self._cursor = self.ring.oldest_available
        while self.ring.total_samples - self._cursor >= CHUNK:
            chunk = self.ring.read(self._cursor, self._cursor + CHUNK)
            prob = self.prob_fn(int16_to_float32(chunk))
            events += self.sm.update(prob, self._cursor)
            self._cursor += CHUNK
        return events

    def flush(self) -> List[VADEvent]:
        return self.sm.flush(self._cursor)


def make_silero_prob_fn():
    import torch
    from silero_vad import load_silero_vad

    torch.set_num_threads(1)  # model sangat kecil; 1 thread cukup & tidak berebut CPU dengan ASR
    model = load_silero_vad()

    def prob_fn(chunk_f32: np.ndarray) -> float:
        return model(torch.from_numpy(chunk_f32), SAMPLE_RATE).item()

    # Silero punya MEMORI internal antar-chunk. Panggil ini di awal tiap sesi baru.
    prob_fn.reset = model.reset_states
    return prob_fn
