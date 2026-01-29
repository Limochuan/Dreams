from db import get_conn


# =========================
# 数据库初始化 DDL 列表
# =========================
# 说明：
# - 这里集中定义所有 Dreams 项目需要的表结构
# - 使用 CREATE TABLE IF NOT EXISTS，只负责“首次创建”
# - 已存在的表不会被修改
# - 表结构变更需要通过手动 ALTER TABLE 完成

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
    初始化 Dreams 项目的数据库表结构

    行为说明：
    - 依次执行 DDL 列表中的建表语句
    - 只负责创建不存在的表
    - 不负责字段变更、不做数据迁移

    使用建议：
    - 首次部署时手动调用一次
    - 不建议在应用启动时自动调用
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for sql in DDL:
                cur.execute(sql)
    finally:
        conn.close()
