from typing import List, Dict
from db import get_conn


def save_message(conversation_id: int, sender_uid: int, content: str) -> int:
    """
    保存一条聊天消息到数据库
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
            return cur.lastrowid
    finally:
        conn.close()


def list_recent_messages(conversation_id: int, limit: int = 50) -> List[Dict]:
    """
    获取指定会话的最近消息列表
    ✨ 核心修改：关联 dreams_users 表，获取头像(avatar)和用户名(username)
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    m.id, 
                    m.conversation_id, 
                    m.sender_uid, 
                    m.content, 
                    m.created_at,
                    u.username as sender_username,
                    u.avatar as sender_avatar
                FROM dreams_messages m
                LEFT JOIN dreams_users u ON m.sender_uid = u.id
                WHERE m.conversation_id=%s
                ORDER BY m.created_at DESC
                LIMIT %s
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()

            # 前端通常希望消息是从旧到新排列
            return list(reversed(rows))
    finally:
        conn.close()
