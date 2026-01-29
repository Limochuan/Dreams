from typing import List, Dict, Optional
from db import get_conn

def create_private(uid1: int, uid2: int) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 检查是否已存在私聊
            cur.execute(
                """
                SELECT c.id FROM dreams_conversations c
                JOIN dreams_conversation_members m1 ON c.id = m1.conversation_id
                JOIN dreams_conversation_members m2 ON c.id = m2.conversation_id
                WHERE c.type = 'private' AND m1.uid = %s AND m2.uid = %s
                """,
                (uid1, uid2)
            )
            existing = cur.fetchone()
            if existing:
                return existing["id"]

            cur.execute("INSERT INTO dreams_conversations (type) VALUES ('private')")
            cid = cur.lastrowid
            
            cur.execute("INSERT INTO dreams_conversation_members (conversation_id, uid) VALUES (%s, %s), (%s, %s)", (cid, uid1, cid, uid2))
            conn.commit()
            return cid
    finally:
        conn.close()

def create_group(owner_uid: int, title: str) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO dreams_conversations (type, title, owner_uid) VALUES ('group', %s, %s)", (title, owner_uid))
            cid = cur.lastrowid
            cur.execute("INSERT INTO dreams_conversation_members (conversation_id, uid, role) VALUES (%s, %s, 'owner')", (cid, owner_uid, cid))
            conn.commit()
            return cid
    finally:
        conn.close()

# ✨ 核心升级：智能列表查询
def list_conversations(uid: int) -> List[Dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 这个 SQL 比较复杂，它做了三件事：
            # 1. 查出会话基本信息 + 我在群里的设置 (置顶/免打扰/上次阅读时间)
            # 2. 统计未读消息数 (count messages > last_read_at)
            # 3. 如果是私聊，查出对方的 username 和 avatar
            sql = """
            SELECT 
                c.id, c.type, c.title, c.updated_at,
                m.is_pinned, m.is_muted, m.last_read_at,
                
                (SELECT COUNT(*) FROM dreams_messages msg 
                 WHERE msg.conversation_id = c.id 
                 AND msg.created_at > m.last_read_at
                ) as unread_count,
                
                (SELECT content FROM dreams_messages msg 
                 WHERE msg.conversation_id = c.id 
                 ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message,
                
                (SELECT created_at FROM dreams_messages msg 
                 WHERE msg.conversation_id = c.id 
                 ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_time,

                -- 查找私聊对象的头像和名字 (仅当 type=private 时有效)
                u_peer.username as peer_name,
                u_peer.avatar as peer_avatar,
                u_peer.id as peer_uid

            FROM dreams_conversation_members m
            JOIN dreams_conversations c ON m.conversation_id = c.id
            -- 尝试连接私聊的另一个人 (self join)
            LEFT JOIN dreams_conversation_members m_peer 
                ON c.id = m_peer.conversation_id 
                AND c.type = 'private' 
                AND m_peer.uid != m.uid
            LEFT JOIN dreams_users u_peer ON m_peer.uid = u_peer.id
            
            WHERE m.uid = %s
            -- 排序：置顶优先 -> 最新消息时间 -> 会话更新时间
            ORDER BY m.is_pinned DESC, COALESCE(last_message_time, c.updated_at) DESC
            """
            cur.execute(sql, (uid,))
            rows = cur.fetchall()
            
            results = []
            for r in rows:
                display_title = r["title"]
                display_avatar = None
                
                # 如果是私聊，且标题为空，就显示对方名字
                if r["type"] == 'private':
                    display_title = r["peer_name"] or "未知用户"
                    display_avatar = r["peer_avatar"]
                
                results.append({
                    "id": r["id"],
                    "type": r["type"],
                    "title": display_title,
                    "avatar": display_avatar,
                    "peer_uid": r["peer_uid"],
                    "is_pinned": bool(r["is_pinned"]),
                    "is_muted": bool(r["is_muted"]),
                    "unread": r["unread_count"],
                    "last_msg": r["last_message"] or "",
                    "last_time": r["last_message_time"]
                })
            return results
    finally:
        conn.close()

def add_member(operator_uid: int, cid: int, new_uid: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO dreams_conversation_members (conversation_id, uid) VALUES (%s, %s)", (cid, new_uid))
            conn.commit()
    finally:
        conn.close()

def is_member(uid: int, cid: int) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, uid))
            return cur.fetchone() is not None
    finally:
        conn.close()
