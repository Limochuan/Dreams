from typing import List, Dict
from db import get_conn

def save_message(conversation_id: int, sender_uid: int, content: str) -> int:
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
            # 前端通常想按时间正序显示
            return list(reversed(rows))
    finally:
        conn.close()
