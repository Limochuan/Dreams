import json
from typing import Dict, List
from fastapi import WebSocket


def detect_device(ws: WebSocket) -> str:
    """
    根据 WebSocket 请求头中的 User-Agent 判断设备类型

    判断逻辑：
    - 如果 User-Agent 中包含常见移动端关键字，则认为是 mobile
    - 否则认为是 desktop

    返回值：
    - "mobile" 或 "desktop"
    """
    ua = (ws.headers.get("user-agent") or "").lower()
    if any(k in ua for k in ["iphone", "android", "ipad", "mobile"]):
        return "mobile"
    return "desktop"


class WSManager:
    """
    WebSocket 会话管理器

    内部结构说明：
    - self.rooms 是一个 dict
    - key: conversation_id
    - value: 一个 list，每一项代表一个在线连接

    list 中的每一项结构：
    {
        "ws": WebSocket 对象,
        "uid": 用户 ID,
        "device": "mobile" 或 "desktop"
    }

    说明：
    - 这个管理器只存在于内存中
    - 服务重启后，所有连接都会断开
    - 不做跨进程 / 多实例同步
    """

    def __init__(self):
        # 保存所有会话的在线 WebSocket 连接
        self.rooms: Dict[int, List[dict]] = {}

    async def join(self, conversation_id: int, ws: WebSocket, uid: int):
        """
        将一个 WebSocket 连接加入指定会话

        参数说明：
        - conversation_id: 会话 ID
        - ws: WebSocket 连接对象
        - uid: 当前用户 ID
        """
        device = detect_device(ws)

        # 如果该会话还没有房间，则先创建
        self.rooms.setdefault(conversation_id, []).append({
            "ws": ws,
            "uid": uid,
            "device": device
        })

    def leave(self, conversation_id: int, ws: WebSocket):
        """
        将 WebSocket 连接从会话中移除

        参数说明：
        - conversation_id: 会话 ID
        - ws: 要移除的 WebSocket 连接
        """
        if conversation_id not in self.rooms:
            return

        # 过滤掉当前 ws
        self.rooms[conversation_id] = [
            c for c in self.rooms[conversation_id]
            if c["ws"] != ws
        ]

        # 如果该会话已经没有任何在线连接，清理掉整个房间
        if not self.rooms[conversation_id]:
            del self.rooms[conversation_id]

    async def broadcast(self, conversation_id: int, payload: dict):
        """
        向指定会话内的所有在线连接广播消息

        参数说明：
        - conversation_id: 会话 ID
        - payload: 要发送的数据（dict，会被序列化成 JSON）

        行为说明：
        - 逐个向房间内的 WebSocket 发送消息
        - 如果某个连接发送失败，认为该连接已失效
        - 失效连接会被自动移除
        """
        if conversation_id not in self.rooms:
            return

        # 将消息序列化为 JSON 字符串
        msg = json.dumps(payload, ensure_ascii=False)

        dead = []

        # 尝试向所有连接发送消息
        for c in self.rooms[conversation_id]:
            try:
                await c["ws"].send_text(msg)
            except Exception:
                # 发送失败的连接，标记为失效
                dead.append(c["ws"])

        # 清理所有失效连接
        for ws in dead:
            self.leave(conversation_id, ws)


# 全局 WebSocket 管理器实例
# main.py 会直接引用这个对象
ws_manager = WSManager()
