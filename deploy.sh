#!/bin/bash

# =================================================================
# 全自动部署脚本 for Trading WebApp (集成 Git)
#
# 功能:
# 1. 从 Git 远程仓库拉取最新的代码。
# 2. 停止并删除旧的 Docker 容器。
# 3. 使用最新的代码构建新的 Docker 镜像。
# 4. 启动基于新镜像的新容器。
# 5. 清理无用的 Docker 镜像。
#
# 用法:
# 确保服务器已配置好 SSH 免密登录 GitHub/Gitee (如果仓库是私有的)。
# 将此脚本放在项目根目录，然后运行 ./deploy.sh
# =================================================================

# --- 配置 ---
APP_NAME="trading-app"
CONTAINER_NAME="my-trading-container"
# Git 远程仓库名 (通常是 origin) 和分支名 (通常是 main 或 master)
GIT_REMOTE="origin"
GIT_BRANCH="master"

# --- 颜色定义 ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- 脚本开始 ---

echo -e "${YELLOW}===== [STEP 1/5] Pulling latest code from Git... =====${NC}"

# 拉取最新代码
git pull $GIT_REMOTE $GIT_BRANCH

# 检查 git pull 是否成功
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


echo -e "${YELLOW}===== [STEP 3/5] Building new Docker image: $APP_NAME =====${NC}"
DOCKER_BUILDKIT=1 sudo docker build -t $APP_NAME .

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
sudo docker image prune -f
echo -e "${GREEN}Cleanup complete.${NC}"
echo ""

echo -e "${GREEN}===== Deployment Finished! Your application is running. =====${NC}"
sudo docker ps -f name=$CONTAINER_NAME