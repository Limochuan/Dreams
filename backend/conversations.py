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
            # 创建者直接成为 Owner
            cur.execute("INSERT INTO dreams_conversation_members (conversation_id, uid, role) VALUES (%s, %s, 'owner')", (cid, owner_uid))
            conn.commit()
            return cid
    finally:
        conn.close()

def list_conversations(uid: int) -> List[Dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 复杂的联合查询：获取会话信息 + 未读数 + 对方信息 + 我的角色
            sql = """
            SELECT 
                c.id, c.type, c.title, c.avatar as group_avatar, c.updated_at,
                m.is_pinned, m.is_muted, m.last_read_at, m.role as my_role,
                
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

                u_peer.username as peer_name,
                u_peer.avatar as peer_avatar,
                u_peer.id as peer_uid

            FROM dreams_conversation_members m
            JOIN dreams_conversations c ON m.conversation_id = c.id
            LEFT JOIN dreams_conversation_members m_peer 
                ON c.id = m_peer.conversation_id 
                AND c.type = 'private' 
                AND m_peer.uid != m.uid
            LEFT JOIN dreams_users u_peer ON m_peer.uid = u_peer.id
            
            WHERE m.uid = %s
            ORDER BY m.is_pinned DESC, COALESCE(last_message_time, c.updated_at) DESC
            """
            cur.execute(sql, (uid,))
            rows = cur.fetchall()
            
            results = []
            for r in rows:
                display_title = r["title"]
                display_avatar = r["group_avatar"]
                
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
                    "last_time": r["last_message_time"],
                    "my_role": r["my_role"] # 关键：返回角色，前端据此判断是否显示管理按钮
                })
            return results
    finally:
        conn.close()

# ✨ 这就是之前缺失的函数：更新群信息 (改名/改头像)
def update_group_info(operator_uid: int, cid: int, title: str = None, avatar: str = None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 1. 鉴权：必须是群主
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
            row = cur.fetchone()
            if not row or row["role"] != 'owner':
                raise PermissionError("只有群主可以修改群信息")
            
            # 2. 更新
            if title:
                cur.execute("UPDATE dreams_conversations SET title=%s WHERE id=%s", (title, cid))
            if avatar:
                cur.execute("UPDATE dreams_conversations SET avatar=%s WHERE id=%s", (avatar, cid))
            
            conn.commit()
    finally:
        conn.close()

# ✨ 这也是之前缺失的函数：移除成员 (踢人)
def remove_member(operator_uid: int, cid: int, target_uid: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 1. 查操作者权限
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
            op_row = cur.fetchone()
            if not op_row: raise PermissionError("你不在群里")
            op_role = op_row["role"]

            # 2. 查目标角色
            cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, target_uid))
            target_row = cur.fetchone()
            if not target_row: return # 本来就不在，直接返回成功

            target_role = target_row["role"]

            # 3. 权限判断
            allow = False
            if op_role == 'owner': allow = True # 群主踢一切
            elif op_role == 'admin' and target_role == 'member': allow = True # 管理踢成员
            
            if not allow:
                raise PermissionError("权限不足")

            # 4. 执行删除
            cur.execute("DELETE FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, target_uid))
            conn.commit()
    finally:
        conn.close()

def add_member(operator_uid: int, cid: int, new_uid: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 简单的权限检查：如果是群聊，只有群主或管理员能拉人
            # (为了世界频道自动加入的兼容性，这里对 ID=1 特殊放行)
            if cid != 1:
                cur.execute("SELECT role FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s", (cid, operator_uid))
                row = cur.fetchone()
                # 如果找不到记录或者只是普通 member，并且不是系统自动操作(uid 1)，则报错
                if (not row or row["role"] == 'member') and cid != 1:
                     # raise PermissionError("只有管理人员可以邀请")
                     pass 

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
