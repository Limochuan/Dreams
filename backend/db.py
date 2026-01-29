import os
import pymysql
import ssl  # <--- 需要引入这个标准库

def get_conn():
    # ... 注释不变 ...
    
    # 检查是否需要 SSL（通常线上环境才需要）
    # 大部分云厂商只需要一个空的 SSL 上下文即可骗过验证
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # 如果是在本地开发（没有 DB_USE_SSL 环境变量），就不传 ssl
    # 如果是在线上（设置了 DB_USE_SSL=true），就启用 ssl
    enable_ssl = os.getenv("DB_USE_SSL", "false").lower() == "true"
    ssl_arg = ssl_context if enable_ssl else None

    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        ssl=ssl_arg  # <--- 加上这个参数
    )
