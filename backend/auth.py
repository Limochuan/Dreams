import bcrypt
import secrets
import time
from typing import Optional, Dict
from db import get_conn

# =========================
# 内部工具函数
# =========================

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

# =========================
# 用户查询
# =========================

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

# =========================
# 用户创建 (含 Gender)
# =========================

def create_user(username: str, password: str, avatar: Optional[str], gender: str = 'secret') -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # ✨ 核心修改：直接把 avatar (Base64字符串) 存入数据库
            # 不需要 save_avatar_file 了，因为数据库已经够大了 (LONGTEXT)
            cur.execute(
                """
                INSERT INTO dreams_users (username, password_hash, avatar, gender)
                VALUES (%s, %s, %s, %s)
                """,
                (username, _hash_password(password), avatar, gender),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()

# =========================
# Token 管理
# =========================

def issue_token(uid: int) -> str:
    token = secrets.token_urlsafe(32)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dreams_sessions (uid, token) VALUES (%s, %s)",
                (uid, token),
            )
            conn.commit()
        return token
    finally:
        conn.close()

def get_uid_by_token(token: str) -> Optional[int]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT uid FROM dreams_sessions WHERE token=%s", (token,))
            row = cur.fetchone()
            return int(row["uid"]) if row else None
    finally:
        conn.close()

# =========================
# 对外接口：注册 / 登录
# =========================

def register(username: str, password: str, avatar: Optional[str], gender: str = 'secret') -> Dict:
    if not username or not password:
        raise ValueError("username and password required")

    existing = get_user_by_username(username)
    if existing:
        raise ValueError("username already exists")

    # 1. 创建用户 (Base64 直接存库，不再存文件)
    uid = create_user(username, password, avatar, gender)
    
    # 2. 签发 Token
    token = issue_token(uid)

    # 3. 自动加入世界频道
    # 使用 try-except 防止因 import 循环或群不存在导致注册失败
    try:
        from conversations import add_member
        # 参数说明: operator_uid=1 (群主操作), cid=1 (世界频道), new_uid=uid (新注册用户)
        # 强制用 UID 1 把新人拉进群，避免权限问题
        add_member(1, 1, uid) 
    except Exception as e:
        print(f"Auto-join world channel failed: {e}")

    return {
        "uid": uid,
        "token": token,
        "avatar": avatar, # 直接返回 Base64 供前端立即显示
        "gender": gender
    }

def login(username: str, password: str) -> Dict:
    if not username or not password:
        raise ValueError("username and password required")

    user = get_user_by_username(username)
    if not user:
        raise ValueError("user not found")

    if not _verify_password(password, user["password_hash"]):
        raise ValueError("wrong password")

    uid = int(user["id"])

    # 更新登录时间
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE dreams_users SET last_login_at=NOW() WHERE id=%s", (uid,))
            conn.commit()
    finally:
        conn.close()

    token = issue_token(uid)

    return {
        "uid": uid,
        "token": token,
        "avatar": user.get("avatar")
    }
