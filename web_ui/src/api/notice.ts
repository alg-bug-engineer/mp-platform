import http from './http'

export interface UserNotice {
  id: string
  owner_id: string
  title: string
  content: string
  notice_type: string  // task/compose/analytics/imitation
  status: number       // 0=未读 1=已读
  ref_id?: string | null
  created_at?: string | null
}

export interface NoticeListParams {
  page?: number
  page_size?: number
  status?: number
}

export const listNotices = (params: NoticeListParams = {}) => {
  const { page = 1, page_size = 20, status } = params
  let url = `/wx/notices?page=${page}&page_size=${page_size}`
  if (status !== undefined) {
    url += `&status=${status}`
  }
  return http.get<{ list: UserNotice[]; total: number; page: number; page_size: number }>(url)
}

export const getUnreadCount = () => {
  return http.get<{ count: number }>('/wx/notices/unread-count')
}

export const markRead = (id: string) => {
  return http.put<{ code: number; message: string }>(`/wx/notices/${id}/read`)
}

export const markAllRead = () => {
  return http.put<{ code: number; message: string }>('/wx/notices/read-all')
}

export const deleteNotice = (id: string) => {
  return http.delete<{ code: number; message: string }>(`/wx/notices/${id}`)
}
