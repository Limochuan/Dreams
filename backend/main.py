import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse


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
# FastAPI 应用入口
# =========================

app = FastAPI(title="Dreams Backend")
# =========================
# 前端静态文件挂载
# =========================

# frontend 目录结构：
# frontend/
#   ├─ login.html
#   ├─ conversations.html
#   ├─ chat.html
#   └─ app.js

app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend"
)

@app.get("/")
async def root():
    return RedirectResponse(url="/login.html")


# =========================
# 数据库初始化
# =========================
# 行为说明：
# - 启动时执行 init_db()
# - 会自动创建不存在的表
# - 不会修改已有表结构
# - 如果你不希望每次启动都触发，可直接删除这一行
init_db()


# =========================
# 工具函数
# =========================

def require_uid_from_token(token: str) -> int:
    """
    通过 token 获取 uid
    用于 HTTP API 的统一鉴权

    token 无效时抛出 PermissionError
    """
    uid = get_uid_by_token(token)
    if not uid:
        raise PermissionError("invalid token")
    return uid


# =========================
# Auth 相关接口
# =========================

@app.post("/api/register")
async def api_register(payload: dict):
    """
    用户注册接口

    payload:
    - username
    - password
    - avatar (可选)
    """
    try:
        out = reg_user(
            username=payload.get("username", "").strip(),
            password=payload.get("password", ""),
            avatar=payload.get("avatar"),
        )
        return out
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/login")
async def api_login(payload: dict):
    """
    用户登录接口

    payload:
    - username
    - password
    """
    try:
        out = login_user(
            username=payload.get("username", "").strip(),
            password=payload.get("password", ""),
        )
        return out
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/me")
async def api_me(token: str):
    """
    获取当前登录用户信息

    query:
    - token
    """
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
# 会话相关接口
# =========================

@app.get("/api/conversations")
async def api_list_conversations(token: str):
    """
    获取当前用户参与的所有会话列表
    """
    try:
        uid = require_uid_from_token(token)
        return {"items": list_conversations(uid)}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)


@app.post("/api/conversations/private")
async def api_create_private(payload: dict):
    """
    创建或获取私聊会话

    payload:
    - token
    - peer_uid
    """
    try:
        uid = require_uid_from_token(payload.get("token", ""))
        peer_uid = int(payload.get("peer_uid"))
        cid = create_private(uid, peer_uid)
        return {"conversation_id": cid}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/conversations/group")
async def api_create_group(payload: dict):
    """
    创建群聊会话

    payload:
    - token
    - title
    """
    try:
        uid = require_uid_from_token(payload.get("token", ""))
        title = (payload.get("title") or "").strip() or "New Group"
        cid = create_group(uid, title)
        return {"conversation_id": cid}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/conversations/{conversation_id}/members")
async def api_add_member(conversation_id: int, payload: dict):
    """
    向会话中添加新成员

    payload:
    - token
    - new_uid
    """
    try:
        uid = require_uid_from_token(payload.get("token", ""))
        new_uid = int(payload.get("new_uid"))
        add_member(uid, conversation_id, new_uid)
        return {"ok": True}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# =========================
# 消息相关接口
# =========================

@app.get("/api/conversations/{conversation_id}/messages")
async def api_list_messages(conversation_id: int, token: str, limit: int = 50):
    """
    获取指定会话的最近消息

    query:
    - token
    - limit (默认 50)
    """
    try:
        uid = require_uid_from_token(token)
        if not is_member(uid, conversation_id):
            return JSONResponse({"error": "not a member"}, status_code=403)

        items = list_recent_messages(conversation_id, limit=limit)
        return {"items": items}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)


# =========================
# WebSocket 实时聊天
# =========================

@app.websocket("/ws/{conversation_id}")
async def ws_chat(ws: WebSocket, conversation_id: int):
    """
    WebSocket 聊天接口

    客户端连接后第一条消息必须发送：
        {"token":"..."}

    后续消息格式：
        {"content":"hello"}

    服务端广播格式：
        {
            "type": "message / system",
            "conversation_id": ...,
            "sender_uid": ...,
            "content": ...,
            "device": "mobile / desktop"
        }
    """
    await ws.accept()
    uid = None

    try:
        # 1. 接收鉴权帧
        raw = await ws.receive_text()
        try:
            auth_frame = json.loads(raw)
        except Exception:
            await ws.close()
            return

        token = auth_frame.get("token", "")
        uid = get_uid_by_token(token)
        if not uid:
            await ws.close()
            return

        if not is_member(uid, conversation_id):
            await ws.close()
            return

        # 2. 加入 WebSocket 会话池
        await ws_manager.join(conversation_id, ws, uid)

        # 广播加入事件
        await ws_manager.broadcast(conversation_id, {
            "type": "system",
            "event": "join",
            "uid": uid,
            "conversation_id": conversation_id,
            "device": detect_device(ws),
        })

        # 3. 消息循环
        while True:
            data = await ws.receive_text()
            try:
                frame = json.loads(data)
            except Exception:
                continue

            content = (frame.get("content") or "").strip()
            if not content:
                continue

            # 保存消息到数据库
            save_message(conversation_id, uid, content)

            # 广播消息
            await ws_manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender_uid": uid,
                "content": content,
                "device": detect_device(ws),
            })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # 离开会话池并广播离开事件
        try:
            ws_manager.leave(conversation_id, ws)
            if uid:
                await ws_manager.broadcast(conversation_id, {
                    "type": "system",
                    "event": "leave",
                    "uid": uid,
                    "conversation_id": conversation_id,
                })
        except Exception:
            pass
