#!/usr/bin/env bash
# เปิด (หรืออัปเดต) บัญชีหนึ่งชุดพร้อมลิงก์ Quick Tunnel แล้วแสดงลิงก์ (รันบนเซิร์ฟเวอร์ในโฟลเดอร์ของบัญชีนั้น)
# ชื่อชุดคือชื่อโฟลเดอร์ เช่น ai-tutor, ai-tutor-2 พอร์ตในเครื่องมาจาก TUTOR_PORT ใน .env
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "ยังไม่มี .env (รหัสผ่านครูและ Admin)"; exit 1; }
set -a; . ./.env; set +a
PROJECT="$(basename "$PWD")"
mkdir -p runtime
docker compose -p "$PROJECT" -f deploy/docker-compose.yml --profile quick up -d --build
for _ in $(seq 1 20); do
  LINK=$(./deploy/link.sh)
  [ -n "$LINK" ] && break
  sleep 2
done
echo "$PROJECT: ${LINK:-ยังไม่ได้ลิงก์ ลอง ./deploy/link.sh อีกครั้ง}"
