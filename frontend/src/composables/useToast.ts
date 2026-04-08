import { inject } from 'vue'

export interface ToastMessage {
  type: 'info' | 'warning' | 'error' | 'success'
  message: string
}

const TOAST_KEY = Symbol('toast')

export function useToast() {
  // Minimal implementation: emit to console + use NToast if injected
  const add = inject<(msg: ToastMessage) => void>(TOAST_KEY, (msg) => {
    // fallback: log to console when no provider
    console.warn(`[Toast ${msg.type}]`, msg.message)
  })
  return { add }
}

export { TOAST_KEY }
