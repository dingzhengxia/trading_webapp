# 应用镜像 Dockerfile
# 功能：使用基础镜像，并加入最新的业务代码。

# 1. 从我们自己构建的基础镜像开始
FROM trading-app-base:latest

# 2. 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=1

# 3. 设置工作目录
WORKDIR /app

# 4. 复制所有源代码和配置文件
# 假设配置文件在 backend/ 目录下
COPY backend/ ./backend
COPY frontend/ ./frontend

# 5. 使用已经安装好的依赖来构建前端
WORKDIR /app/frontend
RUN npm run build

# 6. 将编译好的前端文件移动到后端可以提供的位置
WORKDIR /app
RUN mv /app/frontend/dist ./backend/app/frontend_dist

# 7. 设置最终的工作目录
WORKDIR /app/backend

# 8. 暴露端口
EXPOSE 8000

# 9. 启动命令
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]