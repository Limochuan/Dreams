from typing import List, Dict, Optional
from db import get_conn

# ================= 1. 基础创建 =================

def create_private(uid1: int, uid2: int) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 检查私聊是否已存在
            cur.execute("""
                SELECT c.id FROM dreams_conversations c
                JOIN dreams_conversation_members m1 ON c.id = m1.conversation_id
                JOIN dreams_conversation_members m2 ON c.id = m2.conversation_id
                WHERE c.type = 'private' AND m1.uid = %s AND m2.uid = %s
            """, (uid1, uid2))
            existing = cur.fetchone()
            if existing: return existing["id"]

            # 创建新私聊
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
            # 创建群并指定群主
            cur.execute("INSERT INTO dreams_conversations (type, title, owner_uid) VALUES ('group', %s, %s)", (title, owner_uid))
            cid = cur.lastrowid
            cur.execute("INSERT INTO dreams_conversation_members (conversation_id, uid, role) VALUES (%s, %s, 'owner')", (cid, owner_uid))
            conn.commit()
            return cid
    finally:
        conn.close()

# ================= 2. 列表查询 (核心修复) =================

def list_conversations(uid: int) -> List[Dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 💡 核心修复：
            # 在 JOIN 时更严格地筛选 m_peer.uid != uid，确保查出的 peer_name 绝对不是自己
            sql = """
            SELECT 
                c.id, c.type, c.title, c.avatar as group_avatar, c.updated_at,
                m.is_pinned, m.is_muted, m.last_read_at, m.role as my_role,
                
                (SELECT COUNT(*) FROM dreams_messages msg 
                 WHERE msg.conversation_id = c.id AND msg.created_at > m.last_read_at
                ) as unread_count,
                
                (SELECT content FROM dreams_messages msg 
                 WHERE msg.conversation_id = c.id ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message,
                
                (SELECT created_at FROM dreams_messages msg 
                 WHERE msg.conversation_id = c.id ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_time,

                -- 对方的信息
                u_peer.username as peer_name,
                u_peer.avatar as peer_avatar,
                u_peer.id as peer_uid

            FROM dreams_conversation_members m
            JOIN dreams_conversations c ON m.conversation_id = c.id
            
            -- 尝试查找私聊的“另一方”
            -- 条件：同会话ID + 类型是private + 用户ID不等于我自己
            LEFT JOIN dreams_conversation_members m_peer 
                ON c.id = m_peer.conversation_id 
                AND c.type = 'private' 
                AND m_peer.uid != %s  -- 这里直接用参数排除自己
                
            LEFT JOIN dreams_users u_peer ON m_peer.uid = u_peer.id
            
            WHERE m.uid = %s
            ORDER BY m.is_pinned DESC, COALESCE(last_message_time, c.updated_at) DESC
            """
            # 注意：这里传了两次 uid，一次给 JOIN 里的排除条件，一次给 WHERE
            cur.execute(sql, (uid, uid))
            rows = cur.fetchall()
            
            results = []
            for r in rows:
                display_title = r["title"]
                display_avatar = r["group_avatar"]
                
                # 如果是私聊，强制使用对方的名字和头像
                if r["type"] == 'private':
                    # 如果 peer_name 查出来是空，说明数据可能异常，或者对方注销了
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
                    "last_time": r["last_message_time"],
                    "my_role": r["my_role"]
                })
            return results
    finally:
        conn.close()

# ================= 3. 管理功能 =================

def update_group_info(operator_uid: int, cid: int, title: str = None, avatar: str = None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
            row = cur.fetchone()
            if not row or row["role"] != 'owner':
                raise PermissionError("只有群主可以修改群信息")
            
            if title: cur.execute("UPDATE dreams_conversations SET title=%s WHERE id=%s", (title, cid))
            if avatar: cur.execute("UPDATE dreams_conversations SET avatar=%s WHERE id=%s", (avatar, cid))
            conn.commit()
    finally:
        conn.close()

def remove_member(operator_uid: int, cid: int, target_uid: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
            op = cur.fetchone()
            if not op: raise PermissionError("你不在群里")
            
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, target_uid))
            target = cur.fetchone()
            if not target: return 

            allowed = (op["role"] == 'owner') or (op["role"] == 'admin' and target["role"] == 'member')
            if not allowed:
                raise PermissionError("权限不足，无法移除该成员")

            cur.execute("DELETE FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, target_uid))
            conn.commit()
    finally:
        conn.close()

def add_member(operator_uid: int, cid: int, new_uid: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if cid != 1:
                cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
                row = cur.fetchone()
                if not row: pass 

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
