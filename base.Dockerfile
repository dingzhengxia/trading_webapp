# base.Dockerfile
# 负责安装所有不变的依赖到一个可复用的基础镜像中。

# 1. 从一个包含 Node.js 的轻量级镜像开始
FROM node:20-alpine

# 2. 安装 Python 和 pip。venv 模块通常已包含在 python3 包中。
RUN apk add --no-cache python3 py3-pip

# 3. 创建 Python 虚拟环境
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH

# 4. 将虚拟环境的 bin 目录添加到 PATH 环境变量中
ENV PATH="$VENV_PATH/bin:$PATH"

# 5. 设置工作目录
WORKDIR /deps

# 6. 升级虚拟环境中的 pip
RUN pip install --no-cache-dir --upgrade pip

# 7. 安装 Python 依赖到虚拟环境中
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8. 安装 Node.js 依赖
COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit