import axios from 'axios'
import { ElMessage } from 'element-plus'

const client = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

// 响应拦截：统一错误提示
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg =
      err.response?.data?.detail ??
      err.response?.data?.message ??
      (err.code === 'ECONNABORTED' ? '请求超时，请检查网络' : '请求失败，请稍后重试')
    ElMessage.error(String(msg))
    return Promise.reject(err)
  },
)

export default client

