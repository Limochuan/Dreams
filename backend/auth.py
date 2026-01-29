import bcrypt
import secrets
import base64
import os
import time
from typing import Optional, Dict
from db import get_conn

# =========================
# 内部工具函数：密码处理
# =========================

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


# =========================
# 内部工具函数：头像文件保存
# =========================

def save_avatar_file(uid: int, base64_str: str) -> Optional[str]:
    """
    将 base64 字符串保存为本地图片文件
    返回：相对 URL 路径 (例如 /uploads/1_163822.png)
    """
    if not base64_str or "," not in base64_str:
        return None
    
    try:
        # 1. 解析 Base64
        header, data = base64_str.split(",", 1)
        
        # 2. 确定扩展名
        ext = ".png"
        if "jpeg" in header or "jpg" in header:
            ext = ".jpg"
        elif "gif" in header:
            ext = ".gif"

        # 3. 确定保存目录 (确保和 main.py 里的 UPLOAD_DIR 对应)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        uploads_dir = os.path.join(current_dir, "uploads")
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir)
            
        # 4. 生成文件名 (uid + 时间戳)
        filename = f"{uid}_{int(time.time())}{ext}"
        filepath = os.path.join(uploads_dir, filename)
        
        # 5. 写入文件
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(data))
            
        # 6. 返回给前端的访问路径
        return f"/uploads/{filename}"
        
    except Exception as e:
        print(f"Error saving avatar: {e}")
        return None


# =========================
# 用户查询相关
# =========================

def get_user_by_username(username: str) -> Optional[Dict]:
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
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


# =========================
# Session / Token 相关
# =========================

def issue_token(uid: int) -> str:
    token = secrets.token_urlsafe(32)
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
            conn.commit()
        return token
    finally:
        conn.close()


def get_uid_by_token(token: str) -> Optional[int]:
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
    注册流程：
    1. 校验 -> 2. 建用户(avatar暂空) -> 3. 存图片 -> 4. 更新URL -> 5. 发Token -> 6. 加群
    """
    if not username or not password:
        raise ValueError("username and password required")

    existing = get_user_by_username(username)
    if existing:
        raise ValueError("username already exists")

    # 1. 先创建用户，此时 avatar 传 None，因为我们还没生成 URL
    uid = create_user(username, password, None)
    
    avatar_url = None
    
    # 2. 如果前端传了 Base64 图片，进行保存
    if avatar:
        avatar_url = save_avatar_file(uid, avatar)
        
        # 如果保存成功，更新数据库里的 avatar 字段为 URL
        if avatar_url:
            conn = get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE dreams_users SET avatar=%s WHERE id=%s",
                        (avatar_url, uid)
                    )
                    conn.commit()
            finally:
                conn.close()

    # 3. 签发 Token
    token = issue_token(uid)

    # 4. 自动加入世界频道
    try:
        from conversations import add_member
        add_member(uid, 1, uid)
    except Exception as e:
        print(f"Warning: Failed to add user to World Channel: {e}")

    return {
        "uid": uid,
        "token": token,
        "avatar": avatar_url
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

    # 更新最近登录时间
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dreams_users SET last_login_at=NOW() WHERE id=%s",
                (uid,)
            )
            conn.commit()
    finally:
        conn.close()

    token = issue_token(uid)

    return {
        "uid": uid,
        "token": token,
        "avatar": user.get("avatar")
    }
