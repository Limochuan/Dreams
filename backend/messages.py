from typing import List, Dict
from db import get_conn


def save_message(conversation_id: int, sender_uid: int, content: str) -> int:
    """
    保存一条聊天消息到数据库

    参数说明：
    - conversation_id: 会话 ID
    - sender_uid: 发送者用户 ID
    - content: 消息内容（纯文本）

    返回值：
    - 新插入消息的自增 ID
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dreams_messages (conversation_id, sender_uid, content)
                VALUES (%s, %s, %s)
                """,
                (conversation_id, sender_uid, content),
            )
            # lastrowid 是数据库生成的消息 ID
            return cur.lastrowid
    finally:
        # 无论是否异常，都确保连接被关闭
        conn.close()


def list_recent_messages(conversation_id: int, limit: int = 50) -> List[Dict]:
    """
    获取指定会话的最近消息列表

    参数说明：
    - conversation_id: 会话 ID
    - limit: 返回的最大消息条数，默认 50

    返回值：
    - 消息列表，每条消息是一个 dict
      包含字段：
        id
        conversation_id
        sender_uid
        content
        created_at

    说明：
    - 数据库中按 created_at DESC 查询（最新的在前）
    - 返回前会反转顺序，变为时间正序，方便前端直接渲染
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, conversation_id, sender_uid, content, created_at
                FROM dreams_messages
                WHERE conversation_id=%s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()

            # 前端通常希望消息是从旧到新排列
            return list(reversed(rows))
    finally:
        # 关闭数据库连接
        conn.close()
