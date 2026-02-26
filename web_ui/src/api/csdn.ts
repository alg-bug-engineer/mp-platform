import http from './http'

export interface CsdnAuthStatus {
  authorized: boolean
  status: 'valid' | 'expired'
  csdn_username: string
  updated_at: string | null
}

export interface CsdnQrStartResult {
  qr_image: string   // data:image/png;base64,...
  status: string
  expires_in: number
}

export interface CsdnQrStatusResult {
  session_status: 'pending' | 'success' | 'timeout' | 'failed' | 'cancelled' | 'none'
  csdn_username?: string
  csdn_auth?: CsdnAuthStatus
}

export const csdnApi = {
  /** 启动 CSDN 扫码登录会话，返回初始 QR 截图 */
  startQr: () => http.post<CsdnQrStartResult>('/wx/csdn/auth/qr/start'),

  /** 重新截取当前 QR 图片（用于刷新过期二维码） */
  getQrImage: () => http.get<{ status: string; qr_image: string }>('/wx/csdn/auth/qr/image'),

  /** 轮询扫码状态 */
  getQrStatus: () => http.get<CsdnQrStatusResult>('/wx/csdn/auth/qr/status'),

  /** 取消当前扫码会话 */
  cancelQr: () => http.post('/wx/csdn/auth/qr/cancel'),

  /** 查询 DB 中保存的授权状态 */
  getAuthStatus: () => http.get<CsdnAuthStatus>('/wx/csdn/auth/status'),

  /** 清除授权（重置为 expired） */
  clearAuth: () => http.delete('/wx/csdn/auth/session'),
}
