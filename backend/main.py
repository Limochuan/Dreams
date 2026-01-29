import json
import os
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional

# 假设这些是你的本地模块
from init_db import init_db
from auth import register as reg_user, login as login_user, get_uid_by_token, get_user_by_id
from conversations import list_conversations, create_private, create_group, add_member, is_member
from messages import save_message, list_recent_messages
from ws import ws_manager, detect_device

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DreamsBackend")

app = FastAPI(title="Dreams Backend")

# =========================
# 数据库初始化
# =========================
init_db()

# =========================
# 依赖注入：Token 校验
# =========================
# 将 Token 校验抽离，支持从 Header 或 Query 两种方式获取，提高复用性
def get_current_uid(token: Optional[str] = Query(None), authorization: Optional[str] = Header(None)) -> int:
    # 优先尝试从 Header 获取 (Bearer token)
    final_token = token
    if authorization and authorization.startswith("Bearer "):
        final_token = authorization.split(" ")[1]
    
    if not final_token:
        raise HTTPException(status_code=401, detail="Missing token")
    
    uid = get_uid_by_token(final_token)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return uid

# =========================
# API 路由 (必须在 StaticFiles 之前)
# =========================

@app.post("/api/register")
def api_register(payload: dict):
    """
    注意：这里去掉了 async，因为底层的数据库操作通常是同步的。
    FastAPI 会在外部线程池处理此类请求，防止阻塞主循环。
    """
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
def api_me(uid: int = Depends(get_current_uid)):
    user = get_user_by_id(uid)
    return {
        "uid": user["id"],
        "username": user["username"],
        "avatar": user.get("avatar"),
    }

@app.get("/api/conversations")
def api_list_conversations(uid: int = Depends(get_current_uid)):
    return {"items": list_conversations(uid)}

@app.post("/api/conversations/private")
def api_create_private(payload: dict, uid: int = Depends(get_current_uid)):
    cid = create_private(uid, int(payload["peer_uid"]))
    return {"conversation_id": cid}

@app.post("/api/conversations/group")
def api_create_group(payload: dict, uid: int = Depends(get_current_uid)):
    cid = create_group(uid, payload.get("title") or "New Group")
    return {"conversation_id": cid}

@app.post("/api/conversations/{conversation_id}/members")
def api_add_member(conversation_id: int, payload: dict, uid: int = Depends(get_current_uid)):
    # 只有已经在群里的人才能拉人（简单权限校验）
    if not is_member(uid, conversation_id):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    add_member(uid, conversation_id, int(payload["new_uid"]))
    return {"ok": True}

@app.get("/api/conversations/{conversation_id}/messages")
def api_list_messages(conversation_id: int, limit: int = 50, uid: int = Depends(get_current_uid)):
    if not is_member(uid, conversation_id):
        return JSONResponse({"error": "not a member"}, status_code=403)
    return {"items": list_recent_messages(conversation_id, limit)}

# =========================
# WebSocket 逻辑
# =========================

@app.websocket("/ws/{conversation_id}")
async def ws_chat(ws: WebSocket, conversation_id: int):
    # 1. 握手阶段：先接收一条认证消息
    await ws.accept()
    uid = None
    try:
        auth_data = await ws.receive_text()
        auth = json.loads(auth_data)
        token = auth.get("token")
        uid = get_uid_by_token(token)

        if not uid or not is_member(uid, conversation_id):
            logger.warning(f"WS Auth Failed for conversation {conversation_id}")
            await ws.send_text(json.dumps({"error": "Unauthorized"}))
            await ws.close(code=4003)
            return

        # 2. 加入管理器
        await ws_manager.join(conversation_id, ws, uid)
        
        # 3. 广播上线通知
        await ws_manager.broadcast(conversation_id, {
            "type": "system",
            "event": "join",
            "uid": uid,
            "device": detect_device(ws),
        })

        # 4. 消息循环
        while True:
            data = await ws.receive_text()
            msg_json = json.loads(data)
            content = (msg_json.get("content") or "").strip()
            
            if not content:
                continue

            # 保存到数据库（同步操作建议放在线程池中，或者确保 save_message 极快）
            save_message(conversation_id, uid, content)
            
            # 广播消息
            await ws_manager.broadcast(conversation_id, {
                "type": "message",
                "sender_uid": uid,
                "content": content,
                "device": detect_device(ws),
            })

    except WebSocketDisconnect:
        logger.info(f"User {uid} disconnected from {conversation_id}")
    except Exception as e:
        logger.error(f"WS Error: {e}")
    finally:
        if uid:
            ws_manager.leave(conversation_id, ws)

# =========================
# 静态前端挂载 (最后挂载，防止拦截 API)
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

if os.path.isdir(FRONTEND_DIR):
    # 根目录重定向到登录页
    @app.get("/")
    async def root():
        return RedirectResponse("/login.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logger.error(f"Frontend directory not found at {FRONTEND_DIR}. Static serving disabled.")

# 启动提示：使用 uvicorn main:app --reload 运行
