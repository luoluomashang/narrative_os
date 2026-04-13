import axios from 'axios'
import { ElMessage } from 'element-plus'

const client = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

function resolveErrorMessage(payload: unknown): string | null {
  if (typeof payload === 'string' && payload.trim()) {
    return payload
  }

  if (Array.isArray(payload)) {
    const lines = payload
      .map((item) => resolveErrorMessage(item))
      .filter((item): item is string => Boolean(item))
    return lines.length > 0 ? lines.join('；') : null
  }

  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    return (
      resolveErrorMessage(record.detail) ??
      resolveErrorMessage(record.message) ??
      resolveErrorMessage(record.msg) ??
      null
    )
  }

  return null
}

// 响应拦截：统一错误提示
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg =
      resolveErrorMessage(err.response?.data) ??
      (err.code === 'ECONNABORTED' ? '请求超时，请检查网络' : '请求失败，请稍后重试')
    ElMessage.error(String(msg))
    return Promise.reject(err)
  },
)

export default client

