# Adaptive Tutor ในคอนเทนเนอร์เดียว: build หน้าเว็บด้วย Node แล้วเสิร์ฟทั้ง API และหน้าเว็บด้วย uvicorn
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
EXPOSE 8000
# worker เดียวเท่านั้น: WebSocket คิวงานสร้าง Gem และดัชนีเอกสารอยู่ในหน่วยความจำของ process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
