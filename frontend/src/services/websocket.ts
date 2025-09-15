// frontend/src/services/websocket.ts (最终修复版)
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';

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
    this.heartbeatInterval = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 20000); // 延长到20秒一次
  }

  private stopHeartbeat() {
    clearInterval(this.heartbeatInterval);
    this.heartbeatInterval = undefined;
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

      const uiStore = useUiStore();
      // --- 核心修改在这里 ---
      // 如果当前没有任务在运行，才更新状态为“已连接”
      // 如果有任务在运行，则不改变现有的 "正在执行..." 状态文字
      if (!uiStore.isRunning) {
        uiStore.setStatus('已连接'); // 不再传递 running=false
      }
      // --- 修改结束 ---

      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'pong') return;

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
      // 在断开时，只更新文字，不改变 isRunning 状态
      uiStore.setStatus('已断开');

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

  public disconnect() {
      this.stopHeartbeat();
      clearTimeout(this.reconnectTimeout);
      if (this.ws) {
          this.ws.onclose = null;
          this.ws.close();
          this.ws = null;
      }
  }
}

if (!window.__WEBSOCKET_SERVICE__) {
  window.__WEBSOCKET_SERVICE__ = new WebSocketService();
}

export default window.__WEBSOCKET_SERVICE__;
