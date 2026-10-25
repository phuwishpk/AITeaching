#!/usr/bin/env bash
# ลิงก์เดียวสำหรับทุกบัญชี: nginx ดู cookie ว่าผู้ใช้อยู่บัญชีไหนแล้วส่งต่อไปยังระบบของบัญชีนั้น พร้อม Quick Tunnel หนึ่งลิงก์
# ใช้ (บนเซิร์ฟเวอร์): ./deploy/gateway.sh <รหัสบัญชี>=<ชื่อโฟลเดอร์บัญชี> ...
#   เช่น ./deploy/gateway.sh k7m2xq=ai-tutor b9t4pw=ai-tutor-2 r3n8vd=ai-tutor-3
# ผู้ใช้เลือกบัญชีครั้งแรกที่ <ลิงก์>/a/<รหัสบัญชี> (หรือพิมพ์รหัสในหน้าแรก) ออกจากบัญชีที่ <ลิงก์>/a/out
# ใส่ชื่อโฟลเดอร์โดยไม่มีรหัส (เช่น ./deploy/gateway.sh ai-tutor) = ทุกคนเข้าระบบนั้นทันที ไม่มีขั้นเลือกบัญชี
set -euo pipefail
cd "$(dirname "$0")/gateway"
[ $# -gt 0 ] || { sed -n 2,6p "$0"; exit 1; }

maps="" networks="" netdefs="" default='""'
for pair in "$@"; do
  code="${pair%%=*}" project="${pair#*=}"
  if [[ "$pair" != *=* ]]; then
    default="${project}-app-1"
  else
    [[ "$code" =~ ^[A-Za-z0-9-]+$ ]] || { echo "รหัสบัญชีใช้ได้แค่ตัวอักษรอังกฤษ ตัวเลข และ -: $code"; exit 1; }
    maps+="    $code ${project}-app-1;"$'\n'
  fi
  networks+="      - ${project}"$'\n'
  netdefs+="  ${project}:"$'\n'"    external: true"$'\n'"    name: ${project}_default"$'\n'
done

cat > nginx.conf <<CONF
map \$cookie_tutor_account \$tutor_app {
    default $default;
$maps}

map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ""      close;
}

server {
    listen 80;
    absolute_redirect off;  # อยู่หลัง Cloudflare (https) ให้ redirect เป็น path ไม่ใส่ http:// เอง
    resolver 127.0.0.11 valid=10s ipv6=off;
    client_max_body_size 16m;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    location = /choose.html { root /usr/share/nginx/html; }
    location = /a/out {
        add_header Set-Cookie "tutor_account=; Path=/; Max-Age=0; SameSite=Lax; Secure; HttpOnly";
        return 302 /choose.html;
    }
    location ~ "^/a/([A-Za-z0-9-]+)$" {
        add_header Set-Cookie "tutor_account=\$1; Path=/; Max-Age=31536000; SameSite=Lax; Secure; HttpOnly";
        return 302 /;
    }
    location / {
        if (\$tutor_app = "") { return 302 /choose.html; }
        proxy_pass http://\$tutor_app:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
CONF

cat > docker-compose.yml <<COMPOSE
name: ai-tutor-gateway
services:
  web:
    image: nginx:1.27-alpine
    restart: unless-stopped
    mem_limit: 64m
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./choose.html:/usr/share/nginx/html/choose.html:ro
    networks:
      - default
$networks  quick:
    # ต่อแค่กับ nginx (เครือข่าย default) เพิ่มหรือลดบัญชีแล้ว tunnel ไม่เริ่มใหม่ ลิงก์จึงไม่เปลี่ยน
    image: cloudflare/cloudflared:2024.12.2
    restart: unless-stopped
    command: tunnel --no-autoupdate --url http://web:80
    depends_on:
      - web

networks:
  default:
$netdefs
COMPOSE

docker compose up -d
docker compose exec web nginx -t >/dev/null && docker compose exec web nginx -s reload
for _ in $(seq 1 20); do
  LINK=$(docker compose logs quick 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
  [ -n "$LINK" ] && break
  sleep 2
done
echo "ลิงก์เดียว: ${LINK:-ยังไม่ได้ลิงก์}"
for pair in "$@"; do [[ "$pair" == *=* ]] && echo "  ${pair#*=}: ${LINK:-<ลิงก์>}/a/${pair%%=*}"; done
true
