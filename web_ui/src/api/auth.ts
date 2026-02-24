import http from './http'
import axios from 'axios'
import { Message } from '@arco-design/web-vue'
export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  token_type: string
}

export const login = (data: LoginParams) => {
  const formData = new URLSearchParams()
  formData.append('username', data.username)
  formData.append('password', data.password)
  return http.post<LoginResult>('/wx/auth/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
  })
}

export interface RegisterParams {
  phone: string
  password: string
  nickname?: string
}

export const register = (data: RegisterParams) => {
  return http.post<{ phone: string; username: string }>('/wx/auth/register', data)
}

export interface VerifyResult {
  is_valid: boolean
  username: string
  expires_at?: number
}

export interface UserPlanSummary {
  tier: 'free' | 'pro' | 'premium' | string
  label: string
  description: string
  price_hint: string
  ai_quota: number
  ai_used: number
  ai_remaining: number
  image_quota: number
  image_used: number
  image_remaining: number
  can_generate_images: boolean
  can_publish_wechat_draft: boolean
  quota_reset_at?: string
  plan_expires_at?: string | null
}

export interface CurrentUser {
  username: string
  phone?: string
  nickname?: string
  avatar?: string
  role?: string
  permissions?: string[] | string
  is_active?: boolean
  plan?: UserPlanSummary
}

export const verifyToken = () => {
  return http.get<VerifyResult>('/wx/auth/verify')
}
let qrCodeIntervalId:number = 0;
let qrCodeCounter = 0;
let interval_status_Id:number = 0

const clearQRCodePolling = () => {
  if (qrCodeIntervalId) {
    clearInterval(qrCodeIntervalId)
    qrCodeIntervalId = 0
  }
  qrCodeCounter = 0
}

const clearStatusPolling = () => {
  if (interval_status_Id) {
    clearInterval(interval_status_Id)
    interval_status_Id = 0
  }
}

export const stopQRCodeStatusCheck = () => {
  clearStatusPolling()
}

export const QRCode = () => {
  return new Promise((resolve, reject) => {
    clearQRCodePolling()
    
    http.get('/wx/auth/qr/code').then(res => {
      if (!res?.code) {
        reject(new Error(res?.msg || '获取二维码失败，请稍后重试'))
        return
      }
      if (res?.is_exists) {
        resolve(res)
        return
      }
      const maxAttempts = 18;
      qrCodeIntervalId = setInterval(() => {
        qrCodeCounter++;
        if(qrCodeCounter > maxAttempts) {
          clearQRCodePolling()
          reject(new Error('二维码生成超时，请检查服务端微信授权依赖后重试'));
          return;
        }

        Promise.allSettled([
          axios.head(res?.code),
          http.get("/wx/auth/qr/status"),
        ]).then(results => {
          const headResult = results[0]
          const statusResult = results[1]

          if (statusResult.status === 'fulfilled') {
            const statusData: any = statusResult.value || {}
            if (statusData?.error_message) {
              clearQRCodePolling()
              reject(new Error(String(statusData.error_message)))
              return
            }
            if (statusData?.login_status) {
              clearQRCodePolling()
              resolve(res)
              return
            }
          }

          if (headResult.status === 'fulfilled' && headResult.value?.status === 200) {
            clearQRCodePolling()
            resolve(res)
            return
          }

          if (qrCodeCounter >= maxAttempts) {
            clearQRCodePolling()
            reject(new Error('二维码生成失败，请稍后重试'))
          }
        }).catch(err => {
          if(qrCodeCounter >= maxAttempts) {
            clearQRCodePolling()
            reject(err);
          }
        })
      }, 1000)
    }).catch(reject)
  })
}

export const checkQRCodeStatus = () => {
  return new Promise((resolve, reject) => {
      clearStatusPolling()
      let attempts = 0
      const maxAttempts = 60 // 3 minutes
      interval_status_Id = setInterval(() => {
        attempts += 1
        if (attempts > maxAttempts) {
          clearStatusPolling()
          reject(new Error('扫码授权超时，请重新获取二维码'))
          return
        }
        http.get("/wx/auth/qr/status").then(response => {
          if (response?.error_message) {
            clearStatusPolling()
            reject(new Error(String(response.error_message)))
            return
          }
          if(response?.login_status){
            Message.success("授权成功")
            clearStatusPolling()
            resolve(response)
          }
        }).catch(err => {
          if (attempts >= maxAttempts) {
            clearStatusPolling()
            reject(err)
          }
        })
      }, 3000)
  })
}
export const refreshToken = () => {
  return http.post<LoginResult>('/wx/auth/refresh')
}

export const logout = () => {
  return http.post('/wx/auth/logout')
}

export const getCurrentUser = () => {
  return http.get<CurrentUser>('/wx/user')
}

export interface WechatAuthStatus {
  authorized: boolean
  token: string
  cookie: string
  wx_app_name?: string
  wx_user_name?: string
  expiry_time?: string
  updated_at?: string | null
}

export const getWechatAuthStatus = (strict: boolean = false) => {
  const flag = strict ? '1' : '0'
  return http.get<WechatAuthStatus>(`/wx/auth/wechat/auth?strict=${flag}`)
}

export const mockBindWechatAuth = (data: {
  owner_id?: string
  token: string
  cookie: string
  fingerprint?: string
  wx_app_name?: string
  wx_user_name?: string
  expiry_time?: string
}) => {
  return http.post('/wx/auth/wechat/mock-bind', data)
}
