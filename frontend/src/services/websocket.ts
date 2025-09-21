// frontend/src/services/websocket.ts (优化心跳后的完整代码)
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'

declare global {
  interface Window {
    __WEBSOCKET_SERVICE__: WebSocketService
  }
}

class WebSocketService {
  private ws: WebSocket | null = null
  private isConnecting: boolean = false
  private reconnectTimeoutId?: number

  // REFACTOR: 添加心跳和连接超时相关属性
  private heartbeatIntervalId?: number
  private connectionTimeoutId?: number
  private readonly HEARTBEAT_INTERVAL = 25000 // 25秒发送一次ping
  private readonly CONNECTION_TIMEOUT = this.HEARTBEAT_INTERVAL + 5000 // 30秒没收到任何消息则认为超时

  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = import.meta.env.DEV ? `${window.location.hostname}:8000` : window.location.host
    return `${protocol}//${host}/ws`
  }

  // REFACTOR: 启动心跳和连接检查
  private startHealthChecks() {
    this.stopHealthChecks() // 先确保旧的定时器被清除
    this.heartbeatIntervalId = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        // 发送JSON格式的心跳包
        this.ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, this.HEARTBEAT_INTERVAL)
    this.resetConnectionTimeout()
  }

  // REFACTOR: 停止所有健康检查相关的定时器
  private stopHealthChecks() {
    clearInterval(this.heartbeatIntervalId)
    clearTimeout(this.connectionTimeoutId)
    this.heartbeatIntervalId = undefined
    this.connectionTimeoutId = undefined
  }

  // REFACTOR: 重置连接超时定时器
  private resetConnectionTimeout() {
    clearTimeout(this.connectionTimeoutId)
    this.connectionTimeoutId = window.setTimeout(() => {
      console.error(
        '[WS] ❌ Connection timeout. No message received in the last 30 seconds. Forcing reconnect.',
      )
      this.ws?.close() // 主动关闭会触发 onclose 中的重连逻辑
    }, this.CONNECTION_TIMEOUT)
  }

  public connect() {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)
    ) {
      return
    }
    if (this.isConnecting) {
      return
    }

    this.isConnecting = true
    const url = this.getWebSocketUrl()
    console.log(`[WS] Attempting to connect to: ${url}`)
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      console.log('[WS] ✅ Connection established.')
      this.isConnecting = false

      const uiStore = useUiStore()
      if (!uiStore.isRunning) {
        uiStore.setStatus('已连接')
      }
      this.startHealthChecks() // 连接成功后启动健康检查
    }

    this.ws.onmessage = (event) => {
      this.resetConnectionTimeout() // 收到任何消息（包括pong）都说明连接是健康的，重置超时

      const data = JSON.parse(event.data)

      // 忽略后端发来的 pong 消息，它只用于重置超时
      if (data.type === 'pong') {
        return
      }

      const uiStore = useUiStore()
      const positionStore = usePositionStore()

      switch (data.type) {
        case 'log':
          uiStore.logStore.addLog(data.payload)
          break
        case 'status':
          uiStore.setStatus(data.payload.message, data.payload.isRunning)
          break
        case 'progress_update':
          uiStore.updateProgress(data.payload)
          break
        case 'position_closed':
          const { full_symbol, ratio } = data.payload
          if (Math.abs(ratio - 1.0) < 1e-9) {
            positionStore.removePositions([full_symbol])
          } else {
            positionStore.updatePositionContracts(full_symbol, ratio)
          }
          break
      }
    }

    this.ws.onclose = () => {
      console.error('[WS] ❌ Connection closed. Reconnecting in 5s...')
      this.stopHealthChecks() // 连接关闭时必须停止所有健康检查
      const uiStore = useUiStore()

      if (!uiStore.isStopping) {
        // 如果不是用户主动停止任务导致的断开
        uiStore.setStatus('已断开')
      }

      this.ws = null
      this.isConnecting = false
      clearTimeout(this.reconnectTimeoutId)
      this.reconnectTimeoutId = window.setTimeout(() => this.connect(), 5000)
    }

    this.ws.onerror = (event) => {
      console.error('[WS] ❌ WebSocket Error:', event)
      this.isConnecting = false
      this.ws?.close() // 发生错误时，也尝试关闭以触发 onclose 的重连逻辑
    }
  }

  public disconnect() {
    this.stopHealthChecks()
    clearTimeout(this.reconnectTimeoutId)
    if (this.ws) {
      this.ws.onclose = null // 移除 onclose 处理器以防止重连
      this.ws.close()
      this.ws = null
    }
  }
}

if (!window.__WEBSOCKET_SERVICE__) {
  window.__WEBSOCKET_SERVICE__ = new WebSocketService()
}

export default window.__WEBSOCKET_SERVICE__
