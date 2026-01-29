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
# 📂 静态资源与上传目录
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. 配置上传目录
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# 2. 配置前端目录
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

# 3. 挂载
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# =========================
# 根路径
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
# WebSocket (✨ 核心修改)
# =========================
@app.websocket("/ws/{conversation_id}")
async def ws_chat(
    ws: WebSocket, 
    conversation_id: int,
    token: str = Query(...)  # URL 参数带 token
):
    # 1. 鉴权
    uid = get_uid_by_token(token)
    if not uid or not is_member(uid, conversation_id):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. 建立连接
    await ws.accept()
    await ws_manager.join(conversation_id, ws, uid)

    # ✨ 提前查好当前用户的信息，方便发消息时带上头像
    current_user = get_user_by_id(uid)
    sender_avatar = current_user["avatar"] if current_user else None
    sender_username = current_user["username"] if current_user else f"User {uid}"

    # 3. 广播加入信息
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

            # 存库
            save_message(conversation_id, uid, content)

            # ✨ 4. 广播消息（带上头像和名字）
            await ws_manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender_uid": uid,
                "content": content,
                "device": detect_device(ws),
                # 新增字段
                "sender_avatar": sender_avatar,
                "sender_username": sender_username
            })

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.leave(conversation_id, ws)

# ... (保持前面的代码不变) ...

# =========================
# ✨ 新增：用户资料与好友 API
# =========================

@app.get("/api/users/{target_uid}/profile")
def api_get_user_profile(target_uid: int, token: str):
    try:
        my_uid = require_uid_from_token(token)
        
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                # 1. 查询目标用户信息
                cur.execute(
                    "SELECT id, username, avatar, gender, created_at FROM dreams_users WHERE id=%s",
                    (target_uid,)
                )
                user = cur.fetchone()
                if not user:
                    return JSONResponse({"error": "User not found"}, status_code=404)
                
                # 2. 查询是否已经是好友
                cur.execute(
                    "SELECT 1 FROM dreams_friends WHERE uid=%s AND friend_uid=%s",
                    (my_uid, target_uid)
                )
                is_friend = cur.fetchone() is not None

                # 3. 格式化注册时间
                created_at_str = user["created_at"].strftime("%Y-%m-%d") if user["created_at"] else "未知"

                return {
                    "uid": user["id"],
                    "username": user["username"],
                    "avatar": user["avatar"],
                    "gender": user["gender"],
                    "created_at": created_at_str,
                    "is_friend": is_friend,
                    "is_me": (my_uid == target_uid) # 标记是不是我自己
                }
        finally:
            conn.close()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/friends/add")
def api_add_friend(payload: dict):
    try:
        uid = require_uid_from_token(payload.get("token", ""))
        friend_uid = int(payload.get("friend_uid"))

        if uid == friend_uid:
            return JSONResponse({"error": "不能添加自己为好友"}, status_code=400)

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                # 双向添加好友 (你加他，他也加你)
                cur.execute(
                    "INSERT IGNORE INTO dreams_friends (uid, friend_uid) VALUES (%s, %s), (%s, %s)",
                    (uid, friend_uid, friend_uid, uid)
                )
                conn.commit()
            return {"ok": True}
        finally:
            conn.close()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
