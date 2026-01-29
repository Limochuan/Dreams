import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from auth import create_user, get_user, verify_password
from db import get_conn

app = FastAPI()

# ===== 注册 =====
@app.post("/api/register")
async def register(data: dict):
    user = get_user(data["username"])
    if user:
        return {"error": "user exists"}
    uid = create_user(data["username"], data["password"], data.get("avatar"))
    return {"uid": uid}

# ===== 登录 =====
@app.post("/api/login")
async def login(data: dict):
    user = get_user(data["username"])
    if not user:
        return {"error": "not found"}
    if not verify_password(data["password"], user["password_hash"]):
        return {"error": "wrong password"}
    return {"uid": user["id"], "avatar": user["avatar"]}

# ===== WebSocket（按会话）=====
connections = {}

@app.websocket("/ws/{conversation_id}")
async def ws_chat(ws: WebSocket, conversation_id: int):
    await ws.accept()
    connections.setdefault(conversation_id, []).append(ws)

    try:
        while True:
            msg = await ws.receive_text()
            for c in connections[conversation_id]:
                await c.send_text(msg)
    except WebSocketDisconnect:
        connections[conversation_id].remove(ws)

