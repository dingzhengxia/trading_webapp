# 基础镜像 Dockerfile
# 功能：安装所有不常变动的系统和语言依赖。

# 1. 从一个包含 Node.js 的轻量级镜像开始
FROM node:20-alpine AS base

# 2. 安装 Python 和 pip (系统级依赖)
RUN apk add --no-cache python3 py3-pip

# 3. 设置工作目录
WORKDIR /deps

# 4. 安装 Python 依赖 (包括 gunicorn)
# 将 gunicorn 直接添加到 requirements.txt 是最佳实践，
# 但为了快速修复，我们也可以在这里直接安装。
# 我们将 gunicorn 放在 requirements.txt 的安装命令中。
COPY backend/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 5. 安装 Node.js 依赖
COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit

# This base image is now ready.