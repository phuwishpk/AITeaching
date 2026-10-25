#!/usr/bin/env bash
# สร้าง Cloudflare Tunnel ของ Adaptive Tutor แล้วเปิดลิงก์สาธารณะ (รันบนเซิร์ฟเวอร์ครั้งเดียว)
# ใช้: ./deploy/tunnel.sh tutor.digitalradioeducation.site
# ต้องล็อกอิน cloudflared ไว้แล้ว (~/.cloudflared/cert.pem) และโดเมนอยู่ใน Cloudflare บัญชีเดียวกัน
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${1:?ใส่ชื่อโดเมนที่จะใช้ เช่น tutor.digitalradioeducation.site}"
NAME="${TUNNEL_NAME:-ai-tutor}"

if ! cloudflared tunnel list 2>/dev/null | awk '{print $2}' | grep -qx "$NAME"; then
  cloudflared tunnel create "$NAME"
fi
ID=$(cloudflared tunnel list 2>/dev/null | awk -v n="$NAME" '$2==n {print $1}')
cloudflared tunnel route dns "$NAME" "$HOST"

mkdir -p deploy/cloudflared
cp "$HOME/.cloudflared/$ID.json" deploy/cloudflared/credentials.json
chmod 644 deploy/cloudflared/credentials.json   # คอนเทนเนอร์ cloudflared รันด้วย user ที่ไม่ใช่ root
cat > deploy/cloudflared/config.yml <<CONFIG
tunnel: $ID
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: $HOST
    service: http://app:8000
  - service: http_status:404
CONFIG

docker compose -f deploy/docker-compose.yml --profile quick stop quick 2>/dev/null || true
docker compose -f deploy/docker-compose.yml --profile named up -d
echo "เปิดใช้ที่ https://$HOST"
