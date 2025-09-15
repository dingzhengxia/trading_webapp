#!/bin/bash

# =================================================================
# 全自动部署脚本 (使用独立的、持久化的配置目录)
# =================================================================

# --- 配置 ---
APP_NAME="trading-app"
CONTAINER_NAME="my-trading-container"
GIT_REMOTE="origin"
GIT_BRANCH="master"

# --- 核心修改：定义一个固定的、项目外的配置目录 ---
CONFIG_DIR="/root/config"
# --------------------------------------------------

# --- 颜色定义 ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# --- 脚本开始 ---

echo -e "${YELLOW}===== [STEP 1/6] Setting up persistent config directory... =====${NC}"
# 创建配置目录（如果不存在）
sudo mkdir -p $CONFIG_DIR
# 确保文件存在，如果不存在则创建一个空的
sudo touch "$CONFIG_DIR/user_settings.json"
sudo touch "$CONFIG_DIR/coin_lists.json"
# 赋予正确的权限，确保 Docker 容器可以读写
sudo chmod -R 777 $CONFIG_DIR
echo -e "${GREEN}Config directory '$CONFIG_DIR' is ready.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 2/6] Pulling latest code from Git... =====${NC}"
git pull $GIT_REMOTE $GIT_BRANCH
if [ $? -ne 0 ]; then
    echo -e "${RED}!!!!! Git pull failed! Deployment aborted. !!!!!${NC}"
    exit 1
fi
echo -e "${GREEN}Code is up to date.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 3/6] Stopping and removing old container... =====${NC}"
if [ "$(sudo docker ps -q -f name=$CONTAINER_NAME)" ]; then
    sudo docker stop $CONTAINER_NAME
fi
if [ "$(sudo docker ps -aq -f name=$CONTAINER_NAME)" ]; then
    sudo docker rm $CONTAINER_NAME
fi
echo -e "${GREEN}Old container stopped and removed.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 4/6] Building new Docker image: $APP_NAME =====${NC}"
DOCKER_BUILDKIT=1 sudo docker build -t $APP_NAME .
BUILD_STATUS=$?
if [ $BUILD_STATUS -ne 0 ]; then
    echo -e "${RED}!!!!! Docker build failed! Deployment aborted. !!!!!${NC}"
    exit $BUILD_STATUS
fi
echo -e "${GREEN}Docker image built successfully.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 5/6] Starting new container with volume mounts... =====${NC}"
# --- 核心修改：从固定的配置目录挂载数据卷 ---
sudo docker run -d \
    -p 8000:8000 \
    --name $CONTAINER_NAME \
    -v "$CONFIG_DIR/user_settings.json":/app/user_settings.json:rw \
    -v "$CONFIG_DIR/coin_lists.json":/app/coin_lists.json:rw \
    $APP_NAME
# ---------------------------------------------------
echo -e "${GREEN}New container started successfully.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 6/6] Pruning old Docker images... =====${NC}"
sudo docker image prune -f
echo -e "${GREEN}Cleanup complete.${NC}"
echo ""

echo -e "${GREEN}===== Deployment Finished! Your application is running. =====${NC}"
sudo docker ps -f name=$CONTAINER_NAME