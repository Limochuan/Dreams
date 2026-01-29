import json
from typing import Dict, List
from fastapi import WebSocket

def detect_device(ws: WebSocket) -> str:
    ua = (ws.headers.get("user-agent") or "").lower()
    if any(k in ua for k in ["iphone", "android", "ipad", "mobile"]):
        return "mobile"
    return "desktop"

class WSManager:
    """
    conversation_id -> list of { ws, uid, device }
    """
    def __init__(self):
        self.rooms: Dict[int, List[dict]] = {}

    async def join(self, conversation_id: int, ws: WebSocket, uid: int):
        device = detect_device(ws)
        self.rooms.setdefault(conversation_id, []).append({
            "ws": ws,
            "uid": uid,
            "device": device
        })

    def leave(self, conversation_id: int, ws: WebSocket):
        if conversation_id not in self.rooms:
            return
        self.rooms[conversation_id] = [c for c in self.rooms[conversation_id] if c["ws"] != ws]
        if not self.rooms[conversation_id]:
            del self.rooms[conversation_id]

    async def broadcast(self, conversation_id: int, payload: dict):
        if conversation_id not in self.rooms:
            return
        msg = json.dumps(payload, ensure_ascii=False)

        dead = []
        for c in self.rooms[conversation_id]:
            try:
                await c["ws"].send_text(msg)
            except Exception:
                dead.append(c["ws"])

        for ws in dead:
            self.leave(conversation_id, ws)

ws_manager = WSManager()
