import axios from 'axios'
import { getToken } from '@/utils/auth'
import { Message } from '@arco-design/web-vue'
import router from '@/router'

const SESSION_KEY = 'analytics:session-id'

const getSessionId = () => {
  const cached = localStorage.getItem(SESSION_KEY)
  if (cached) return cached
  const next = `sess-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
  localStorage.setItem(SESSION_KEY, next)
  return next
}
// 创建axios实例
const http = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL || '') + 'api/v1/',
  timeout: 100000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }
})

// 请求拦截器
http.interceptors.request.use(
  config => {
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    config.headers['X-Session-Id'] = getSessionId()
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
http.interceptors.response.use(
  response => {
    // 处理标准响应格式
    if (response.data?.code === 0) {
      return response.data?.data||response.data?.detail||response.data||response
    }
    if(response.data?.code==401){
      router.push("/login")
      return Promise.reject("未登录或登录已过期，请重新登录。")
    }
    const data=response.data?.detail||response.data
    const errorMsg = data?.message || '请求失败'
    if(response.headers['content-type']==='application/json') {
      Message.error(errorMsg)
    }else{
      return response.data
    }
    // Reject with string message instead of object to avoid "[object Object]" error
    return Promise.reject(errorMsg)
  },
  error => {
     if(error.status==401){
      router.push("/login")
    }
    // console.log(error)
    // 统一错误处理
    let errorMsg = error?.message || '请求错误'

    // 处理 FastAPI 422 验证错误
    if (error?.response?.status === 422) {
      const detail = error?.response?.data?.detail
      if (Array.isArray(detail) && detail.length > 0) {
        // FastAPI 验证错误格式: [{loc: [...], msg: "...", type: "..."}]
        errorMsg = detail.map((err: any) => err.msg || err.type).join('; ')
      } else {
        errorMsg = '请求参数验证失败'
      }
    } else {
      // 处理其他错误格式
      errorMsg = error?.response?.data?.message ||
                 error?.response?.data?.detail?.message ||
                 error?.response?.data?.detail ||
                 error?.message ||
                 '请求错误'
    }
    // Message.error(errorMsg)
    return Promise.reject(errorMsg)
  }
)

export default http
