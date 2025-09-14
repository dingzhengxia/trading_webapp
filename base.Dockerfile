# base.Dockerfile
# 负责安装所有不变的依赖

FROM node:20-alpine

# 安装系统依赖
RUN apk add --no-cache python3 py3-pip

# 创建并激活 Python 虚拟环境
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

# 设置工作目录
WORKDIR /deps

# 安装 Python 依赖到虚拟环境
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 安装 Node.js 依赖
COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit