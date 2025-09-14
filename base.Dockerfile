# base.Dockerfile
# 只负责安装依赖

FROM node:20-alpine

RUN apk add --no-cache python3 py3-pip

# 创建虚拟环境
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /deps

# 安装 Python 依赖到虚拟环境
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 安装 Node.js 依赖
COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit