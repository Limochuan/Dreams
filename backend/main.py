import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from init_db import init_db
from auth import register as reg_user, login as login_user, get_uid_by_token, get_user_by_id
from conversations import list_conversations, create_private, create_group, add_member, is_member
from messages import save_message, list_recent_messages
from ws import ws_manager, detect_device


app = FastAPI(title="Dreams Backend")

# =========================
# 静态前端挂载（绝对路径，防炸）
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# 强校验：不存在直接炸，方便你第一时间发现 Docker 问题
if not os.path.isdir(FRONTEND_DIR):
    raise RuntimeError(f"frontend directory not found: {FRONTEND_DIR}")

app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend"
)

@app.get("/")
async def root():
    return RedirectResponse("/login.html")

# =========================
# 数据库初始化
# =========================

init_db()

# =========================
# 工具函数
# =========================

def require_uid_from_token(token: str) -> int:
    uid = get_uid_by_token(token)
    if not uid:
        raise PermissionError("invalid token")
    return uid

# =========================
# Auth
# =========================

@app.post("/api/register")
async def api_register(payload: dict):
    try:
        return reg_user(
            username=payload.get("username", "").strip(),
            password=payload.get("password", ""),
            avatar=payload.get("avatar"),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.post("/api/login")
async def api_login(payload: dict):
    try:
        return login_user(
            username=payload.get("username", "").strip(),
            password=payload.get("password", ""),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.get("/api/me")
async def api_me(token: str):
    try:
        uid = require_uid_from_token(token)
        user = get_user_by_id(uid)
        return {
            "uid": user["id"],
            "username": user["username"],
            "avatar": user.get("avatar"),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=401)

# =========================
# 会话
# =========================

@app.get("/api/conversations")
async def api_list_conversations(token: str):
    try:
        uid = require_uid_from_token(token)
        return {"items": list_conversations(uid)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=401)

@app.post("/api/conversations/private")
async def api_create_private(payload: dict):
    uid = require_uid_from_token(payload["token"])
    cid = create_private(uid, int(payload["peer_uid"]))
    return {"conversation_id": cid}

@app.post("/api/conversations/group")
async def api_create_group(payload: dict):
    uid = require_uid_from_token(payload["token"])
    cid = create_group(uid, payload.get("title") or "New Group")
    return {"conversation_id": cid}

@app.post("/api/conversations/{conversation_id}/members")
async def api_add_member(conversation_id: int, payload: dict):
    uid = require_uid_from_token(payload["token"])
    add_member(uid, conversation_id, int(payload["new_uid"]))
    return {"ok": True}

# =========================
# 消息
# =========================

@app.get("/api/conversations/{conversation_id}/messages")
async def api_list_messages(conversation_id: int, token: str, limit: int = 50):
    uid = require_uid_from_token(token)
    if not is_member(uid, conversation_id):
        return JSONResponse({"error": "not a member"}, status_code=403)
    return {"items": list_recent_messages(conversation_id, limit)}

# =========================
# WebSocket
# =========================

@app.websocket("/ws/{conversation_id}")
async def ws_chat(ws: WebSocket, conversation_id: int):
    await ws.accept()
    uid = None
    try:
        auth = json.loads(await ws.receive_text())
        uid = get_uid_by_token(auth.get("token", ""))
        if not uid or not is_member(uid, conversation_id):
            await ws.close()
            return

        await ws_manager.join(conversation_id, ws, uid)

        await ws_manager.broadcast(conversation_id, {
            "type": "system",
            "event": "join",
            "uid": uid,
            "device": detect_device(ws),
        })

        while True:
            data = json.loads(await ws.receive_text())
            content = (data.get("content") or "").strip()
            if not content:
                continue

            save_message(conversation_id, uid, content)
            await ws_manager.broadcast(conversation_id, {
                "type": "message",
                "sender_uid": uid,
                "content": content,
                "device": detect_device(ws),
            })

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.leave(conversation_id, ws)
