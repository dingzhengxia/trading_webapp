// frontend/src/services/websocket.ts (最终诊断版)
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
  private heartbeatInterval: number | undefined;

  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.DEV ? `${window.location.hostname}:8000` : window.location.host;
    return `${protocol}//${host}/ws`;
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    console.log('[WS] Starting heartbeat (ping every 5s)...');
    this.heartbeatInterval = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        console.log('[WS] >> PING');
        this.ws.send('ping');
      }
    }, 5000);
  }

  private stopHeartbeat() {
    if(this.heartbeatInterval) {
        console.log('[WS] Stopping heartbeat.');
        clearInterval(this.heartbeatInterval);
        this.heartbeatInterval = undefined;
    }
  }

  public connect() {
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
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
      console.log("[WS] ✅ Connection established.");
      this.isConnecting = false;
      useUiStore().setStatus('已连接', false);
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      // --- 核心修改：增加接收日志 ---
      console.log('[WS] << RECV:', event.data);
      // -----------------------------

      const data = JSON.parse(event.data);

      // 确保每次都获取最新的 store 实例
      const uiStore = useUiStore();
      const positionStore = usePositionStore();

      if (data.type === 'pong') {
        console.log('[WS] << PONG');
        return;
      }

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
      console.error("[WS] ❌ Connection closed. Reconnecting in 5s...");
      this.stopHeartbeat();
      const uiStore = useUiStore();
      uiStore.logStore.addLog({ message: '--- WebSocket 连接断开，5秒后重试... ---', level: 'error', timestamp: new Date().toLocaleTimeString() });
      uiStore.setStatus('已断开', false);
      this.ws = null;
      this.isConnecting = false;
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = window.setTimeout(() => this.connect(), 5000);
    };

    this.ws.onerror = (event) => {
      console.error("[WS] ❌ WebSocket Error:", event);
      this.isConnecting = false;
    };
  }
}

if (!window.__WEBSOCKET_SERVICE__) {
  window.__WEBSOCKET_SERVICE__ = new WebSocketService();
}

export default window.__WEBSOCKET_SERVICE__;
