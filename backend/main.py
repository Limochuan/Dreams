import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from init_db import init_db
from auth import (
    register as reg_user, 
    login as login_user, 
    get_uid_by_token, 
    get_user_by_id
)
from conversations import (
    list_conversations, 
    create_private, 
    create_group, 
    add_member, 
    is_member
)
from messages import save_message, list_recent_messages
from ws import ws_manager, detect_device


# =========================
# FastAPI App
# =========================

app = FastAPI(title="Dreams Backend")


# =========================
# 数据库初始化
# =========================
init_db()


# =========================
# 📂 静态资源与上传目录 (核心修改)
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. 配置上传目录 (用来存图片)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# 2. 配置前端目录
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

# 3. 挂载上传目录：让 /uploads/xxx.png 可以被访问
app.mount(
    "/uploads",
    StaticFiles(directory=UPLOAD_DIR),
    name="uploads"
)

# 4. 挂载前端页面 (注意：/static 要放在最后或者非根路径，但在 heavy logic 中挂载根路径要小心覆盖 API)
# 这里我们把前端挂载到 /static，根路径做跳转
app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static"
)


# =========================
# 根路径：重定向到登录页
# =========================

@app.get("/")
def root():
    return RedirectResponse(url="/static/login.html")


# =========================
# 工具函数
# =========================

def require_uid_from_token(token: str) -> int:
    uid = get_uid_by_token(token)
    if not uid:
        raise PermissionError("invalid token")
    return uid


# =========================
# Auth API
# =========================

@app.post("/api/register")
def api_register(payload: dict):
    try:
        # 这里 reg_user 内部逻辑已经修改为保存文件了
        return reg_user(
            username=payload.get("username", "").strip(),
            password=payload.get("password", ""),
            avatar=payload.get("avatar"), # 传入 Base64
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/login")
def api_login(payload: dict):
    try:
        return login_user(
            username=payload.get("username", "").strip(),
            password=payload.get("password", ""),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/me")
def api_me(token: str):
    try:
        uid = require_uid_from_token(token)
        user = get_user_by_id(uid)
        if not user:
            return JSONResponse({"error": "user not found"}, status_code=404)
        return {
            "uid": user["id"],
            "username": user["username"],
            "avatar": user.get("avatar"), # 这里返回的已经是 URL 了
        }
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)


# =========================
# Conversations API
# =========================

@app.get("/api/conversations")
def api_list_conversations(token: str):
    try:
        uid = require_uid_from_token(token)
        return {"items": list_conversations(uid)}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)


@app.post("/api/conversations/private")
def api_create_private(payload: dict):
    try:
        uid = require_uid_from_token(payload.get("token", ""))
        peer_uid = int(payload.get("peer_uid"))
        cid = create_private(uid, peer_uid)
        return {"conversation_id": cid}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/conversations/group")
def api_create_group(payload: dict):
    try:
        uid = require_uid_from_token(payload.get("token", ""))
        title = (payload.get("title") or "").strip() or "New Group"
        cid = create_group(uid, title)
        return {"conversation_id": cid}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/conversations/{conversation_id}/members")
def api_add_member(conversation_id: int, payload: dict):
    try:
        uid = require_uid_from_token(payload.get("token", ""))
        new_uid = int(payload.get("new_uid"))
        add_member(uid, conversation_id, new_uid)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# =========================
# Messages API
# =========================

@app.get("/api/conversations/{conversation_id}/messages")
def api_list_messages(conversation_id: int, token: str, limit: int = 50):
    try:
        uid = require_uid_from_token(token)
        if not is_member(uid, conversation_id):
            return JSONResponse({"error": "not a member"}, status_code=403)
        return {"items": list_recent_messages(conversation_id, limit)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# =========================
# WebSocket
# =========================

@app.websocket("/ws/{conversation_id}")
async def ws_chat(
    ws: WebSocket, 
    conversation_id: int,
    token: str = Query(...) 
):
    uid = get_uid_by_token(token)
    
    if not uid or not is_member(uid, conversation_id):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws.accept()
    await ws_manager.join(conversation_id, ws, uid)

    await ws_manager.broadcast(conversation_id, {
        "type": "system",
        "event": "join",
        "uid": uid,
        "device": detect_device(ws),
    })

    try:
        while True:
            data = await ws.receive_text()
            try:
                frame = json.loads(data)
                content = (frame.get("content") or "").strip()
            except json.JSONDecodeError:
                continue

            if not content:
                continue

            save_message(conversation_id, uid, content)

            await ws_manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender_uid": uid,
                "content": content,
                "device": detect_device(ws),
            })

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.leave(conversation_id, ws)
