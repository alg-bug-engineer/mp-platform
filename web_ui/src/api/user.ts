import http from './http'

export interface UserInfo {
  username: string
  phone?: string
  nickname: string
  email: string
  avatar: string
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
  image_quota?: number
  created_at?: string
  updated_at?: string
}

export interface UpdateUserParams {
  username?: string
  nickname?: string
  email?: string
  avatar?: string
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

export const getUserList = (page: number = 1, pageSize: number = 20) => {
  return http.get<{ total: number; page: number; page_size: number; list: UserListItem[] }>(
    `/wx/user/list?page=${page}&page_size=${pageSize}`
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
