#!/bin/bash
# deploy.sh (最终简化版)

APP_NAME="trading-app"
CONTAINER_NAME="my-trading-container"
GIT_REMOTE="origin"
GIT_BRANCH="master"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}===== [STEP 1/4] Pulling latest code... =====${NC}"
git pull $GIT_REMOTE $GIT_BRANCH
if [ $? -ne 0 ]; then echo -e "${RED}Git pull failed!${NC}"; exit 1; fi
echo -e "${GREEN}Code updated.${NC}\n"

echo -e "${YELLOW}===== [STEP 2/4] Building Docker image... =====${NC}"
DOCKER_BUILDKIT=1 sudo docker build -t $APP_NAME .
if [ $? -ne 0 ]; then echo -e "${RED}Docker build failed!${NC}"; exit 1; fi
echo -e "${GREEN}Image built successfully.${NC}\n"

echo -e "${YELLOW}===== [STEP 3/4] Restarting container... =====${NC}"
sudo docker stop $CONTAINER_NAME 2>/dev/null || true
sudo docker rm $CONTAINER_NAME 2>/dev/null || true
sudo docker run -d -p 8000:8000 --name $CONTAINER_NAME $APP_NAME
echo -e "${GREEN}Container restarted successfully.${NC}\n"

echo -e "${YELLOW}===== [STEP 4/4] Pruning old images... =====${NC}"
sudo docker image prune -f
echo -e "${GREEN}Cleanup complete.${NC}\n"

echo -e "${GREEN}===== Deployment Finished! =====${NC}"
sudo docker ps -f name=$CONTAINER_NAME