import http from './http'
import type { ConfigManagement, ConfigManagementUpdate } from '@/types/configManagement'

export interface ConfigListResponse {
  list: ConfigManagement[]
  page: {
    limit: number
    offset: number
  }
  total: number
}

export const listConfigs = (params?: { page?: number; pageSize?: number; keyword?: string }) => {
  const page = params?.page || 1
  const pageSize = params?.pageSize || 10
  const keyword = String(params?.keyword || '').trim()
  const apiParams = {
    offset: (page - 1) * pageSize,
    limit: pageSize,
    ...(keyword ? { keyword } : {})
  }
  return http.get<ConfigListResponse>('/wx/configs', { params: apiParams })
}
export const getConfig = (key: string) => {
  return http.get<ConfigManagement>(`/wx/configs/${key}`)
}



export const createConfig = (data: ConfigManagementUpdate) => {
  return http.post('/wx/configs', data)
}

export const updateConfig = (key: string, data: ConfigManagementUpdate) => {
  return http.put(`/wx/configs/${key}`, data)
}

export const deleteConfig = (key: string) => {
  return http.delete(`/wx/configs/${key}`)
}
