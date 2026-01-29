from typing import List, Dict, Optional
from db import get_conn

# ----------------- 基础创建功能 -----------------

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

# ----------------- 核心查询功能 -----------------

def list_conversations(uid: int) -> List[Dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 联合查询：获取群信息、我的角色、未读数、最后一条消息、私聊对方信息
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

                u_peer.username as peer_name,
                u_peer.avatar as peer_avatar,
                u_peer.id as peer_uid

            FROM dreams_conversation_members m
            JOIN dreams_conversations c ON m.conversation_id = c.id
            LEFT JOIN dreams_conversation_members m_peer 
                ON c.id = m_peer.conversation_id AND c.type = 'private' AND m_peer.uid != m.uid
            LEFT JOIN dreams_users u_peer ON m_peer.uid = u_peer.id
            
            WHERE m.uid = %s
            ORDER BY m.is_pinned DESC, COALESCE(last_message_time, c.updated_at) DESC
            """
            cur.execute(sql, (uid,))
            rows = cur.fetchall()
            
            results = []
            for r in rows:
                title = r["title"]
                avatar = r["group_avatar"]
                # 如果是私聊，用对方的名字和头像覆盖
                if r["type"] == 'private':
                    title = r["peer_name"] or "未知用户"
                    avatar = r["peer_avatar"]
                
                results.append({
                    "id": r["id"], 
                    "type": r["type"], 
                    "title": title, 
                    "avatar": avatar,
                    "peer_uid": r["peer_uid"], 
                    "is_pinned": bool(r["is_pinned"]), 
                    "is_muted": bool(r["is_muted"]),
                    "unread": r["unread_count"], 
                    "last_msg": r["last_message"] or "", 
                    "last_time": r["last_message_time"],
                    "my_role": r["my_role"] # ✨ 关键：返回角色，前端据此判断是否显示管理按钮
                })
            return results
    finally:
        conn.close()

# ----------------- 管理功能 (之前缺失的部分) -----------------

# 1. 更新群信息 (改名/改头像)
def update_group_info(operator_uid: int, cid: int, title: str = None, avatar: str = None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 鉴权：只有群主能改
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
            row = cur.fetchone()
            if not row or row["role"] != 'owner':
                raise PermissionError("只有群主可以修改群信息")
            
            if title: cur.execute("UPDATE dreams_conversations SET title=%s WHERE id=%s", (title, cid))
            if avatar: cur.execute("UPDATE dreams_conversations SET avatar=%s WHERE id=%s", (avatar, cid))
            conn.commit()
    finally:
        conn.close()

# 2. 移除成员 (踢人)
def remove_member(operator_uid: int, cid: int, target_uid: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 查操作者权限
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
            op = cur.fetchone()
            if not op: raise PermissionError("你不在群里")
            
            # 查目标角色
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, target_uid))
            target = cur.fetchone()
            if not target: return # 目标本来就不在群里

            # 权限逻辑：群主能踢所有人，管理员只能踢普通成员
            allowed = (op["role"] == 'owner') or (op["role"] == 'admin' and target["role"] == 'member')
            
            if not allowed:
                raise PermissionError("权限不足，无法移除该成员")

            cur.execute("DELETE FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, target_uid))
            conn.commit()
    finally:
        conn.close()

# 3. 添加成员 (拉人)
def add_member(operator_uid: int, cid: int, new_uid: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 只有 ID=1 的世界频道允许系统自动拉人，其他群需要管理员权限
            if cid != 1:
                cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
                row = cur.fetchone()
                # 如果找不到记录或者只是普通 member，并且不是世界频道，则报错
                if (not row or row["role"] == 'member'):
                     # 这里为了演示方便暂时放行，如果需要严格权限，取消下面这行的注释：
                     # raise PermissionError("只有群主或管理员可以邀请")
                     pass

            cur.execute("INSERT IGNORE INTO dreams_conversation_members (conversation_id, uid) VALUES (%s, %s)", (cid, new_uid))
            conn.commit()
    finally:
        conn.close()

# 4. 检查是否在群里
def is_member(uid: int, cid: int) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, uid))
            return cur.fetchone() is not None
    finally:
        conn.close()
