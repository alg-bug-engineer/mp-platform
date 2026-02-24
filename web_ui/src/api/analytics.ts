import http from './http'

export type ProductMode = 'all_free' | 'commercial'

export interface RuntimeSettings {
  product_mode: ProductMode | string
  is_all_free: boolean
  billing_visible: boolean
  analytics_enabled: boolean
}

export interface AnalyticsEventPayload {
  event_type: string
  page?: string
  feature?: string
  action?: string
  method?: string
  path?: string
  status_code?: number
  duration_ms?: number
  input_name?: string
  input_length?: number
  value?: string
  metadata?: Record<string, any>
  session_id?: string
  created_at?: string
}

export interface AnalyticsSummary {
  window_days: number
  overview: {
    total_events: number
    page_views: number
    api_requests: number
    input_events: number
    login_events: number
    unique_users: number
    avg_api_duration_ms: number
    p95_api_duration_ms: number
    avg_session_seconds: number
    registered_users_total?: number
    authorized_users_total?: number
  }
  top_pages: Array<{ page: string; visits: number }>
  top_features: Array<{ feature: string; events: number }>
  top_users: Array<{
    username: string
    events: number
    page_views: number
    api_requests: number
    input_events: number
    last_active?: string | null
  }>
  daily_trend: Array<{
    date: string
    events: number
    page_views: number
    api_requests: number
    inputs: number
    users: number
  }>
  recent_events: Array<{
    event_type: string
    page?: string
    feature?: string
    action?: string
    path?: string
    method?: string
    status_code?: number
    duration_ms?: number
    username?: string
    created_at?: string
  }>
  runtime?: RuntimeSettings & { updated_at?: string }
}

export interface AnalyticsUserUsage {
  username: string
  phone?: string
  nickname?: string
  role: string
  is_active: boolean
  plan_tier: string
  plan_label: string
  ai_quota: number
  ai_used: number
  ai_remaining: number
  ai_usage_rate: number
  image_quota: number
  image_used: number
  image_remaining: number
  image_usage_rate: number
  wechat_authorized: boolean
  event_count: number
  last_active?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export const getRuntimeSettings = () => {
  return http.get<RuntimeSettings>('/wx/analytics/runtime')
}

export const updateRuntimeMode = (mode: ProductMode) => {
  return http.put<RuntimeSettings>('/wx/analytics/runtime', { mode })
}

export const reportAnalyticsEvents = (events: AnalyticsEventPayload[]) => {
  return http.post<{ accepted: number }>('/wx/analytics/events', { events })
}

export const getAnalyticsSummary = (days: number = 7, limit: number = 20) => {
  return http.get<AnalyticsSummary>(`/wx/analytics/summary?days=${days}&limit=${limit}`)
}

export const getAnalyticsUsers = (page: number = 1, pageSize: number = 20, keyword: string = '') => {
  const encoded = encodeURIComponent(String(keyword || '').trim())
  return http.get<{ total: number; page: number; page_size: number; list: AnalyticsUserUsage[] }>(
    `/wx/analytics/users?page=${page}&page_size=${pageSize}&keyword=${encoded}`
  )
}
