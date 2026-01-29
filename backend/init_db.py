from db import get_conn

# =========================
# 数据库初始化 DDL 列表
# =========================
DDL = [
    # 1. 用户表
    # [变更]: avatar 改为 LONGTEXT (存Base64)，新增 gender 字段
    """
    CREATE TABLE IF NOT EXISTS dreams_users (
        id INT PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(50) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        avatar LONGTEXT DEFAULT NULL,
        gender ENUM('male', 'female', 'secret') DEFAULT 'secret',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 2. 好友关系表 (新增)
    # [新增]: 用于好友列表功能
    """
    CREATE TABLE IF NOT EXISTS dreams_friends (
        uid INT NOT NULL,
        friend_uid INT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (uid, friend_uid),
        CONSTRAINT fk_friend_user FOREIGN KEY (uid) REFERENCES dreams_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_friend_target FOREIGN KEY (friend_uid) REFERENCES dreams_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 3. 登录会话 / token 表 (保持不变)
    """
    CREATE TABLE IF NOT EXISTS dreams_sessions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        uid INT NOT NULL,
        token VARCHAR(128) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NULL,
        INDEX idx_uid (uid),
        CONSTRAINT fk_sessions_user
            FOREIGN KEY (uid) REFERENCES dreams_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 4. 会话表
    # [变更]: 新增 avatar (群头像), updated_at (用于排序)
    """
    CREATE TABLE IF NOT EXISTS dreams_conversations (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        type ENUM('private','group') NOT NULL,
        title VARCHAR(100) DEFAULT NULL,
        avatar LONGTEXT DEFAULT NULL,
        owner_uid INT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_type (type),
        INDEX idx_owner (owner_uid),
        CONSTRAINT fk_conv_owner
            FOREIGN KEY (owner_uid) REFERENCES dreams_users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 5. 会话成员表
    # [变更]: 新增 last_read_at (红点), is_pinned (置顶), is_muted (免打扰)
    """
    CREATE TABLE IF NOT EXISTS dreams_conversation_members (
        conversation_id BIGINT NOT NULL,
        uid INT NOT NULL,
        role ENUM('owner','admin','member') DEFAULT 'member',
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_pinned BOOLEAN DEFAULT FALSE,
        is_muted BOOLEAN DEFAULT FALSE,
        
        PRIMARY KEY (conversation_id, uid),
        INDEX idx_uid (uid),
        CONSTRAINT fk_mem_conv
            FOREIGN KEY (conversation_id) REFERENCES dreams_conversations(id) ON DELETE CASCADE,
        CONSTRAINT fk_mem_user
            FOREIGN KEY (uid) REFERENCES dreams_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 6. 消息表 (保持不变)
    """
    CREATE TABLE IF NOT EXISTS dreams_messages (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        conversation_id BIGINT NOT NULL,
        sender_uid INT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_conv_time (conversation_id, created_at),
        CONSTRAINT fk_msg_conv
            FOREIGN KEY (conversation_id) REFERENCES dreams_conversations(id) ON DELETE CASCADE,
        CONSTRAINT fk_msg_user
            FOREIGN KEY (sender_uid) REFERENCES dreams_users(id) ON DELETE CASCADE
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
            
            # 2. 预制“世界频道”
            # [升级]: 显式指定 owner_uid=1，方便后续权限管理
            cur.execute(
                """
                INSERT IGNORE INTO dreams_conversations (id, type, title, owner_uid) 
                VALUES (1, 'group', '🌍 世界频道', 1)
                """
            )
            
            # 3. [升级] 尝试将 UID 1 设为世界频道的群主
            # (如果当前数据库是空的，这里不会生效，等到用户注册后逻辑会自动处理)
            # (如果数据库里已有用户，这步能确保权限正确)
            try:
                # 如果 UID 1 用户存在，确保他在成员表里是 owner
                cur.execute("""
                    INSERT IGNORE INTO dreams_conversation_members (conversation_id, uid, role) 
                    VALUES (1, 1, 'owner')
                """)
                # 如果他以前就在表里（比如是member），强制升级为owner
                cur.execute("UPDATE dreams_conversation_members SET role='owner' WHERE conversation_id=1 AND uid=1")
                conn.commit()
            except Exception:
                pass # 忽略错误（比如用户表还没人）

            print("✅ Database initialized successfully (Tables updated, World Channel ready).")

    except Exception as e:
        print(f"❌ Database init failed: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
