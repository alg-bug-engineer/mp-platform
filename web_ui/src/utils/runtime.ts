import { getRuntimeSettings, type RuntimeSettings } from '@/api/analytics'

const RUNTIME_CACHE_KEY = 'runtime:settings'
const RUNTIME_CACHE_TIME_KEY = 'runtime:settings:ts'
const CACHE_TTL_MS = 60 * 1000

const defaultSettings: RuntimeSettings = {
  product_mode: 'all_free',
  is_all_free: true,
  billing_visible: false,
  analytics_enabled: true,
}

let pending: Promise<RuntimeSettings> | null = null

const readCache = (): RuntimeSettings | null => {
  try {
    const raw = localStorage.getItem(RUNTIME_CACHE_KEY)
    const ts = Number(localStorage.getItem(RUNTIME_CACHE_TIME_KEY) || '0')
    if (!raw || !ts) return null
    if (Date.now() - ts > CACHE_TTL_MS) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return { ...defaultSettings, ...parsed }
  } catch {
    return null
  }
}

const writeCache = (settings: RuntimeSettings) => {
  try {
    localStorage.setItem(RUNTIME_CACHE_KEY, JSON.stringify(settings))
    localStorage.setItem(RUNTIME_CACHE_TIME_KEY, String(Date.now()))
  } catch {
    // ignored
  }
}

export const clearRuntimeCache = () => {
  localStorage.removeItem(RUNTIME_CACHE_KEY)
  localStorage.removeItem(RUNTIME_CACHE_TIME_KEY)
}

export const loadRuntimeSettings = async (force = false): Promise<RuntimeSettings> => {
  if (!force) {
    const cached = readCache()
    if (cached) return cached
  }

  if (!pending) {
    pending = getRuntimeSettings()
      .then((res) => {
        const data = { ...defaultSettings, ...(res || {}) }
        writeCache(data)
        return data
      })
      .catch(() => {
        const fallback = readCache() || defaultSettings
        return fallback
      })
      .finally(() => {
        pending = null
      })
  }

  return pending
}

export const getDefaultRuntimeSettings = () => defaultSettings
