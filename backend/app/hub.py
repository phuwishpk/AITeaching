"""ส่งเหตุการณ์สดผ่าน WebSocket

ครูและ Admin รับทุกเหตุการณ์ (เห็นนักเรียนเป็น Student Code เท่านั้น ชื่อจริงอยู่ฝั่งครูใน Roster)
นักเรียนแต่ละคนรับเฉพาะเหตุการณ์ของตัวเอง เช่น คำใบ้พร้อมแล้ว หรือครูปลดล็อก
"""

import asyncio
import json

from fastapi import WebSocket


class Hub:
    def __init__(self):
        self.staff: set[WebSocket] = set()
        self.students: dict[str, set[WebSocket]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def join(self, ws: WebSocket, role: str, code: str | None):
        await ws.accept()
        self.loop = asyncio.get_running_loop()
        if role == "student" and code:
            self.students.setdefault(code, set()).add(ws)
        else:
            self.staff.add(ws)

    def leave(self, ws: WebSocket, role: str, code: str | None):
        if role == "student" and code:
            self.students.get(code, set()).discard(ws)
        else:
            self.staff.discard(ws)

    async def _send(self, targets: set[WebSocket], message: dict):
        text = json.dumps(message, ensure_ascii=False, default=str)
        dead = []
        for ws in list(targets):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            targets.discard(ws)

    async def to_staff(self, message: dict):
        await self._send(self.staff, message)

    async def to_student(self, code: str, message: dict):
        await self._send(self.students.get(code, set()), message)


hub = Hub()
