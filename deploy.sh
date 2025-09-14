#!/bin/bash

# =================================================================
# 全自动部署脚本 for Trading WebApp (集成 Git)
#
# 功能:
# 1. 从 Git 远程仓库拉取最新的代码。
# 2. 停止并删除旧的 Docker 容器。
# 3. 使用最新的代码和 BuildKit 引擎构建新的 Docker 镜像。
# 4. 启动基于新镜像的新容器。
# 5. 清理无用的 Docker 镜像。
#
# 用法:
# 将此脚本放在项目根目录，然后运行 ./deploy.sh
# =================================================================

# --- 配置 ---
APP_NAME="trading-app"
CONTAINER_NAME="my-trading-container"
GIT_REMOTE="origin"
GIT_BRANCH="master" # 根据您的 git push 日志，您的分支是 master

# --- 颜色定义 ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# --- 脚本开始 ---

echo -e "${YELLOW}===== [STEP 1/5] Pulling latest code from Git... =====${NC}"

git pull $GIT_REMOTE $GIT_BRANCH
if [ $? -ne 0 ]; then
    echo -e "${RED}!!!!! Git pull failed! Deployment aborted. !!!!!${NC}"
    exit 1
fi
echo -e "${GREEN}Code is up to date.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 2/5] Stopping and removing old container... =====${NC}"
if [ "$(sudo docker ps -q -f name=$CONTAINER_NAME)" ]; then
    sudo docker stop $CONTAINER_NAME
fi
if [ "$(sudo docker ps -aq -f name=$CONTAINER_NAME)" ]; then
    sudo docker rm $CONTAINER_NAME
fi
echo -e "${GREEN}Old container stopped and removed.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 3/5] Building new Docker image with BuildKit: $APP_NAME =====${NC}"
# --- 核心修复：强制启用 BuildKit ---
export DOCKER_BUILDKIT=1
sudo docker build -t $APP_NAME .
# -----------------------------------

BUILD_STATUS=$?
if [ $BUILD_STATUS -ne 0 ]; then
    echo -e "${RED}!!!!! Docker build failed! Deployment aborted. !!!!!${NC}"
    exit $BUILD_STATUS
fi
echo -e "${GREEN}Docker image built successfully.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 4/5] Starting new container: $CONTAINER_NAME =====${NC}"
sudo docker run -d -p 8000:8000 --name $CONTAINER_NAME $APP_NAME
echo -e "${GREEN}New container started successfully.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 5/5] Pruning old Docker images... =====${NC}"
sudo docker image prune -f
echo -e "${GREEN}Cleanup complete.${NC}"
echo ""

echo -e "${GREEN}===== Deployment Finished! Your application is running. =====${NC}"
sudo docker ps -f name=$CONTAINER_NAME