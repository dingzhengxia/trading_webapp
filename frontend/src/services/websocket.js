// frontend/src/services/websocket.ts (优化心跳后的完整代码)
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
class WebSocketService {
    ws = null;
    isConnecting = false;
    reconnectTimeoutId;
    reconnectAttempts = 0;
    MAX_RECONNECT_DELAY = 30000;
    // REFACTOR: 添加心跳和连接超时相关属性
    heartbeatIntervalId;
    connectionTimeoutId;
    HEARTBEAT_INTERVAL = 25000; // 25秒发送一次ping
    CONNECTION_TIMEOUT = this.HEARTBEAT_INTERVAL + 5000; // 30秒没收到任何消息则认为超时
    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = import.meta.env.DEV ? `${window.location.hostname}:8000` : window.location.host;
        return `${protocol}//${host}/ws`;
    }
    // REFACTOR: 启动心跳和连接检查
    startHealthChecks() {
        this.stopHealthChecks(); // 先确保旧的定时器被清除
        this.heartbeatIntervalId = window.setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                // 发送JSON格式的心跳包
                this.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, this.HEARTBEAT_INTERVAL);
        this.resetConnectionTimeout();
    }
    // REFACTOR: 停止所有健康检查相关的定时器
    stopHealthChecks() {
        clearInterval(this.heartbeatIntervalId);
        clearTimeout(this.connectionTimeoutId);
        this.heartbeatIntervalId = undefined;
        this.connectionTimeoutId = undefined;
    }
    // REFACTOR: 重置连接超时定时器
    resetConnectionTimeout() {
        clearTimeout(this.connectionTimeoutId);
        this.connectionTimeoutId = window.setTimeout(() => {
            console.error('[WS] ❌ Connection timeout. No message received in the last 30 seconds. Forcing reconnect.');
            this.ws?.close(); // 主动关闭会触发 onclose 中的重连逻辑
        }, this.CONNECTION_TIMEOUT);
    }
    connect() {
        if (this.ws &&
            (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        if (this.isConnecting) {
            return;
        }
        this.isConnecting = true;
        const url = this.getWebSocketUrl();
        console.log(`[WS] Attempting to connect to: ${url}`);
        this.ws = new WebSocket(url);
        this.ws.onopen = () => {
            console.log('[WS] ✅ Connection established.');
            this.isConnecting = false;
            this.reconnectAttempts = 0;
            const uiStore = useUiStore();
            const positionStore = usePositionStore();
            if (!uiStore.isRunning) {
                uiStore.setStatus('已连接');
            }
            this.startHealthChecks(); // 连接成功后启动健康检查
            // 断线期间错过的持仓变更/任务结束事件无法重放，重连后必须做一次全量对账，
            // 否则页面可能继续显示已被平掉的仓位。
            void positionStore.fetchPositions();
            void uiStore.checkInitialStatus();
        };
        this.ws.onmessage = (event) => {
            this.resetConnectionTimeout(); // 收到任何消息（包括pong）都说明连接是健康的，重置超时
            const data = JSON.parse(event.data);
            // 忽略后端发来的 pong 消息，它只用于重置超时
            if (data.type === 'pong') {
                return;
            }
            const uiStore = useUiStore();
            const positionStore = usePositionStore();
            switch (data.type) {
                case 'log':
                    uiStore.logStore.addLog(data.payload);
                    break;
                case 'status':
                    uiStore.setStatus(data.payload.message, data.payload.isRunning);
                    break;
                case 'progress_update':
                    uiStore.updateProgress(data.payload);
                    break;
                case 'position_closed':
                    const { full_symbol, ratio } = data.payload;
                    if (Math.abs(ratio - 1.0) < 1e-9) {
                        positionStore.removePositions([full_symbol]);
                    }
                    else {
                        positionStore.updatePositionContracts(full_symbol, ratio);
                    }
                    break;
            }
        };
        this.ws.onclose = () => {
            this.stopHealthChecks(); // 连接关闭时必须停止所有健康检查
            const uiStore = useUiStore();
            if (!uiStore.isStopping) {
                // 如果不是用户主动停止任务导致的断开
                uiStore.setStatus('已断开');
            }
            this.ws = null;
            this.isConnecting = false;
            // 指数退避重连：1s → 2s → 4s ... 上限 30s，避免后端重启时刷屏
            const delay = Math.min(1000 * 2 ** this.reconnectAttempts, this.MAX_RECONNECT_DELAY);
            this.reconnectAttempts += 1;
            console.warn(`[WS] ❌ Connection closed. Reconnecting in ${delay}ms...`);
            clearTimeout(this.reconnectTimeoutId);
            this.reconnectTimeoutId = window.setTimeout(() => this.connect(), delay);
        };
        this.ws.onerror = (event) => {
            console.error('[WS] ❌ WebSocket Error:', event);
            this.isConnecting = false;
            this.ws?.close(); // 发生错误时，也尝试关闭以触发 onclose 的重连逻辑
        };
    }
    disconnect() {
        this.stopHealthChecks();
        clearTimeout(this.reconnectTimeoutId);
        if (this.ws) {
            this.ws.onclose = null; // 移除 onclose 处理器以防止重连
            this.ws.close();
            this.ws = null;
        }
    }
}
if (!window.__WEBSOCKET_SERVICE__) {
    window.__WEBSOCKET_SERVICE__ = new WebSocketService();
}
export default window.__WEBSOCKET_SERVICE__;
