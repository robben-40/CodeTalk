# PRODUCT REQUIREMENTS DOCUMENT

**Nama Produk:** CodeTalk — Real-Time CS Lecture Transcriber & Smart Note Summarizer

---

## 1. Executive Summary & Visi Produk

**CodeTalk** adalah aplikasi *real-time speech recognition* yang berjalan secara lokal untuk membantu mahasiswa Computer Science menangkap penjelasan lisan dosen selama sesi perkuliahan dan *live coding*, lalu merangkumnya menjadi catatan pembelajaran terstruktur menggunakan LLM. Sistem ini dirancang untuk memproses aliran suara secara *continuous* dengan latensi rendah tanpa bergantung pada layanan API Speech-to-Text eksternal.

---

## 2. Latar Belakang Masalah & Target Pengguna

### 2.1 Problem Statement

Dalam perkuliahan Computer Science (seperti *Data Structures*, *Algorithms*, atau *Object-Oriented Programming*), dosen sering menjelaskan konsep abstrak sembari mendemonstrasikan penulisan kode (*live coding*). Mahasiswa menghadapi dilema kognitif:

1. Jika fokus mencatat penjelasan lisan dosen, mereka tertinggal memperhatikan logika kode yang sedang diketik di layar proyektor.
2. Jika fokus melihat demonstrasi kode, mereka kehilangan detail penjelasan konseptual, analisis kompleksitas ($O(n)$), atau alasan di balik pemilihan algoritma tersebut.
3. Alat transkripsi umum sering gagal mengenali gaya bicara dosen CS di Indonesia yang menggunakan *code-switching* (Bahasa Indonesia bercampur terminologi teknis Bahasa Inggris seperti *pointer*, *array*, *recursion*, *polymorphism*, *linked list*).

### 2.2 Target User (Spesifik & Teridentifikasi)

Sesuai ketentuan proyek bahwa target pengguna harus nyata dan spesifik:

- **Segmen Pengguna:** Mahasiswa aktif S1 Computer Science (khususnya semester 3 hingga semester 5) yang mengikuti kelas pemrograman, algoritma, dan rekayasa perangkat lunak.
- **Karakteristik:** Menggunakan laptop di dalam ruang kelas, membutuhkan catatan yang menggabungkan teori dan blok *pseudocode*/kode, serta akrab dengan antarmuka aplikasi desktop/web modern.
- **Target Rekrutmen Pengujian:** Minimal 5 mahasiswa aktif Computer Science untuk sesi *User Testing* langsung.

### 2.3 Usage Scenario

Mahasiswa membuka aplikasi CodeTalk di laptop saat sesi kuliah dimulai, memilih konteks mata kuliah (misal: *Data Structures*), lalu menekan tombol **Start Listening**. Saat dosen menjelaskan materi, layar secara *real-time* menampilkan *partial transcription* yang terus diperbarui menjadi kalimat utuh. Setiap beberapa menit (atau saat sub-topik selesai), mahasiswa menekan tombol **Generate Smart Note** (atau berjalan otomatis per interval) untuk mengubah transkrip tersebut menjadi rangkuman poin materi dan potongan *pseudocode* di panel sebelah kanan.

---

## 3. Batasan Teknis & Kepatuhan Proyek (Compliance Constraints)

Agar lulus kriteria mutlak proyek akhir:

1. **Zero External ASR API:** Seluruh proses perubahan suara menjadi teks (*Speech-to-Text inference*) wajib berjalan secara lokal di perangkat pengguna menggunakan model *open-source*. Dilarang menggunakan Google Speech API, OpenAI Whisper API (Cloud), Azure Speech, atau AssemblyAI.
2. **True Real-Time Streaming:** Aplikasi dilarang menggunakan alur *Rekam Selesai → Upload File → Transkrip*. Aplikasi wajib menangkap aliran suara secara *continuous*, melakukan inferensi saat pembicara masih berbicara, menampilkan *partial/intermediate transcription*, dan memperbaruinya (*updated transcription*) seiring kalimat berlanjut.
3. **Penggunaan API Eksternal Hanya untuk LLM (Post-Processing):** Penggunaan API eksternal (seperti Gemini API / OpenAI GPT API) hanya digunakan pada tahap kedua (pembuatan ringkasan catatan pembelajaran dari teks hasil transkrip lokal), bukan pada tahap Speech Recognition.

