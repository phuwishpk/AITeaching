import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// ตอนพัฒนา: Vite (5173) ส่งต่อ /api และ /ws ไปที่ FastAPI (8000)
// วันสาธิต: npm run build แล้ว FastAPI เสิร์ฟไฟล์ใน dist/ เอง
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
