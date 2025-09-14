#!/bin/bash

# =================================================================
# 自动化部署脚本 for Trading WebApp
#
# 功能:
# 1. 停止并删除旧的容器。
# 2. 使用最新的代码构建新的 Docker 镜像。
# 3. 启动基于新镜像的新容器。
# 4. 清理无用的 Docker 镜像。
#
# 用法:
# 将此脚本放在项目根目录，然后运行 ./deploy.sh
# =================================================================

# --- 配置 ---
# 应用的名称，用于镜像名和容器名
APP_NAME="trading-app"
CONTAINER_NAME="my-trading-container"

# 使用颜色输出，方便阅读
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- 脚本开始 ---

echo -e "${YELLOW}===== [STEP 1/5] Stopping and removing old container... =====${NC}"
# 使用 "docker ps -q" 来检查容器是否存在，更健壮
if [ "$(sudo docker ps -q -f name=$CONTAINER_NAME)" ]; then
    sudo docker stop $CONTAINER_NAME
fi
if [ "$(sudo docker ps -aq -f name=$CONTAINER_NAME)" ]; then
    sudo docker rm $CONTAINER_NAME
fi
echo -e "${GREEN}Old container stopped and removed.${NC}"
echo ""

echo -e "${YELLOW}===== [STEP 2/5] Pulling latest code... (Optional, for Git users) =====${NC}"
# 如果您使用 Git，取消下面这行的注释
# git pull origin main
echo -e "${GREEN}Code is up to date.${NC}"
echo ""

echo -e "${YELLOW}===== [STEP 3/5] Building new Docker image: $APP_NAME =====${NC}"
# 强制使用 BuildKit 引擎，并构建镜像
DOCKER_BUILDKIT=1 sudo docker build -t $APP_NAME .

# 检查构建是否成功
if [ $? -ne 0 ]; then
    echo -e "${RED}!!!!! Docker build failed! Deployment aborted. !!!!!${NC}"
    exit 1
fi
echo -e "${GREEN}Docker image built successfully.${NC}"
echo ""

echo -e "${YELLOW}===== [STEP 4/5] Starting new container: $CONTAINER_NAME =====${NC}"
sudo docker run -d -p 8000:8000 --name $CONTAINER_NAME $APP_NAME
echo -e "${GREEN}New container started successfully.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 5/5] Pruning old Docker images... =====${NC}"
# 清理所有未被任何容器使用的 "悬空" 镜像 (dangling images)
sudo docker image prune -f
echo -e "${GREEN}Cleanup complete.${NC}"
echo ""

echo -e "${GREEN}===== Deployment Finished! Your application is running. =====${NC}"
sudo docker ps -f name=$CONTAINER_NAME