---

## 4. Functional Requirements

| ID | Fitur / Modul | Deskripsi Kebutuhan | Prioritas |
| :--- | :--- | :--- | :--- |
| **FR-01** | Continuous Audio Capture | Sistem harus dapat menangkap input audio secara terus-menerus (*streaming*) dari mikrofon perangkat pada *sample rate* 16kHz Mono PCM. | **P0 (Wajib)** |
| **FR-02** | Voice Activity Detection (VAD) & Preprocessing | Sistem memfilter keheningan (*silence*) dan *background noise* ringan serta memotong aliran suara menjadi *sliding window chunks* tanpa menghentikan rekaman. | **P0 (Wajib)** |
| **FR-03** | Local Real-Time ASR Inference | Sistem menjalankan model ASR lokal (misal: `faster-whisper` dengan kuantisasi INT8/FP16) untuk mengekstrak teks dari *audio buffer* secara *real-time*. | **P0 (Wajib)** |
| **FR-04** | Partial & Updated Transcription Display | UI wajib menampilkan teks sementara (*partial transcript*) saat pengguna sedang berbicara dan memperbaruinya menjadi *final/updated transcript* ketika konteks kalimat selesai. | **P0 (Wajib)** |
| **FR-05** | Real-Time Telemetry & Status Indicator | UI wajib menampilkan status sistem (*Listening*, *Processing*, *Stopped*) serta metrik Latency (detik/ms) dan Real-Time Factor (RTF) secara langsung di layar. | **P0 (Wajib)** |
| **FR-06** | CS Domain Context Prompting | Pengguna dapat memilih/memasukkan topik kuliah (misal: OOP, Algoritma, Database) yang diinjeksikan ke *initial prompt* model ASR lokal untuk meningkatkan akurasi pengenalan istilah teknis. | **P1 (Penting)** |
| **FR-07** | LLM Smart Note & Code Summarizer | Sistem mengirim kumpulan *final transcript* ke LLM API untuk: (1) mengoreksi salah eja fonetik istilah CS, (2) membuat poin ringkasan konsep, dan (3) mengekstrak contoh *pseudocode* atau *code snippet*. | **P1 (Penting)** |
| **FR-08** | Session Export & Evaluation Logging | Pengguna dapat menyimpan hasil transkrip mentah, catatan ringkasan (`.md`), serta log waktu inferensi (`.csv`/`.json`) untuk keperluan perhitungan WER dan Latency pada laporan. | **P1 (Penting)** |

---

## 5. Non-Functional Requirements

1. **Responsiveness & Latency:**
   - Jeda waktu (*latency*) antara kata diucapkan hingga muncul sebagai *partial transcription* di layar ditargetkan berada di bawah **1.0 – 1.5 detik**.
   - Real-Time Factor ($RTF = \frac{ProcessingTime}{AudioDuration}$) harus berada di angka $< 1.0$ agar antrean audio tidak menumpuk saat dosen berbicara panjang.
2. **Resource Efficiency:**
   - Model lokal (seperti `faster-whisper-small` atau `base`) harus dapat berjalan stabil secara *native* di laptop mahasiswa standar (baik menggunakan CPU/Apple Silicon M-series maupun GPU diskrit kelas *entry-level*) dengan penggunaan RAM di bawah 4 GB.
3. **Usability:**
   - Antarmuka dibagi menjadi *Split-View* yang bersih (kiri: *Live Transcript & Audio Telemetry*, kanan: *Structured CS Study Notes*) dengan mode gelap (*Dark Mode*) agar nyaman dilihat di ruang kelas.

---

## 6. System Architecture Design & Data Pipeline

