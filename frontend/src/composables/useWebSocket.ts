import { ref, onUnmounted } from 'vue'

export type WsStatus = 'connecting' | 'open' | 'closed' | 'error'

export function useWebSocket(url: string, maxRetries = 3) {
  const ws = ref<WebSocket | null>(null)
  const messages = ref<unknown[]>([])
  const status = ref<WsStatus>('connecting')
  let retries = 0
  let destroyed = false
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let pongTimeout: ReturnType<typeof setTimeout> | null = null

  function startHeartbeat() {
    stopHeartbeat()
    heartbeatTimer = setInterval(() => {
      if (ws.value?.readyState === WebSocket.OPEN) {
        ws.value.send(JSON.stringify({ type: 'ping' }))
        // 10s 内没收到 pong 则重连
        pongTimeout = setTimeout(() => {
          ws.value?.close()
        }, 10_000)
      }
    }, 30_000)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
    if (pongTimeout) { clearTimeout(pongTimeout); pongTimeout = null }
  }

  function connect() {
    if (destroyed) return
    status.value = 'connecting'
    const socket = new WebSocket(url)
    ws.value = socket

    socket.onopen = () => {
      status.value = 'open'
      retries = 0
      startHeartbeat()
    }

    socket.onmessage = (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data as string)
        if (data?.type === 'pong') {
          // 收到 pong，取消超时
          if (pongTimeout) { clearTimeout(pongTimeout); pongTimeout = null }
          return
        }
        messages.value.push(data)
      } catch {
        messages.value.push(ev.data)
      }
    }

    socket.onerror = () => {
      status.value = 'error'
    }

    socket.onclose = () => {
      stopHeartbeat()
      if (destroyed) return
      status.value = 'closed'
      if (retries < maxRetries) {
        const base = Math.min(1000 * 2 ** retries, 8000)
        const jitter = Math.random() * base * 0.3  // 30% jitter 防雷群
        retries++
        setTimeout(connect, base + jitter)
      }
    }
  }

  function send(data: unknown) {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(data))
    }
  }

  connect()

  onUnmounted(() => {
    destroyed = true
    stopHeartbeat()
    ws.value?.close()
  })

  return { ws, messages, status, send }
}
