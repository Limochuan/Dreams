from typing import Optional, List, Dict
from db import get_conn

def list_conversations(uid: int) -> List[Dict]:
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

def is_member(uid: int, conversation_id: int) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM dreams_conversation_members WHERE conversation_id=%s AND uid=%s",
                (conversation_id, uid),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()

def create_group(owner_uid: int, title: str) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dreams_conversations (type, title, owner_uid) VALUES ('group', %s, %s)",
                (title, owner_uid),
            )
            cid = cur.lastrowid
            cur.execute(
                "INSERT INTO dreams_conversation_members (conversation_id, uid, role) VALUES (%s, %s, 'owner')",
                (cid, owner_uid),
            )
            return cid
    finally:
        conn.close()

def _find_private_conversation(uid1: int, uid2: int) -> Optional[int]:
    """
    找一个 private 会话，且成员正好包含 uid1 和 uid2。
    简化写法：找出 uid1 的 private 会话，判断 uid2 是否也在同会话。
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id
                FROM dreams_conversations c
                JOIN dreams_conversation_members m1 ON c.id=m1.conversation_id AND m1.uid=%s
                JOIN dreams_conversation_members m2 ON c.id=m2.conversation_id AND m2.uid=%s
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
    if uid1 == uid2:
        raise ValueError("cannot create private conversation with yourself")

    existing = _find_private_conversation(uid1, uid2)
    if existing:
        return existing

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO dreams_conversations (type) VALUES ('private')")
            cid = cur.lastrowid
            cur.execute(
                "INSERT INTO dreams_conversation_members (conversation_id, uid, role) VALUES (%s, %s, 'member')",
                (cid, uid1),
            )
            cur.execute(
                "INSERT INTO dreams_conversation_members (conversation_id, uid, role) VALUES (%s, %s, 'member')",
                (cid, uid2),
            )
            return cid
    finally:
        conn.close()

def add_member(requester_uid: int, conversation_id: int, new_uid: int) -> None:
    """
    简化权限：只要 requester 是成员就允许拉人（你要严格权限我再加 owner/admin 判断）
    """
    if not is_member(requester_uid, conversation_id):
        raise PermissionError("not a member")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT IGNORE INTO dreams_conversation_members (conversation_id, uid, role)
                VALUES (%s, %s, 'member')
                """,
                (conversation_id, new_uid),
            )
    finally:
        conn.close()
