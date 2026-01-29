from db import get_conn


# =========================
# 数据库初始化 DDL 列表
# =========================
# (这部分 DDL 定义保持不变，完全正确)
DDL = [
    # 用户表
    """
    CREATE TABLE IF NOT EXISTS dreams_users (
        id INT PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(50) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        avatar VARCHAR(512) DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 登录会话 / token 表
    """
    CREATE TABLE IF NOT EXISTS dreams_sessions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        uid INT NOT NULL,
        token VARCHAR(128) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NULL,
        INDEX idx_uid (uid),
        CONSTRAINT fk_sessions_user
            FOREIGN KEY (uid)
            REFERENCES dreams_users(id)
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 会话表（私聊 / 群聊）
    """
    CREATE TABLE IF NOT EXISTS dreams_conversations (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        type ENUM('private','group') NOT NULL,
        title VARCHAR(100) DEFAULT NULL,
        owner_uid INT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_type (type),
        INDEX idx_owner (owner_uid),
        CONSTRAINT fk_conv_owner
            FOREIGN KEY (owner_uid)
            REFERENCES dreams_users(id)
            ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 会话成员表
    """
    CREATE TABLE IF NOT EXISTS dreams_conversation_members (
        conversation_id BIGINT NOT NULL,
        uid INT NOT NULL,
        role ENUM('owner','admin','member') DEFAULT 'member',
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (conversation_id, uid),
        INDEX idx_uid (uid),
        CONSTRAINT fk_mem_conv
            FOREIGN KEY (conversation_id)
            REFERENCES dreams_conversations(id)
            ON DELETE CASCADE,
            # 注意：这里我们保留了级联删除，
            # 如果删除了世界频道，所有人都会退群，逻辑是自洽的
        CONSTRAINT fk_mem_user
            FOREIGN KEY (uid)
            REFERENCES dreams_users(id)
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 消息表
    """
    CREATE TABLE IF NOT EXISTS dreams_messages (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        conversation_id BIGINT NOT NULL,
        sender_uid INT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_conv_time (conversation_id, created_at),
        CONSTRAINT fk_msg_conv
            FOREIGN KEY (conversation_id)
            REFERENCES dreams_conversations(id)
            ON DELETE CASCADE,
        CONSTRAINT fk_msg_user
            FOREIGN KEY (sender_uid)
            REFERENCES dreams_users(id)
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
]


# =========================
# 数据库初始化入口函数
# =========================

def init_db():
    """
    初始化 Dreams 项目的数据库表结构并预制种子数据
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 1. 执行建表
            for sql in DDL:
                cur.execute(sql)
            
            # 2. 【关键新增】预制“世界频道”
            # 使用 INSERT IGNORE，防止每次重启时重复插入或报错
            # 我们手动指定 id=1，确保它永远是第 1 号会话
            cur.execute(
                """
                INSERT IGNORE INTO dreams_conversations (id, type, title) 
                VALUES (1, 'group', '🌍 世界频道')
                """
            )
            
            # 这里的 conn 在 db.py 里已经开启了 autocommit=True，
            # 所以不需要手动 commit
            print("Database initialized successfully (World Channel created).")

    except Exception as e:
        print(f"Database init failed: {e}")
        raise e  # 抛出异常让程序知道初始化失败了
    finally:
        conn.close()

if __name__ == "__main__":
    # 允许直接运行此文件来初始化
    init_db()