```plaintext
[Microphone Input (16kHz Stream)]
        │
        ▼
[Audio Ring Buffer & Silero VAD] ──► (Mendeteksi suara aktif vs hening)
        │
        ▼
[Sliding Window Streamer (Step: ~0.5s - 0.8s)]
        │
        ▼
[Local ASR Engine (Faster-Whisper Local Model)]
        │
        ├──► Output Sementara ──► [UI: Partial Transcription (Abu-abu/Italic)]
        │
        └──► Kalimat Selesai  ──► [UI: Updated/Final Transcription (Putih/Tegas)]
                                          │
                                          ▼
                                  [Transcript Context Buffer]
                                          │
                                          ▼ (Trigger Otomatis / Manual)
                                  [LLM API (Post-ASR Correction + Summarizer)]
                                          │
                                          ▼
                                  [UI: CS Structured Notes & Pseudocode]
```

### Tech Stack

- **Programming Language:** Python 3.11+
- **Audio Capture & Processing:** `sounddevice` / `PyAudio`, `numpy`, `librosa`, `torchaudio`
- **VAD & Local ASR Model:** Silero VAD + `faster-whisper` (CTranslate2 backend) — dijalankan 100% lokal
- **LLM Integration (Summarizer):** Gemini API / OpenAI API (menggunakan *System Prompt* khusus koreksi istilah Computer Science)
- **Frontend / UI:** FastAPI + WebSockets (Backend) dengan React + Vite + Tailwind CSS (Frontend)

---

## 7. Repository Structure

```text
codetalk/
├── README.md
├── .gitignore
├── .env.example
├── start.sh
│
├── backend/
│   ├── pyproject.toml
│   ├── main.py
│   ├── app/
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── ws_stream.py
│   │   │   └── routes_notes.py
│   │   ├── audio/
│   │   │   ├── stream_buffer.py
│   │   │   ├── vad_processor.py
│   │   │   └── preprocessor.py
│   │   ├── asr_local/
│   │   │   ├── engine.py
│   │   │   ├── streaming_policy.py
│   │   │   └── cs_prompts.py
│   │   ├── llm_summarizer/
│   │   │   ├── client.py
│   │   │   └── prompts.py
│   │   └── telemetry/
│   │       ├── latency_tracker.py
│   │       └── session_logger.py
│   └── models/
│
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.tsx
│       ├── hooks/
│       │   ├── useAudioStream.ts
│       │   └── useWebSocketASR.ts
│       └── components/
│           ├── HeaderBar.tsx
│           ├── StatusTelemetry.tsx
│           ├── LiveTranscript.tsx
│           └── SmartNotesPanel.tsx
│
├── evaluation/
│   ├── audio_samples/
│   │   ├── baseline_clean/
│   │   ├── exp1_noisy_class/
│   │   └── exp2_heavy_cs_terms/
│   ├── ground_truth/
│   │   └── references.json
│   ├── scripts/
│   │   ├── evaluate_wer.py
│   │   ├── benchmark_latency.py
│   │   └── generate_error_table.py
│   └── results/
│
└── docs/
    ├── PRD.md
    ├── user_testing/
    └── ai_usage_log.md
```

---

## 8. Pembagian Tugas Tim (5 Anggota)

