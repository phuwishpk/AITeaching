"""จุดเริ่มของ backend: FastAPI เซิร์ฟเวอร์เดียว ทำทั้ง REST, WebSocket และเสิร์ฟหน้าเว็บ

รัน: uvicorn app.main:app --port 8000 (จากโฟลเดอร์ backend)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, seed, services
from .api import admin, auth, gems, rules, student, teacher
from .api.deps import resolve_token
from .config import FRONTEND_DIST
from .hub import hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    seed.ensure_seed()
    yield


app = FastAPI(title="Adaptive Tutor", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(student.router)
app.include_router(teacher.router)
app.include_router(gems.router)
app.include_router(admin.router)
app.include_router(rules.router)


@app.exception_handler(services.NotFound)
async def not_found(request: Request, error: services.NotFound):
    return JSONResponse({"detail": str(error)}, status_code=404)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.websocket("/ws")
async def websocket(ws: WebSocket, token: str = ""):
    identity = resolve_token(token)
    if not identity:
        await ws.close(code=4401)
        return
    role, code = identity["role"], identity.get("code")
    await hub.join(ws, role, code)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.leave(ws, role, code)


if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """หน้าเว็บที่ build แล้ว ทุกเส้นทางที่ไม่ใช่ API ส่ง index.html (React Router จัดการต่อ)
    ส่งไฟล์ได้เฉพาะที่อยู่ใน dist จริง กัน path อย่าง ../../runtime/secrets.json"""
    root = FRONTEND_DIST.resolve()
    file = (root / path).resolve()
    if path and file.is_relative_to(root) and file.is_file():
        return FileResponse(file)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        # build ใหม่แล้วชื่อไฟล์ใน assets เปลี่ยน เบราว์เซอร์จึงต้องโหลด index.html ใหม่ทุกครั้ง
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "ยังไม่ได้ build หน้าเว็บ: cd frontend && npm run build"}, status_code=503)
