#!/usr/bin/env bash
# ลิงก์สาธารณะปัจจุบันของ Quick Tunnel (เปลี่ยนทุกครั้งที่ tunnel เริ่มใหม่ เช่น หลังรีบูตเครื่อง)
cd "$(dirname "$0")/.."
docker compose -f deploy/docker-compose.yml --profile quick logs quick 2>/dev/null \
  | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
