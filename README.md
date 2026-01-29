# Dreams
Dreams 聊天软件
dreams/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── db.py                # MySQL 连接
│   ├── auth.py              # 注册 / 登录 / 密码
│   ├── conversations.py     # 单聊 / 群聊 API
│   ├── ws.py                # WebSocket 逻辑
│   ├── requirements.txt
│   └── Procfile
│
├── frontend/
│   ├── login.html           # 登录 / 注册
│   ├── conversations.html  # 会话列表
│   ├── chat.html            # 聊天窗口
│   └── app.js               # 前端通用逻辑
│
├── README.md
└── .gitignore
