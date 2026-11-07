#!/bin/bash

# =================================================================
# 全自动部署脚本 (使用独立的、持久化的配置目录)
# =================================================================

# --- 配置 ---
APP_NAME="trading-app"
CONTAINER_NAME="my-trading-container"
GIT_REMOTE="origin"
GIT_BRANCH="master"

# --- 持久化数据目录（SQLite / JSON），与代码目录分离 ---
CONFIG_DIR="/root/config"

# --- 代码目录：本脚本所在目录，.env 就放在这里（与 deploy.sh 同级） ---
# 用 BASH_SOURCE 解析，保证在任意 cwd 下执行都能定位到项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# git pull / docker build 都依赖 cwd，统一切到项目目录，避免在别处执行时拉错仓库/打错上下文
cd "$PROJECT_DIR" || { echo "无法进入项目目录 $PROJECT_DIR"; exit 1; }
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
# SQLite 数据库目录（/app/data/app.db）：所有设置、币种池、信号/仓位保护状态都在这里，
# 必须挂载持久卷，否则容器重建后配置全部丢失
sudo mkdir -p "$CONFIG_DIR/data"

# 环境变量文件（交易所密钥 / 钉钉 webhook）：放在项目目录下，与 deploy.sh 同级
# - 已被 .gitignore 忽略，不会进仓库；已被 .dockerignore 忽略，不会进镜像
# - 由 docker run --env-file 在容器创建时注入（注意：--env-file 只在创建时读取，
#   `docker restart` 不会重新加载，改完必须重建容器，即重跑本脚本）
ENV_FILE="$PROJECT_DIR/.env"
LEGACY_ENV_FILE="$CONFIG_DIR/.env"

# 兼容旧部署：项目目录还没有 .env，而旧的 /root/config/.env 已经填过真实值时，直接迁移过来
if [ ! -f "$ENV_FILE" ] && [ -f "$LEGACY_ENV_FILE" ]; then
    sudo cp "$LEGACY_ENV_FILE" "$ENV_FILE"
    echo -e "${YELLOW}已把旧的 $LEGACY_ENV_FILE 迁移到 $ENV_FILE（旧文件保留，可手动删除）${NC}"
fi

if [ ! -f "$ENV_FILE" ]; then
    sudo tee "$ENV_FILE" > /dev/null <<'ENVEOF'
# 填入真实值后重新执行本脚本；本文件仅存在于服务器，不会进入 Git / 镜像
BINANCE_API_KEY=
BINANCE_API_SECRET=
DINGTALK_WEBHOOK_URL=
DINGTALK_SECRET=
ENVEOF
    echo -e "${YELLOW}已创建环境变量模板 $ENV_FILE，请先填入密钥再执行部署。${NC}"
fi

# 归属改为当前用户（免 sudo 编辑），权限收紧到 600（仅属主可读）
sudo chown "$(id -u):$(id -g)" "$ENV_FILE" 2>/dev/null || true
sudo chmod 600 "$ENV_FILE"

# 在 Windows 上编辑过 .env 会带 CRLF，docker --env-file 会把 \r 一起注入，
# 导致 webhook 签名/交易所密钥校验失败，这里先统一成 LF
if grep -q $'\r' "$ENV_FILE"; then
    sed -i 's/\r$//' "$ENV_FILE"
    echo -e "${YELLOW}检测到 CRLF 换行，已转换为 LF：$ENV_FILE${NC}"
fi
echo -e "${GREEN}Env file: $ENV_FILE${NC}"

# 赋予正确的权限，确保 Docker 容器可以读写（.env 已不在该目录内，不受 777 影响）
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
# 启动前自检：变量为空时钉钉会显示“未配置”、交易所会报 -2015，提前提示比事后排查省事
if ! sudo grep -qE '^[[:space:]]*DINGTALK_WEBHOOK_URL=[^[:space:]]+' "$ENV_FILE"; then
    echo -e "${YELLOW}提示：$ENV_FILE 中 DINGTALK_WEBHOOK_URL 为空，网页上会显示“钉钉未配置”。${NC}"
fi
if ! sudo grep -qE '^[[:space:]]*BINANCE_API_KEY=[^[:space:]]+' "$ENV_FILE"; then
    echo -e "${YELLOW}提示：$ENV_FILE 中 BINANCE_API_KEY 为空，交易所接口会鉴权失败。${NC}"
fi

# --- 从固定的配置目录挂载数据卷 ---
# JSON 文件仅用于首次启动时的 SQLite 一次性迁移（迁移完成后不再读写，可保留兜底）；
# 真正的持久化数据在 SQLite：宿主机 /root/config/data ↔ 容器 /app/data
sudo docker run -d \
    -p 8000:8000 \
    --restart unless-stopped \
    --name $CONTAINER_NAME \
    --env-file "$ENV_FILE" \
    -v "$ENV_FILE":/app/.env:ro \
    -v "$CONFIG_DIR/user_settings.json":/app/user_settings.json:rw \
    -v "$CONFIG_DIR/coin_lists.json":/app/coin_lists.json:rw \
    -v "$CONFIG_DIR/data":/app/data:rw \
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