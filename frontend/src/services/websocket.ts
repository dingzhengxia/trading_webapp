// frontend/src/services/websocket.ts (终极单例版)
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';

// 在全局 window 对象上定义一个类型，用于挂载我们的服务实例
declare global {
  interface Window {
    __WEBSOCKET_SERVICE__: WebSocketService;
  }
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private isConnecting: boolean = false;
  private reconnectTimeout: number | undefined;

  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.DEV ? `${window.location.hostname}:8000` : window.location.host;
    return `${protocol}//${host}/ws`;
  }

  public connect() {
    // 如果实例已经存在并且正在连接或已连接，则不执行任何操作
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      console.log("WebSocket connect() called, but already connected or connecting.");
      return;
    }

    // 防止在连接过程中重复调用
    if (this.isConnecting) {
        console.log("WebSocket connect() called, but connection is already in progress.");
        return;
    }

    this.isConnecting = true;

    const uiStore = useUiStore();
    const url = this.getWebSocketUrl();
    console.log(`Attempting to connect to WebSocket at: ${url}`);

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log("WebSocket connection established.");
      this.isConnecting = false;
      uiStore.setStatus('已连接', false);
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
      this.isConnecting = false;
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = window.setTimeout(() => this.connect(), 5000);
    };

    this.ws.onerror = (event) => {
      console.error("WebSocket Error:", event);
      this.isConnecting = false;
      // 在这里不需要记录日志，因为 onclose 很快也会被触发并记录日志
    };
  }
}

// 核心修改：强制单例逻辑
// 如果全局实例不存在，则创建一个新的并挂载到 window
if (!window.__WEBSOCKET_SERVICE__) {
  console.log("Creating new WebSocketService singleton.");
  window.__WEBSOCKET_SERVICE__ = new WebSocketService();
}

// 始终导出全局的单例
export default window.__WEBSOCKET_SERVICE__;
