import bcrypt
import secrets
from typing import Optional, Dict
from db import get_conn

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

def get_user_by_username(username: str) -> Optional[Dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dreams_users WHERE username=%s", (username,))
            return cur.fetchone()
    finally:
        conn.close()

def get_user_by_id(uid: int) -> Optional[Dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dreams_users WHERE id=%s", (uid,))
            return cur.fetchone()
    finally:
        conn.close()

def create_user(username: str, password: str, avatar: Optional[str]) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dreams_users (username, password_hash, avatar) VALUES (%s,%s,%s)",
                (username, _hash_password(password), avatar),
            )
            return cur.lastrowid
    finally:
        conn.close()

def issue_token(uid: int) -> str:
    token = secrets.token_urlsafe(32)  # 43~ chars
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dreams_sessions (uid, token) VALUES (%s,%s)",
                (uid, token),
            )
        return token
    finally:
        conn.close()

def get_uid_by_token(token: str) -> Optional[int]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT uid FROM dreams_sessions WHERE token=%s",
                (token,),
            )
            row = cur.fetchone()
            return int(row["uid"]) if row else None
    finally:
        conn.close()

def register(username: str, password: str, avatar: Optional[str]) -> Dict:
    if not username or not password:
        raise ValueError("username and password required")
    existing = get_user_by_username(username)
    if existing:
        raise ValueError("username already exists")

    uid = create_user(username, password, avatar)
    token = issue_token(uid)
    return {"uid": uid, "token": token}

def login(username: str, password: str) -> Dict:
    if not username or not password:
        raise ValueError("username and password required")

    user = get_user_by_username(username)
    if not user:
        raise ValueError("user not found")

    if not _verify_password(password, user["password_hash"]):
        raise ValueError("wrong password")

    uid = int(user["id"])

    # 更新 last_login_at（可选）
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE dreams_users SET last_login_at=NOW() WHERE id=%s", (uid,))
    finally:
        conn.close()

    token = issue_token(uid)
    return {"uid": uid, "token": token, "avatar": user.get("avatar")}
