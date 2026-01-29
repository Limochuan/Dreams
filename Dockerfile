FROM python:3.11-slim

# 工作目录
WORKDIR /app

# 先拷依赖，利用缓存
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端代码
COPY backend/ ./backend/

# 拷贝前端代码（重点！！！！）
COPY frontend/ ./frontend/

# 进入 backend 作为运行目录
WORKDIR /app/backend

# Railway 会注入 PORT
ENV PORT=8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
