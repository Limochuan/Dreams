import bcrypt
import secrets
from typing import Optional, Dict
from db import get_conn


# =========================
# 内部工具函数：密码处理
# =========================

def _hash_password(password: str) -> str:
    """
    使用 bcrypt 对明文密码进行加密
    返回可直接存入数据库的字符串形式 hash
    """
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """
    校验用户输入的明文密码是否与数据库中的 hash 匹配
    """
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


# =========================
# 用户查询相关
# =========================

def get_user_by_username(username: str) -> Optional[Dict]:
    """
    通过 username 查询用户
    返回一整行用户记录（dict），不存在则返回 None
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dreams_users WHERE username=%s",
                (username,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(uid: int) -> Optional[Dict]:
    """
    通过 uid 查询用户
    常用于 token 校验后获取用户信息
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dreams_users WHERE id=%s",
                (uid,)
            )
            return cur.fetchone()
    finally:
        conn.close()


# =========================
# 用户创建
# =========================

def create_user(username: str, password: str, avatar: Optional[str]) -> int:
    """
    创建新用户
    - username: 用户名（必须唯一）
    - password: 明文密码（函数内部会自动加密）
    - avatar: 头像地址，可为空

    返回新用户的 uid（自增主键）
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dreams_users (username, password_hash, avatar)
                VALUES (%s, %s, %s)
                """,
                (username, _hash_password(password), avatar),
            )
            return cur.lastrowid
    finally:
        conn.close()


# =========================
# Session / Token 相关
# =========================

def issue_token(uid: int) -> str:
    """
    为指定用户签发一个新的登录 token
    token 会写入 dreams_sessions 表
    """
    token = secrets.token_urlsafe(32)  # 大约 43 个字符

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dreams_sessions (uid, token)
                VALUES (%s, %s)
                """,
                (uid, token),
            )
        return token
    finally:
        conn.close()


def get_uid_by_token(token: str) -> Optional[int]:
    """
    通过 token 反查 uid
    用于 HTTP API / WebSocket 的统一鉴权
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT uid
                FROM dreams_sessions
                WHERE token=%s
                """,
                (token,),
            )
            row = cur.fetchone()
            return int(row["uid"]) if row else None
    finally:
        conn.close()


# =========================
# 对外接口：注册 / 登录
# =========================

def register(username: str, password: str, avatar: Optional[str]) -> Dict:
    """
    用户注册流程：
    1. 校验参数
    2. 检查用户名是否已存在
    3. 创建用户
    4. 签发登录 token
    """
    if not username or not password:
        raise ValueError("username and password required")

    existing = get_user_by_username(username)
    if existing:
        raise ValueError("username already exists")

    uid = create_user(username, password, avatar)
    token = issue_token(uid)

    return {
        "uid": uid,
        "token": token
    }


def login(username: str, password: str) -> Dict:
    """
    用户登录流程：
    1. 校验参数
    2. 查询用户
    3. 校验密码
    4. 更新 last_login_at
    5. 签发新 token
    """
    if not username or not password:
        raise ValueError("username and password required")

    user = get_user_by_username(username)
    if not user:
        raise ValueError("user not found")

    if not _verify_password(password, user["password_hash"]):
        raise ValueError("wrong password")

    uid = int(user["id"])

    # 更新最近登录时间（非关键逻辑，失败不影响登录）
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dreams_users SET last_login_at=NOW() WHERE id=%s",
                (uid,)
            )
    finally:
        conn.close()

    token = issue_token(uid)

    return {
        "uid": uid,
        "token": token,
        "avatar": user.get("avatar")
    }
