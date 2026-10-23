#!/usr/bin/env bash
# เปิด Adaptive Tutor บนเครื่องนี้ที่ http://localhost:8000
# ครั้งแรกติดตั้งแพ็กเกจให้เอง และ build หน้าเว็บใหม่เมื่อโค้ดใน frontend/src เปลี่ยน
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/uvicorn ]; then
  echo "ติดตั้งแพ็กเกจ Python…"
  if command -v uv >/dev/null 2>&1; then
    uv venv backend/.venv
    uv pip install --python backend/.venv -r backend/requirements.txt
  else
    python3 -m venv backend/.venv
    backend/.venv/bin/pip install -r backend/requirements.txt
  fi
fi

if [ ! -d frontend/node_modules ]; then
  echo "ติดตั้งแพ็กเกจหน้าเว็บ…"
  (cd frontend && npm ci)
fi

if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  echo "build หน้าเว็บ…"
  (cd frontend && npm run build)
fi

cd backend
echo "เปิดที่ http://localhost:${PORT:-8000}"
exec .venv/bin/uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
