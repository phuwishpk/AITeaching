"""ส่งเหตุการณ์สดผ่าน WebSocket

ครูและ Admin รับเหตุการณ์ของนักเรียนของตัวเอง (มีผู้ใช้หลายคน: scope.py) เห็นนักเรียนเป็น Student Code
ชื่อจริงอยู่ฝั่งครูใน Roster นักเรียนแต่ละคนรับเฉพาะเหตุการณ์ของตัวเอง เช่น คำใบ้พร้อมแล้ว หรือครูปลดล็อก
"""

import asyncio
import json

from fastapi import WebSocket

from . import scope, users


class Hub:
    def __init__(self):
        # ครูและ Admin: WebSocket → ชื่อผู้ใช้ (None ในโหมดเดิมที่ยังไม่มีบัญชีผู้ใช้)
        self.staff: dict[WebSocket, str | None] = {}
        self.students: dict[str, set[WebSocket]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def join(self, ws: WebSocket, role: str, code: str | None):
        await ws.accept()
        self.loop = asyncio.get_running_loop()
        if role == "student" and code:
            self.students.setdefault(code, set()).add(ws)
        else:
            self.staff[ws] = code

    def leave(self, ws: WebSocket, role: str, code: str | None):
        if role == "student" and code:
            self.students.get(code, set()).discard(ws)
        else:
            self.staff.pop(ws, None)

    async def _send(self, targets: list[WebSocket], message: dict) -> list[WebSocket]:
        text = json.dumps(message, ensure_ascii=False, default=str)
        dead = []
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        return dead

    async def to_staff(self, message: dict):
        """ส่งถึงเจ้าของนักเรียนในเหตุการณ์ (โหมดเดิมส่งถึงทุกคน)"""
        owner = scope.student_owner(message.get("code")) if users.exist() else None
        targets = [ws for ws, user in list(self.staff.items()) if user is None or user == owner]
        for ws in await self._send(targets, message):
            self.staff.pop(ws, None)

    async def to_student(self, code: str, message: dict):
        targets = self.students.get(code, set())
        for ws in await self._send(list(targets), message):
            targets.discard(ws)


hub = Hub()
