#!/usr/bin/env bash
# ลิงก์สาธารณะปัจจุบันของ Quick Tunnel ของบัญชีในโฟลเดอร์นี้ (เปลี่ยนทุกครั้งที่ tunnel เริ่มใหม่ เช่น หลังรีบูตเครื่อง)
cd "$(dirname "$0")/.."
docker compose -p "$(basename "$PWD")" -f deploy/docker-compose.yml --profile quick logs quick 2>/dev/null \
  | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
