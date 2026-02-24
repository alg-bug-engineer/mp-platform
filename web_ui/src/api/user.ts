import http from './http'

export interface UserInfo {
  username: string
  phone?: string
  nickname: string
  email: string
  avatar: string
  wechat_app_id?: string
  wechat_app_secret_set?: boolean
  role: string
  is_active: boolean
  created_at: string
  plan?: {
    tier: string
    label: string
    ai_quota: number
    ai_used: number
    image_quota: number
    image_used: number
    plan_expires_at?: string | null
  }
}

export interface UserListItem {
  username: string
  phone?: string
  nickname?: string
  email?: string
  avatar?: string
  role?: string
  is_active?: boolean
  plan_tier?: string
  plan_label?: string
  ai_quota?: number
  ai_used?: number
  image_quota?: number
  image_used?: number
  wechat_authorized?: boolean
  wechat_auth?: {
    authorized: boolean
    token: string
    cookie: string
    wx_app_name?: string
    wx_user_name?: string
    expiry_time?: string
    updated_at?: string | null
  }
  mp_count?: number
  article_count?: number
  event_count?: number
  last_active?: string | null
  created_at?: string
  updated_at?: string
}

export interface UserAdminDetail {
  user: {
    username: string
    phone?: string
    nickname?: string
    email?: string
    avatar?: string
    role?: string
    is_active?: boolean
    created_at?: string | null
    updated_at?: string | null
  }
  plan: {
    tier: string
    label: string
    ai_quota: number
    ai_used: number
    image_quota: number
    image_used: number
    quota_reset_at?: string | null
    plan_expires_at?: string | null
  }
  usage: {
    mp_count: number
    article_count: number
    task_count: number
    event_count: number
    last_active?: string | null
  }
  wechat_auth: {
    authorized: boolean
    token: string
    cookie: string
    wx_app_name?: string
    wx_user_name?: string
    expiry_time?: string
    updated_at?: string | null
    fingerprint?: string
    raw_payload?: Record<string, any>
  }
  subscriptions: Array<{
    id: string
    mp_name: string
    faker_id: string
    status: number
    created_at?: string | null
    updated_at?: string | null
  }>
}

export interface UpdateUserParams {
  username?: string
  nickname?: string
  email?: string
  avatar?: string
  wechat_app_id?: string
  wechat_app_secret?: string
  clear_wechat_app_secret?: boolean
  password?: string
  is_active?: boolean
  plan_tier?: string
  monthly_ai_quota?: number
  monthly_image_quota?: number
  monthly_ai_used?: number
  monthly_image_used?: number
  plan_expires_at?: string | null
}

export const getUserInfo = () => {
  return http.get<{code: number, data: UserInfo}>('/wx/user')
}

export const getUserList = (page: number = 1, pageSize: number = 20, keyword: string = '') => {
  const encodedKeyword = encodeURIComponent(String(keyword || '').trim())
  return http.get<{ total: number; page: number; page_size: number; list: UserListItem[] }>(
    `/wx/user/list?page=${page}&page_size=${pageSize}&keyword=${encodedKeyword}`
  )
}

export const updateUserInfo = (data: UpdateUserParams) => {
  return http.put<{code: number, message: string}>('/wx/user', data)
}

export const updateUserPlan = (username: string, data: UpdateUserParams) => {
  return http.put<{ username: string; plan: Record<string, any> }>(`/wx/user/${username}/plan`, data)
}

export const resetUserPlanUsage = (username: string) => {
  return http.post<{ username: string; plan: Record<string, any> }>(`/wx/user/${username}/plan/reset-usage`)
}

export const getUserAdminDetail = (username: string, maskSensitive = false) => {
  return http.get<UserAdminDetail>(`/wx/user/${username}/admin-detail?mask_sensitive=${maskSensitive ? '1' : '0'}`)
}

export const deleteUser = (username: string) => {
  return http.delete<{ username: string; deleted: Record<string, number> }>(`/wx/user/${username}`)
}

export interface ChangePasswordParams {
  old_password: string
  new_password: string
}

export const changePassword = (data: ChangePasswordParams) => {
  return http.put<{code: number, message: string}>('/wx/user/password', data, {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token')}`
    }
  })
}

// 保持旧方法向后兼容
export const changePasswordLegacy = (newPassword: string) => {
  return updateUserInfo({ password: newPassword })
}

export const toggleUserStatus = (active: boolean) => {
  return updateUserInfo({ is_active: active })
}

export const uploadAvatar = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return http.post<{code: number, url: string}>('/wx/user/avatar', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}
