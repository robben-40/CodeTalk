# CodeTalk — Real-Time CS Lecture Transcriber & Smart Note Summarizer

**CodeTalk** adalah aplikasi *real-time speech recognition* yang berjalan secara lokal untuk membantu mahasiswa Computer Science menangkap penjelasan lisan dosen selama sesi perkuliahan dan *live coding*, lalu merangkumnya menjadi catatan pembelajaran terstruktur dan *pseudocode* menggunakan LLM.

## Fitur Utama & Batasan Teknis

- **Zero External ASR API**: Seluruh proses *Speech-to-Text* berjalan 100% lokal menggunakan `Silero VAD` + `faster-whisper` (CTranslate2).
- **True Real-Time Streaming**: Menangkap audio secara *continuous* (16kHz Mono PCM) melalui WebSocket dan menampilkan *partial transcription* serta *updated/final transcription* secara langsung.
- **CS Domain Context Prompting**: Injeksi istilah teknis Computer Science ke *initial prompt* ASR lokal untuk meningkatkan akurasi pengenalan istilah (*code-switching* Indonesia–Inggris).
- **LLM Smart Note & Code Summarizer**: Menggunakan LLM API (Gemini / OpenAI) hanya untuk tahap *post-processing* guna mengoreksi istilah teknis, merangkum poin materi, dan mengekstrak *pseudocode/code snippet*.
- **Real-Time Telemetry**: Memantau status sistem, *Latency*, dan *Real-Time Factor (RTF)* secara langsung.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, WebSockets, `faster-whisper`, Silero VAD, `numpy`, `librosa`, `torchaudio`
- **Frontend**: React, Vite, TypeScript, Tailwind CSS
- **LLM (Post-Processing)**: Gemini API / OpenAI API

## Struktur Projek

```text
CodeTalk/
├── README.md
├── .gitignore
├── .env.example
├── start.sh
├── backend/
│   ├── pyproject.toml
│   ├── main.py
│   ├── models/
│   └── app/
│       ├── config.py
│       ├── api/            # WebSocket streaming & REST endpoints
│       ├── audio/          # Ring buffer, Silero VAD, preprocessing
│       ├── asr_local/      # Faster-Whisper engine, streaming policy, CS prompts
│       ├── llm_summarizer/ # LLM client & prompt templates
│       └── telemetry/      # Latency/RTF tracker & session logger
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.tsx
│       ├── hooks/          # Audio stream & WebSocket ASR hooks
│       └── components/     # Split-View UI components
├── evaluation/
│   ├── audio_samples/      # Baseline, noisy class, & heavy CS terms
│   ├── ground_truth/       # Reference transcripts (references.json)
│   ├── scripts/            # WER, latency benchmark, & error table scripts
│   └── results/
└── docs/
    ├── PRD.md
    ├── ai_usage_log.md
    └── user_testing/       # Questionnaire template & feedback summary
```

## Memulai (Quick Start)

1. Salin `.env.example` menjadi `.env` dan isi konfigurasi API key LLM yang diperlukan:
   ```bash
   cp .env.example .env
   ```
2. Jalankan aplikasi (backend & frontend) menggunakan skrip startup:
   ```bash
   ./start.sh
   ```
   *(Catatan: Implementasi modul saat ini masih berupa kerangka awal / scaffold sesuai pembagian tugas tim.)*
