#!/bin/bash

# =================================================================
# 全自动部署脚本 (使用基础镜像方案)
# =================================================================

# --- 配置 ---
APP_NAME="trading-app"
BASE_IMAGE_NAME="trading-app-base"
CONTAINER_NAME="my-trading-container"
GIT_REMOTE="origin"
GIT_BRANCH="master"

# --- 颜色定义 ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# --- 脚本开始 ---

echo -e "${YELLOW}===== [STEP 1/6] Pulling latest code from Git... =====${NC}"
git pull $GIT_REMOTE $GIT_BRANCH
if [ $? -ne 0 ]; then
    echo -e "${RED}!!!!! Git pull failed! Deployment aborted. !!!!!${NC}"
    exit 1
fi
echo -e "${GREEN}Code is up to date.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 2/6] Building base image (if necessary)... =====${NC}"
# 使用 Docker BuildKit 来构建基础镜像
DOCKER_BUILDKIT=1 sudo docker build -t $BASE_IMAGE_NAME -f base.Dockerfile .
if [ $? -ne 0 ]; then
    echo -e "${RED}!!!!! Base image build failed! Deployment aborted. !!!!!${NC}"
    exit 1
fi
echo -e "${GREEN}Base image is up to date.${NC}"
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


echo -e "${YELLOW}===== [STEP 4/6] Building new application image... =====${NC}"
DOCKER_BUILDKIT=1 sudo docker build -t $APP_NAME -f Dockerfile .
if [ $? -ne 0 ]; then
    echo -e "${RED}!!!!! Application image build failed! Deployment aborted. !!!!!${NC}"
    exit 1
fi
echo -e "${GREEN}Application image built successfully.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 5/6] Starting new container... =====${NC}"
sudo docker run -d -p 8000:8000 --name $CONTAINER_NAME $APP_NAME
echo -e "${GREEN}New container started successfully.${NC}"
echo ""


echo -e "${YELLOW}===== [STEP 6/6] Pruning old Docker images... =====${NC}"
sudo docker image prune -f
echo -e "${GREEN}Cleanup complete.${NC}"
echo ""

echo -e "${GREEN}===== Deployment Finished! Your application is running. =====${NC}"
sudo docker ps -f name=$CONTAINER_NAME