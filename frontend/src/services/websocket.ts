// frontend/src/services/websocket.ts (健壮的单例模式)
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';

class WebSocketService {
  private ws: WebSocket | null = null;
  private connectionPromise: Promise<void> | null = null;
  private reconnectTimeout: number | undefined;

  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.DEV ? `${window.location.hostname}:8000` : window.location.host;
    return `${protocol}//${host}/ws`;
  }

  // 公共的连接方法
  public connect() {
    // 如果已经有WebSocket实例并且处于连接中或已连接状态，则直接返回
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      console.log("WebSocket is already connected or connecting.");
      return;
    }

    // 防止并发连接
    if (this.connectionPromise) {
      return this.connectionPromise;
    }

    this.connectionPromise = new Promise((resolve, reject) => {
      const uiStore = useUiStore();
      const url = this.getWebSocketUrl();
      console.log(`Attempting to connect to WebSocket at: ${url}`);

      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log("WebSocket connection established.");
        uiStore.setStatus('已连接', false);
        this.connectionPromise = null;
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
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
            } else {
              positionStore.updatePositionContracts(full_symbol, ratio);
            }
            break;
          case 'refresh_positions':
            positionStore.fetchPositions();
            break;
        }
      };

      this.ws.onclose = () => {
        console.log("WebSocket connection closed.");
        uiStore.logStore.addLog({ message: '--- WebSocket 连接断开，5秒后重试... ---', level: 'error', timestamp: new Date().toLocaleTimeString() });
        uiStore.setStatus('已断开', false);
        this.ws = null;
        this.connectionPromise = null;
        clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = window.setTimeout(() => this.connect(), 5000);
      };

      this.ws.onerror = (event) => {
        console.error("WebSocket Error:", event);
        uiStore.logStore.addLog({ message: '--- WebSocket 连接发生错误 ---', level: 'error', timestamp: new Date().toLocaleTimeString() });
        this.connectionPromise = null;
        reject(event);
      };
    });
    return this.connectionPromise;
  }

  // 添加一个断开连接的方法，用于热重载时清理
  public disconnect() {
    clearTimeout(this.reconnectTimeout);
    if (this.ws) {
      this.ws.onclose = null; // 阻止自动重连
      this.ws.close();
      this.ws = null;
      console.log("WebSocket disconnected by client.");
    }
  }
}

// 导出单例
const websocketService = new WebSocketService();
export default websocketService;
