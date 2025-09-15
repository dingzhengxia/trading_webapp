// frontend/src/services/websocket.ts (完整代码)
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';

class WebSocketService {
  private ws: WebSocket | null = null;

  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.DEV ? `${window.location.hostname}:8000` : window.location.host;
    return `${protocol}//${host}/ws`;
  }

  connect() {
    const uiStore = useUiStore();

    const url = this.getWebSocketUrl();
    console.log(`Connecting to WebSocket at: ${url}`);
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
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
      uiStore.logStore.addLog({ message: '--- WebSocket 连接断开，5秒后重试... ---', level: 'error', timestamp: new Date().toLocaleTimeString() });
      uiStore.setStatus('已断开', false);
      setTimeout(() => this.connect(), 5000);
    };

    this.ws.onerror = (event) => {
        console.error("WebSocket Error:", event);
        uiStore.logStore.addLog({ message: '--- WebSocket 连接发生错误 ---', level: 'error', timestamp: new Date().toLocaleTimeString() });
    }
  }
}

export default new WebSocketService();
