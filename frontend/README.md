# Frontend CodeTalk

Implementasi tugas Orang 3 menggunakan React, TypeScript, Tailwind CSS, dan Web Audio API. Tata letak mengikuti desain yang telah disetujui.

## Menjalankan

Gunakan Node.js 20.19+ atau 22.12+.

```sh
cd frontend
npm ci
npm run dev
```

Buka `http://localhost:5173`. Jalankan backend tim secara terpisah pada port 8000. Vite meneruskan `/topics`, `/ws`, dan `/api` ke `http://127.0.0.1:8000`. Untuk backend terpisah, salin `.env.example` ke `.env.local` dan isi `VITE_BACKEND_URL` dengan root URL backend. Mikrofon membutuhkan localhost atau HTTPS.

Pilih mata kuliah dan isi istilah tambahan yang dipisahkan koma jika diperlukan, lalu klik **Mulai rekam**. Koneksi menunggu `ready` sebelum mikrofon mengirim audio. **Akhiri rekaman** menghentikan mikrofon, mengirim frame audio terakhir, lalu meminta backend memfinalkan transkrip. **Sesi baru** mengosongkan hasil sesi setelah rekaman berhenti.

## Kontrak backend

- `GET /topics` → `{ default_topic, topics: [{ key, label, ... }] }`. Daftar bawaan berisi sepuluh topik yang sama dengan backend jika daftar tidak dapat dimuat.
- `WS /ws/stream?topic=<key>&extra_terms=<comma-separated>` menggunakan kontrak yang sudah ada di `backend/app/api/ws_stream.py`.
- Audio berupa PCM Int16 little-endian, 16 kHz, mono, dengan frame 100 ms. AudioWorklet mencampur kanal dan melakukan resampling secara kontinu, termasuk untuk perangkat 44,1/48 kHz. Frame pendek terakhir dikirim saat berhenti. Frontend tidak memakai Web Speech API atau ASR cloud.
- Pesan `ready`, `status`, `transcript`, `error`, dan `stopped` diproses sesuai backend. `committed_transcript` menjadi sumber teks final agar pembaruan tidak menggandakan kalimat. Audio tidak diantrikan sebelum `ready` atau diputar kembali ke speaker.

### Integrasi Smart Notes dengan Orang 4

`backend/app/api/routes_notes.py` saat implementasi frontend masih berupa placeholder. Frontend menyiapkan kontrak berikut di `src/api.ts`:

```http
POST /api/notes
Content-Type: application/json

{"transcript":"teks final sesi", "topic":"data_structures"}
```

```json
{ "markdown": "# Judul catatan\n\nRingkasan dan blok kode Markdown." }
```

Hanya transkrip final yang dikirim; teks sementara tidak dimasukkan. Kontrak ini perlu disamakan dengan Orang 4 ketika endpoint-nya dibuat. Jika endpoint belum tersedia atau gagal, aplikasi menampilkan pesan dan mempertahankan transkrip. Tidak ada hasil catatan tiruan di aplikasi.

## Ekspor

- Transkrip `.txt` berisi teks final dan menandai teks sementara yang belum terkonfirmasi jika masih ada.
- Smart Notes `.pdf` membuka dialog cetak browser. Pilih **Simpan sebagai PDF**. Tampilan cetak hanya memuat catatan dan mata kuliah. Akhiri rekaman lebih dahulu agar dialog cetak tidak mengganggu streaming audio.
- Metrik sesi `.json` berisi metadata `ready`, transkrip, sampel latency/RTF, dan ringkasan backend. Tidak menyimpan rekaman suara.

## Pemeriksaan

```sh
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Jika Microsoft Edge sudah terpasang di Windows, unduhan Chromium tidak diperlukan:

```powershell
$env:PLAYWRIGHT_CHANNEL = 'msedge'
npm run test:e2e
```

Tes browser menggunakan mikrofon virtual serta endpoint/WebSocket uji, bukan mikrofon pengguna atau model ASR. Tes mencakup urutan `ready`, format/frame PCM, partial/final tanpa duplikasi, flush/stop, pelepasan mikrofon, pembatalan, putus koneksi, layanan catatan yang belum tersedia, ekspor, dan tata letak kecil. Pengujian inference ASR serta LLM sesungguhnya dilakukan bersama backend tim.

`npm audit` saat penyusunan masih melaporkan empat temuan pada rantai dependensi pengembangan Vite → tinyglobby/fdir → picomatch. Registry belum menyediakan picomatch yang memperbaiki advisory tersebut. Tidak dilakukan downgrade/`audit fix --force`; dependensi runtime tidak termasuk temuan ini.
