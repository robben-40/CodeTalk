"""Klien uji manual: mengalirkan file WAV ke server /ws/stream seperti mikrofon (real-time).

Gunanya menguji seluruh backend (buffer + VAD + streamer + Whisper asli) TANPA frontend.

Langkah:
  1. Terminal A (venv aktif, folder backend/):  python main.py
  2. Terminal B (venv aktif, folder backend/):
       python tests/ws_client_wav.py /path/rekamanjava.wav --topic oop

Butuh paket `websockets` (pip install websockets). WAV harus 16 kHz, mono, 16-bit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import wave

import websockets


def load_pcm(path: str) -> bytes:
    with wave.open(path, "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 16000):
            raise SystemExit(
                f"Format WAV harus mono/16-bit/16 kHz, file ini: "
                f"{w.getnchannels()} ch, {w.getsampwidth() * 8}-bit, {w.getframerate()} Hz"
            )
        return w.readframes(w.getnframes())


async def send_audio(
    ws, pcm: bytes, frame_ms: int, tail_sec: float, realtime: bool, ready: asyncio.Event
) -> None:
    # Kontrak: JANGAN kirim audio sebelum server mengirim pesan "ready".
    # Server menunda "ready" sampai model Whisper & Silero selesai dimuat (bisa lama
    # pada sesi pertama / saat model baru diunduh). Mengirim audio lebih awal membuat
    # antrean server penuh dan koneksi putus karena "keepalive ping timeout".
    print("Menunggu server siap (model mungkin sedang dimuat/diunduh)...")
    await ready.wait()
    frame_bytes = int(16000 * frame_ms / 1000) * 2
    pcm = pcm + bytes(int(16000 * tail_sec) * 2)  # hening penutup agar kalimat terakhir final
    for i in range(0, len(pcm), frame_bytes):
        await ws.send(pcm[i : i + frame_bytes])
        if realtime:
            await asyncio.sleep(frame_ms / 1000)
    await ws.send(json.dumps({"type": "stop"}))


async def receive(ws, ready: asyncio.Event) -> None:
    async for raw in ws:
        msg = json.loads(raw)
        kind = msg.get("type")
        if kind == "ready":
            ready.set()
            print(f"[ready] sesi {msg['session_id'][:8]} topik={msg['topic']}")
        elif kind == "status":
            print(f"[status] {msg['state']}")
        elif kind == "transcript":
            if msg["final_text"]:
                print(f"[FINAL  ] {msg['final_text']}")
            if msg["partial_text"]:
                print(
                    f"[partial] {msg['partial_text']}   "
                    f"(asr={msg['latency_ms']} ms, rtf={msg['rtf']}, e2e={msg.get('server_e2e_ms')} ms)"
                )
        elif kind == "error":
            print(f"[ERROR  ] {msg['message']}")
            if not ready.is_set():  # gagal menyiapkan sesi: tidak ada gunanya lanjut
                return
        elif kind == "stopped":
            print("\n=== SESI SELESAI ===")
            print("Transkrip akhir:", msg["committed_transcript"])
            print("Ringkasan      :", json.dumps(msg["summary"], indent=2))
            print("Log disimpan   :", msg["log_dir"])
            return


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("wav")
    p.add_argument("--url", default="ws://localhost:8000/ws/stream")
    p.add_argument("--topic", default=None)
    p.add_argument("--extra-terms", default=None, help="dipisah koma")
    p.add_argument("--frame-ms", type=int, default=100)
    p.add_argument("--tail", type=float, default=1.5, help="detik hening penutup")
    p.add_argument("--fast", action="store_true", help="kirim tanpa jeda real-time (BUKAN untuk ukur latency)")
    args = p.parse_args()

    url = args.url
    params = []
    if args.topic:
        params.append(f"topic={args.topic}")
    if args.extra_terms:
        params.append(f"extra_terms={args.extra_terms}")
    if params:
        url += "?" + "&".join(params)

    pcm = load_pcm(args.wav)
    async with websockets.connect(url, max_size=None) as ws:
        ready = asyncio.Event()
        recv_task = asyncio.create_task(receive(ws, ready))
        send_task = asyncio.create_task(
            send_audio(ws, pcm, args.frame_ms, args.tail, not args.fast, ready)
        )
        done, _ = await asyncio.wait({recv_task, send_task}, return_when=asyncio.FIRST_COMPLETED)
        if recv_task in done:  # server selesai/menolak lebih dulu: hentikan pengiriman
            send_task.cancel()
            await asyncio.gather(send_task, return_exceptions=True)
            recv_task.result()
        else:  # normal: audio habis terkirim, tunggu pesan "stopped"
            send_task.result()
            await recv_task


if __name__ == "__main__":
    asyncio.run(main())