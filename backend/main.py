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
# 启动时检查表是否存在，并确保世界频道存在
init_db()


# =========================
# 静态前端目录
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 假设前端在 backend 的上一级目录的 frontend 文件夹中
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

if not os.path.exists(FRONTEND_DIR):
    print(f"Warning: Frontend directory not found at {FRONTEND_DIR}")

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
# Auth API (注意：去掉了 async)
# =========================

@app.post("/api/register")
def api_register(payload: dict):
    try:
        return reg_user(
            username=payload.get("username", "").strip(),
            password=payload.get("password", ""),
            avatar=payload.get("avatar"),
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
            "avatar": user.get("avatar"),
        }
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)


# =========================
# Conversations API (注意：去掉了 async)
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
# Messages API (注意：去掉了 async)
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
# WebSocket (核心：保持 async，并加上了握手验证)
# =========================

@app.websocket("/ws/{conversation_id}")
async def ws_chat(
    ws: WebSocket, 
    conversation_id: int,
    token: str = Query(...)  # ✅ 从 URL 参数中获取 token
):
    # 1. 握手前验证：如果 token 无效，直接拒绝连接
    uid = get_uid_by_token(token)
    
    # 因为 is_member 内部查库是同步的，为了不阻塞 WS 握手，
    # 严格来说这里应该在线程池跑，但为了简化代码，
    # 且 is_member 查询非常快，这里直接调用影响不大。
    # 如果追求极致性能，可以用 run_in_executor。
    if not uid or not is_member(uid, conversation_id):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. 验证通过，建立连接
    await ws.accept()
    
    # 3. 加入管理器
    await ws_manager.join(conversation_id, ws, uid)

    # 4. 广播“加入房间”事件
    await ws_manager.broadcast(conversation_id, {
        "type": "system",
        "event": "join",
        "uid": uid,
        "device": detect_device(ws),
    })

    try:
        while True:
            # 等待接收消息
            data = await ws.receive_text()
            
            # 尝试解析 JSON
            try:
                frame = json.loads(data)
                content = (frame.get("content") or "").strip()
            except json.JSONDecodeError:
                continue

            if not content:
                continue

            # 5. 保存消息到数据库 (注意：这里在 async 里调同步 DB 函数)
            # 虽然 save_message 是同步的，但对聊天体验影响在毫秒级，Demo 可接受
            # 完美做法是: await loop.run_in_executor(None, save_message, ...)
            save_message(conversation_id, uid, content)

            # 6. 广播消息
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
        # 7. 断开清理
        ws_manager.leave(conversation_id, ws)
