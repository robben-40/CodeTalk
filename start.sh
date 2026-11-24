#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "Menghentikan CodeTalk..."
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "[warn] File .env belum ditemukan di root proyek."
  echo "       ASR lokal tetap berjalan dengan default (model=small, id), tetapi Smart Notes butuh API key di .env."
fi

if [[ -x "$VENV_PYTHON" ]]; then
  PYTHON_BIN="$VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "[error] Python tidak ditemukan. Buat virtualenv dulu di backend/.venv"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import uvicorn, fastapi, faster_whisper, scipy, httpx" 2>/dev/null; then
  echo "[error] Dependensi backend belum lengkap pada: $PYTHON_BIN"
  echo "        Jalankan dari folder backend/:"
  echo "        uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e '.[audio,dev]'"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[error] npm tidak ditemukan. Install Node.js (>=20.19 atau >=22.12) terlebih dahulu."
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Menginstall dependensi frontend (npm install)..."
  npm --prefix "$FRONTEND_DIR" install
fi

echo "Menjalankan CodeTalk Backend di http://localhost:8000 ..."
(
  cd "$BACKEND_DIR"
  exec "$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

echo "Menjalankan CodeTalk Frontend di http://localhost:5173 ..."
(
  cd "$FRONTEND_DIR"
  exec npm run dev -- --host 0.0.0.0 --port 5173
) &
FRONTEND_PID=$!

echo ""
echo "=========================================="
echo " CodeTalk berjalan!"
echo " - Frontend : http://localhost:5173"
echo " - Backend  : http://localhost:8000"
echo " - Health   : http://localhost:8000/health"
echo " Tekan Ctrl+C untuk berhenti."
echo "=========================================="

# Tunggu salah satu proses keluar (compat dengan Bash 3.2 bawaan macOS).
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
