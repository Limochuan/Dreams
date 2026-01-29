import bcrypt
from db import get_conn

def hash_password(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

def verify_password(pwd: str, pwd_hash: str) -> bool:
    return bcrypt.checkpw(pwd.encode(), pwd_hash.encode())

def create_user(username, password, avatar):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dreams_users (username, password_hash, avatar) VALUES (%s,%s,%s)",
            (username, hash_password(password), avatar)
        )
        return cur.lastrowid

def get_user(username):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM dreams_users WHERE username=%s", (username,))
        return cur.fetchone()

