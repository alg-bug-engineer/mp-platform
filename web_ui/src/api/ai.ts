import http from './http'

export interface AIProfile {
  provider_name: string
  model_name: string
  base_url: string
  api_key: string
  temperature: number
}

export interface ComposePlatformOption {
  key: string
  label: string
  style: string
  structure: string
}

export interface ComposeStyleOption {
  key: string
  label: string
  desc: string
}

export interface ComposeLengthOption {
  key: string
  label: string
}

export interface ComposeOptions {
  platforms: ComposePlatformOption[]
  styles: ComposeStyleOption[]
  lengths: ComposeLengthOption[]
  jimeng?: {
    req_key?: string
    fallback_req_keys?: string[]
    req_key_candidates?: string[]
  }
  rules_file: string
}

export interface AIComposePayload {
  instruction?: string
  platform?: string
  style?: string
  length?: string
  image_count?: number
  audience?: string
  tone?: string
  generate_images?: boolean
}

export interface AIComposeResult {
  article_id: string
  mode: 'analyze' | 'create' | 'rewrite'
  result: string
  recommended_tags?: string[]
  image_prompts?: string[]
  images?: string[]
  image_notice?: string
  options?: Record<string, any>
  plan?: PlanSummary
}

export interface PlanSummary {
  tier: string
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
  highlights: string[]
  quota_reset_at?: string | null
  plan_expires_at?: string | null
}

export interface PlanCatalogItem {
  tier: string
  label: string
  description: string
  price_hint: string
  ai_quota: number
  image_quota: number
  can_generate_images: boolean
  can_publish_wechat_draft: boolean
  highlights: string[]
}

export interface DraftPublishPayload {
  title?: string
  content: string
  digest?: string
  author?: string
  cover_url?: string
  platform?: string
  mode?: string
  sync_to_wechat?: boolean
  queue_on_fail?: boolean
  max_retries?: number
  items?: DraftPublishItem[]
}

export interface DraftPublishItem {
  title: string
  content: string
  digest?: string
  author?: string
  cover_url?: string
}

export interface DraftRecord {
  id: string
  article_id: string
  title: string
  content: string
  platform: string
  mode: string
  created_at: string
  metadata?: Record<string, any>
}

export interface WorkbenchOverview {
  plan: PlanSummary
  plan_catalog: PlanCatalogItem[]
  stats: {
    mp_count: number
    article_count: number
    unread_count: number
    local_draft_count: number
    pending_publish_count: number
  }
  activity?: {
    days: number
    draft_count_7d: number
    avg_daily_draft: number
    publish_total_7d: number
    publish_success_7d: number
    publish_failed_7d: number
    publish_pending_7d: number
    publish_success_rate_7d: number | null
    trend: Array<{
      date: string
      drafts: number
      publish_success: number
      publish_failed: number
    }>
  }
  wechat_auth: {
    authorized: boolean
    hint: string
  }
  wechat_whitelist?: {
    ips: string[]
    guide: string
    doc_url?: string
  }
  recent_drafts: DraftRecord[]
}

export const getAIProfile = () => {
  return http.get<AIProfile>('/wx/ai/profile')
}

export const updateAIProfile = (data: {
  base_url: string
  api_key: string
  model_name: string
  temperature: number
}) => {
  return http.put<AIProfile>('/wx/ai/profile', data)
}

export const getComposeOptions = () => {
  return http.get<ComposeOptions>('/wx/ai/compose/options')
}

export const getPlanCatalog = () => {
  return http.get<PlanCatalogItem[]>('/wx/ai/plans')
}

export const getWorkbenchOverview = () => {
  return http.get<WorkbenchOverview>('/wx/ai/workbench/overview')
}

export const recommendTags = (items: Array<{ article_id: string; title: string }>, limit: number = 6) => {
  return http.post<Array<{ article_id: string; title: string; tags: string[] }>>('/wx/ai/tags/recommend', {
    items,
    limit,
  })
}

export const aiAnalyze = (articleId: string, payload: AIComposePayload = {}) => {
  return http.post<AIComposeResult>(`/wx/ai/articles/${articleId}/analyze`, payload)
}

export const aiCreate = (articleId: string, payload: AIComposePayload = {}) => {
  return http.post<AIComposeResult>(`/wx/ai/articles/${articleId}/create`, payload)
}

export const aiRewrite = (articleId: string, payload: AIComposePayload = {}) => {
  return http.post<AIComposeResult>(`/wx/ai/articles/${articleId}/rewrite`, payload)
}

export const publishDraft = (articleId: string, payload: DraftPublishPayload) => {
  return http.post<{
    local_draft: DraftRecord | DraftRecord[]
    local_drafts: DraftRecord[]
    wechat: {
      requested: boolean
      synced: boolean
      message: string
      raw?: Record<string, any>
      queued?: number
    }
    queued_tasks?: PublishTask[]
    plan: PlanSummary
  }>(`/wx/ai/articles/${articleId}/publish-draft`, payload)
}

export const getDrafts = (limit: number = 20) => {
  return http.get<DraftRecord[]>(`/wx/ai/drafts?limit=${limit}`)
}

export interface DraftUpdatePayload {
  title?: string
  content?: string
  platform?: string
  mode?: string
}

export const updateDraft = (draftId: string, payload: DraftUpdatePayload) => {
  return http.put<DraftRecord>(`/wx/ai/drafts/${draftId}`, payload)
}

export const deleteDraft = (draftId: string) => {
  return http.delete<{ id: string; deleted: boolean }>(`/wx/ai/drafts/${draftId}`)
}

export interface DraftSyncPayload {
  title?: string
  content?: string
  digest?: string
  author?: string
  cover_url?: string
  platform?: string
  queue_on_fail?: boolean
  max_retries?: number
}

export const syncDraftToWechat = (draftId: string, payload: DraftSyncPayload) => {
  return http.post<{
    wechat: {
      requested: boolean
      synced: boolean
      message: string
      raw?: Record<string, any>
      queued?: number
    }
    queued_task?: PublishTask
  }>(`/wx/ai/drafts/${draftId}/sync`, payload)
}

export interface PublishTask {
  id: string
  article_id: string
  title: string
  platform: string
  status: string
  retries: number
  max_retries: number
  next_retry_at?: string | null
  last_error?: string
  created_at?: string
}

export const getPublishTasks = (params?: { status?: string; limit?: number }) => {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  query.set('limit', String(params?.limit || 30))
  return http.get<PublishTask[]>(`/wx/ai/publish/tasks?${query.toString()}`)
}

export const processPublishTasks = (limit: number = 10) => {
  return http.post<{ total: number; success: number; failed: number; details: any[] }>(
    '/wx/ai/publish/tasks/process',
    { limit }
  )
}

export const retryPublishTask = (taskId: string) => {
  return http.post<{ ok: boolean; message: string; task: PublishTask }>(`/wx/ai/publish/tasks/${taskId}/retry`)
}

export const deletePublishTask = (taskId: string) => {
  return http.delete<{ id: string; deleted: boolean }>(`/wx/ai/publish/tasks/${taskId}`)
}
