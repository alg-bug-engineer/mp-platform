import type { Router } from 'vue-router'
import { loadRuntimeSettings } from '@/utils/runtime'

export type TrackEvent = {
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
  created_at?: string
}

const SESSION_KEY = 'analytics:session-id'
const INPUT_THROTTLE_MS = 12000
const FLUSH_INTERVAL_MS = 6000
const BATCH_LIMIT = 30
const API_URL = `${import.meta.env.VITE_API_BASE_URL || ''}api/v1/wx/analytics/events`

let queue: TrackEvent[] = []
let flushing = false
let started = false
let analyticsEnabled = true
const inputTimeMap = new Map<string, number>()

const createSessionId = () => {
  try {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  } catch {
    // ignored
  }
  return `sess-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

const getSessionId = () => {
  const cached = localStorage.getItem(SESSION_KEY)
  if (cached) return cached
  const sessionId = createSessionId()
  localStorage.setItem(SESSION_KEY, sessionId)
  return sessionId
}

const authHeaders = () => {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Session-Id': getSessionId(),
  }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

const postBatch = async (events: TrackEvent[]) => {
  if (!events.length) return
  const body = JSON.stringify({ events })

  if (document.hidden && navigator.sendBeacon) {
    try {
      const blob = new Blob([body], { type: 'application/json' })
      const ok = navigator.sendBeacon(API_URL, blob)
      if (ok) return
    } catch {
      // ignored
    }
  }

  await fetch(API_URL, {
    method: 'POST',
    headers: authHeaders(),
    body,
    keepalive: true,
  })
}

const flushQueue = async () => {
  if (flushing || !queue.length || !analyticsEnabled) return
  flushing = true
  const current = queue.slice(0, BATCH_LIMIT)
  queue = queue.slice(BATCH_LIMIT)

  try {
    await postBatch(current)
  } catch {
    queue = [...current, ...queue].slice(0, 400)
  } finally {
    flushing = false
  }
}

export const trackEvent = (payload: TrackEvent) => {
  if (!analyticsEnabled) return
  const event: TrackEvent = {
    ...payload,
    page: payload.page || window.location.pathname,
    created_at: payload.created_at || new Date().toISOString(),
  }
  queue.push(event)
  if (queue.length >= BATCH_LIMIT) {
    void flushQueue()
  }
}

export const trackPageView = (path: string) => {
  trackEvent({
    event_type: 'page_view',
    page: path,
    path,
    feature: 'navigation',
    action: 'visit',
    metadata: {
      title: document.title,
      referrer: document.referrer,
    },
  })
}

const getElementLabel = (element: Element | null): string => {
  if (!element) return ''
  const el = element as HTMLElement
  const direct = (el.getAttribute('data-track-label') || el.getAttribute('aria-label') || '').trim()
  if (direct) return direct.slice(0, 60)
  const text = (el.textContent || '').trim().replace(/\s+/g, ' ')
  return text.slice(0, 60)
}

const handleClick = (event: Event) => {
  const target = event.target as HTMLElement | null
  const clickable = target?.closest('button,a,[role="button"],.arco-btn') as HTMLElement | null
  if (!clickable) return

  const feature = (clickable.getAttribute('data-track-feature') || '').trim() || 'ui'
  const action = (clickable.getAttribute('data-track-action') || '').trim() || 'click'
  const label = getElementLabel(clickable)

  trackEvent({
    event_type: 'click',
    feature,
    action,
    value: label,
    metadata: {
      tag: clickable.tagName,
      class: (clickable.className || '').toString().slice(0, 120),
    },
  })
}

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement | null
  if (!target) return

  const tag = (target.tagName || '').toLowerCase()
  const type = (target as HTMLInputElement).type || ''
  if (tag !== 'input' && tag !== 'textarea') return
  if (String(type).toLowerCase() === 'password') return

  const key = `${window.location.pathname}|${target.name || target.id || target.placeholder || 'field'}`
  const now = Date.now()
  const last = inputTimeMap.get(key) || 0
  if (now - last < INPUT_THROTTLE_MS) return
  inputTimeMap.set(key, now)

  const value = String(target.value || '')
  trackEvent({
    event_type: 'input',
    feature: 'form',
    action: 'typing',
    input_name: (target.name || target.id || target.placeholder || 'field').slice(0, 120),
    input_length: value.length,
    metadata: {
      tag,
      type,
    },
  })
}

export const bootstrapAnalytics = async (router: Router) => {
  if (started) return
  started = true

  const runtime = await loadRuntimeSettings()
  analyticsEnabled = Boolean(runtime?.analytics_enabled !== false)
  if (!analyticsEnabled) return

  router.afterEach((to) => {
    trackPageView(to.fullPath)
  })

  window.addEventListener('click', handleClick, true)
  window.addEventListener('input', handleInput, true)
  window.addEventListener('beforeunload', () => {
    void flushQueue()
  })
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      void flushQueue()
    }
  })

  window.setInterval(() => {
    void flushQueue()
  }, FLUSH_INTERVAL_MS)

  trackPageView(window.location.pathname + window.location.search)
}
