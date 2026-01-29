import os
import pymysql


def get_conn():
    """
    获取一个新的 MySQL 数据库连接

    设计说明：
    - 每次调用都会创建一个新的连接
    - 使用环境变量读取数据库配置，适配本地 / Railway / 云数据库
    - 不在模块加载或应用启动时自动连接数据库
    - 由具体业务函数在需要时主动调用

    使用的环境变量：
    - DB_HOST: 数据库地址（不要写 localhost，线上一般是云数据库地址）
    - DB_USER: 数据库用户名
    - DB_PASSWORD: 数据库密码
    - DB_NAME: 数据库名称
    - DB_PORT: 数据库端口（可选，默认 3306）

    返回：
    - 一个 pymysql 连接对象
    """
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
