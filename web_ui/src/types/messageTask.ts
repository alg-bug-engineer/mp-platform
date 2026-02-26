export interface MessageTask {
  id: string
  name: string
  message_type: number
  message_template: string
  web_hook_url: string
  mps_id: any // JSON类型
  status: number
  cron_exp?: string
  auto_compose_sync_enabled?: number
  auto_compose_platform?: string
  auto_compose_instruction?: string
  auto_compose_topk?: number
  auto_compose_last_article_id?: string
  auto_compose_last_sync_at?: string
  csdn_publish_enabled?: number
  csdn_publish_topk?: number
  task_type?: string          // 'crawl' | 'publish'
  publish_platforms?: string[] // ['wechat_mp', 'csdn']
  created_at: string
  updated_at: string
}

export interface MessageTaskCreate {
  name: string
  message_type: number
  message_template: string
  web_hook_url: string
  mps_id: any
  status?: number
  cron_exp?: string
  auto_compose_sync_enabled?: number
  auto_compose_platform?: string
  auto_compose_instruction?: string
  auto_compose_topk?: number
  csdn_publish_enabled?: number
  csdn_publish_topk?: number
  task_type?: string
  publish_platforms?: string[]
}

export interface MessageTaskUpdate {
  name?: string
  message_type?: number
  message_template?: string
  web_hook_url?: string
  mps_id?: any
  status?: number
  cron_exp?: string
  auto_compose_sync_enabled?: number
  auto_compose_platform?: string
  auto_compose_instruction?: string
  auto_compose_topk?: number
  csdn_publish_enabled?: number
  csdn_publish_topk?: number
  task_type?: string
  publish_platforms?: string[]
}