| Anggota | Fokus Utama | File / Direktori yang Dikerjakan | Deskripsi Tugas Singkat |
| :--- | :--- | :--- | :--- |
| **Orang 1** | Local ASR Engine & Core Backend | • `backend/main.py`<br>• `backend/app/config.py`<br>• `backend/app/asr_local/engine.py`<br>• `backend/app/asr_local/streaming_policy.py`<br>• `backend/app/asr_local/cs_prompts.py` | Membangun wrapper model ASR lokal (Faster-Whisper), mengatur logika pemisahan *partial* vs *updated transcription*, serta injeksi *initial prompt* kata-kata Computer Science. |
| **Orang 2** | Audio Streaming, VAD & WebSocket | • `backend/app/audio/stream_buffer.py`<br>• `backend/app/audio/vad_processor.py`<br>• `backend/app/audio/preprocessor.py`<br>• `backend/app/api/ws_stream.py`<br>• `backend/app/telemetry/latency_tracker.py`<br>• `backend/app/telemetry/session_logger.py` | Mengelola *continuous audio buffer* (16kHz Mono PCM), filter suara aktif menggunakan Silero VAD, *streaming* via WebSocket, serta pencatatan Latency & RTF. |
| **Orang 3** | Frontend UI & Audio Client | • `frontend/src/App.tsx`<br>• `frontend/src/hooks/useAudioStream.ts`<br>• `frontend/src/hooks/useWebSocketASR.ts`<br>• `frontend/src/components/HeaderBar.tsx`<br>• `frontend/src/components/StatusTelemetry.tsx`<br>• `frontend/src/components/LiveTranscript.tsx`<br>• `frontend/src/components/SmartNotesPanel.tsx` | Membangun antarmuka Split-View React + Tailwind, menangkap mikrofon via Web Audio API, dan menampilkan *live partial/final transcript* beserta indikator Latency. |
| **Orang 4** | LLM Summarizer & Script Evaluasi WER | • `backend/app/llm_summarizer/client.py`<br>• `backend/app/llm_summarizer/prompts.py`<br>• `backend/app/api/routes_notes.py`<br>• `evaluation/scripts/evaluate_wer.py`<br>• `evaluation/scripts/benchmark_latency.py`<br>• `evaluation/scripts/generate_error_table.py` | Mengintegrasikan API LLM untuk merangkum transkrip menjadi catatan CS/pseudocode, serta membuat script perhitungan otomatis WER, CER, dan tabel Error Analysis. |
| **Orang 5** | Dataset Eksperimen, User Testing & Docs | • `evaluation/audio_samples/`<br>• `evaluation/ground_truth/references.json`<br>• `docs/user_testing/questionnaire_template.md`<br>• `docs/user_testing/user_feedback_summary.csv`<br>• `docs/PRD.md` & `docs/ai_usage_log.md`<br>• `README.md` | Menyiapkan rekaman audio eksperimen (Baseline, Noise, Fast Speech), memandu pengujian ke 5 mahasiswa CS, dan mengelola dokumentasi repo serta AI Usage Log. |

---

## 9. Rencana Evaluasi Teknis & User Testing (Sesuai Rubrik Penilaian)

### 9.1 Rencana Eksperimen Teknis (Bobot 20% — LO-2)

Pengujian kuantitatif wajib membandingkan **Baseline** dengan minimal satu **Experimental Condition** menggunakan metrik **Word Error Rate (WER)** dan **Latency**:

$$WER = \frac{S + D + I}{N}$$

1. **Baseline (Clean Speech):** Rekaman/pembacaan materi kuliah CS pada ruangan tenang dengan jarak mikrofon dekat dan kecepatan bicara normal.
2. **Eksperimen 1 (Background Noise):** Pengujian materi yang sama dengan gangguan suara bising ruang kelas (suara AC/kipas, ketikan keyboard).
3. **Eksperimen 2 (Speaking Speed / Code-Switching Density):** Pengujian perbandingan antara penjelasan kecepatan normal vs kecepatan tinggi yang padat istilah teknis Bahasa Inggris (*polymorphism*, *asynchronous*, *recursion*).
4. **Error Analysis Table:** Mendokumentasikan contoh kalimat *Reference* vs *System Output* dan mengklasifikasikan letak kesalahan ke dalam *Substitution*, *Deletion*, atau *Insertion*.

### 9.2 Rencana User Testing (Bobot 20% — LO-3)

- **Partisipan:** Minimal **5 mahasiswa Computer Science** nyata.
- **Task Pengujian:** Setiap partisipan diminta menggunakan CodeTalk untuk mentranskrip penjelasan materi koding berdurasi 2–3 menit, mengamati kemunculan *partial transcription* secara langsung, lalu meninjau hasil ringkasan catatan CS yang dihasilkan.
- **Instrumen Evaluasi:** Kuesioner skala Likert (1–5) yang menilai *Ease of Use*, *Responsiveness*, *Transcription Quality*, dan *Overall Satisfaction*, ditambah wawancara singkat mengenai kesalahan kata teknis dan manfaat fitur rangkuman.
