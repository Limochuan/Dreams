import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from init_db import init_db
from auth import register as reg_user, login as login_user, get_uid_by_token
from auth import get_user_by_id
from conversations import (
    list_conversations,
    create_private,
    create_group,
    add_member,
    is_member
)
from messages import save_message, list_recent_messages
from ws import ws_manager, detect_device

app = FastAPI(title="Dreams Backend")

# 启动时建表（你不想自动建表也可以删掉这行）
init_db()

# ----------- 工具：从 token 得到 uid -----------
def require_uid_from_token(token: str):
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
# Conversations
# =========================
@app.get("/api/conversations")
async def api_list_conversations(token: str):
    try:
        uid = require_uid_from_token(token)
        return {"items": list_conversations(uid)}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)

@app.post("/api/conversations/private")
async def api_create_private(payload: dict):
    """
    payload: { token, peer_uid }
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
    payload: { token, title }
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
    payload: { token, new_uid }
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
# Messages
# =========================
@app.get("/api/conversations/{conversation_id}/messages")
async def api_list_messages(conversation_id: int, token: str, limit: int = 50):
    try:
        uid = require_uid_from_token(token)
        if not is_member(uid, conversation_id):
            return JSONResponse({"error": "not a member"}, status_code=403)
        items = list_recent_messages(conversation_id, limit=limit)
        return {"items": items}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)

# =========================
# WebSocket (Realtime)
# =========================
@app.websocket("/ws/{conversation_id}")
async def ws_chat(ws: WebSocket, conversation_id: int):
    """
    客户端连接后第一条必须发：
      {"token":"..."}
    后续发：
      {"content":"hello"}
    服务端广播：
      {
        "type":"message",
        "conversation_id":...,
        "sender_uid":...,
        "content":...,
        "created_at": "...",
        "device":"mobile/desktop"
      }
    """
    await ws.accept()
    uid = None

    try:
        # 1) auth frame
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

        await ws_manager.join(conversation_id, ws, uid)

        # join notify（可选）
        await ws_manager.broadcast(conversation_id, {
            "type": "system",
            "event": "join",
            "uid": uid,
            "conversation_id": conversation_id,
            "device": detect_device(ws),
        })

        # 2) message loop
        while True:
            data = await ws.receive_text()
            try:
                frame = json.loads(data)
            except Exception:
                continue

            content = (frame.get("content") or "").strip()
            if not content:
                continue

            # save to DB
            save_message(conversation_id, uid, content)

            # broadcast
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
