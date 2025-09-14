# 基础镜像 Dockerfile
# 功能：安装所有不常变动的系统和语言依赖。

# 1. 从一个包含 Node.js 的轻量级镜像开始
FROM node:20-alpine AS base

# 2. 安装 Python, pip, 和 gunicorn
RUN apk add --no-cache python3 py3-pip gunicorn

# 3. 设置工作目录
WORKDIR /deps

# 4. 安装 Python 依赖 (此层将被高度缓存)
COPY backend/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 5. 安装 Node.js 依赖 (此层将被高度缓存)
COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit