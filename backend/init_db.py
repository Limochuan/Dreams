from db import get_conn

DDL = [
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
"""
CREATE TABLE IF NOT EXISTS dreams_sessions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    uid INT NOT NULL,
    token VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    INDEX idx_uid (uid),
    CONSTRAINT fk_sessions_user FOREIGN KEY (uid) REFERENCES dreams_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS dreams_conversations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    type ENUM('private','group') NOT NULL,
    title VARCHAR(100) DEFAULT NULL,
    owner_uid INT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_type (type),
    INDEX idx_owner (owner_uid),
    CONSTRAINT fk_conv_owner FOREIGN KEY (owner_uid) REFERENCES dreams_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS dreams_conversation_members (
    conversation_id BIGINT NOT NULL,
    uid INT NOT NULL,
    role ENUM('owner','admin','member') DEFAULT 'member',
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, uid),
    INDEX idx_uid (uid),
    CONSTRAINT fk_mem_conv FOREIGN KEY (conversation_id) REFERENCES dreams_conversations(id) ON DELETE CASCADE,
    CONSTRAINT fk_mem_user FOREIGN KEY (uid) REFERENCES dreams_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS dreams_messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conversation_id BIGINT NOT NULL,
    sender_uid INT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conv_time (conversation_id, created_at),
    CONSTRAINT fk_msg_conv FOREIGN KEY (conversation_id) REFERENCES dreams_conversations(id) ON DELETE CASCADE,
    CONSTRAINT fk_msg_user FOREIGN KEY (sender_uid) REFERENCES dreams_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""
]

def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for sql in DDL:
                cur.execute(sql)
    finally:
        conn.close()
