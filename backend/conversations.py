from typing import Optional, List, Dict
from db import get_conn


# =========================
# 会话列表
# =========================

def list_conversations(uid: int) -> List[Dict]:
    """
    获取某个用户参与的所有会话列表

    返回字段：
    - id: 会话 ID
    - type: private / group
    - title: 群聊标题（私聊通常为空）
    - owner_uid: 群主 uid（私聊通常为空）
    - created_at: 会话创建时间

    排序规则：
    - 按会话创建时间倒序
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.type, c.title, c.owner_uid, c.created_at
                FROM dreams_conversations c
                JOIN dreams_conversation_members m
                  ON c.id = m.conversation_id
                WHERE m.uid = %s
                ORDER BY c.created_at DESC
                """,
                (uid,),
            )
            return cur.fetchall()
    finally:
        conn.close()


# =========================
# 成员关系判断
# =========================

def is_member(uid: int, conversation_id: int) -> bool:
    """
    判断某个用户是否是指定会话的成员
    用于接口鉴权、WebSocket 鉴权等场景
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM dreams_conversation_members
                WHERE conversation_id=%s AND uid=%s
                """,
                (conversation_id, uid),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


# =========================
# 群聊创建
# =========================

def create_group(owner_uid: int, title: str) -> int:
    """
    创建一个群聊会话

    规则：
    - 创建者自动成为 owner
    - 创建后立即写入会话成员表

    返回新创建的 conversation_id
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 创建会话记录
            cur.execute(
                """
                INSERT INTO dreams_conversations (type, title, owner_uid)
                VALUES ('group', %s, %s)
                """,
                (title, owner_uid),
            )
            cid = cur.lastrowid

            # 创建者加入成员表，角色为 owner
            cur.execute(
                """
                INSERT INTO dreams_conversation_members
                (conversation_id, uid, role)
                VALUES (%s, %s, 'owner')
                """,
                (cid, owner_uid),
            )
            return cid
    finally:
        conn.close()


# =========================
# 私聊相关
# =========================

def _find_private_conversation(uid1: int, uid2: int) -> Optional[int]:
    """
    查找是否已经存在 uid1 和 uid2 之间的私聊会话

    逻辑：
    - 会话类型必须是 private
    - 两个用户必须同时是该会话的成员

    返回：
    - 存在则返回 conversation_id
    - 不存在则返回 None
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id
                FROM dreams_conversations c
                JOIN dreams_conversation_members m1
                  ON c.id = m1.conversation_id AND m1.uid=%s
                JOIN dreams_conversation_members m2
                  ON c.id = m2.conversation_id AND m2.uid=%s
                WHERE c.type='private'
                LIMIT 1
                """,
                (uid1, uid2),
            )
            row = cur.fetchone()
            return int(row["id"]) if row else None
    finally:
        conn.close()


def create_private(uid1: int, uid2: int) -> int:
    """
    创建私聊会话

    规则：
    - 不允许和自己创建私聊
    - 如果两人之间已存在私聊，直接复用
    - 否则新建 private 会话，并把双方加入成员表

    返回 conversation_id
    """
    if uid1 == uid2:
        raise ValueError("cannot create private conversation with yourself")

    existing = _find_private_conversation(uid1, uid2)
    if existing:
        return existing

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 创建私聊会话
            cur.execute(
                "INSERT INTO dreams_conversations (type) VALUES ('private')"
            )
            cid = cur.lastrowid

            # 两个用户加入会话成员表
            cur.execute(
                """
                INSERT INTO dreams_conversation_members
                (conversation_id, uid, role)
                VALUES (%s, %s, 'member')
                """,
                (cid, uid1),
            )
            cur.execute(
                """
                INSERT INTO dreams_conversation_members
                (conversation_id, uid, role)
                VALUES (%s, %s, 'member')
                """,
                (cid, uid2),
            )
            return cid
    finally:
        conn.close()


# =========================
# 群成员管理
# =========================

def add_member(requester_uid: int, conversation_id: int, new_uid: int) -> None:
    """
    向指定会话中添加新成员

    当前规则（简化版）：
    - 只要 requester 是该会话成员，就允许拉人
    - 不区分 owner / admin / member

    INSERT IGNORE 用于避免重复插入
    """
    if not is_member(requester_uid, conversation_id):
        raise PermissionError("not a member")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT IGNORE INTO dreams_conversation_members
                (conversation_id, uid, role)
                VALUES (%s, %s, 'member')
                """,
                (conversation_id, new_uid),
            )
    finally:
        conn.close()
