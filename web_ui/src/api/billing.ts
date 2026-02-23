import http from './http'

export interface BillingCatalogItem {
  tier: string
  label: string
  description: string
  monthly_price_cents: number
  monthly_price_text: string
  ai_quota: number
  image_quota: number
  highlights: string[]
}

export interface BillingOrder {
  order_no: string
  plan_tier: string
  months: number
  amount_cents: number
  currency: string
  channel: string
  status: string
  created_at?: string
  paid_at?: string | null
  effective_from?: string | null
  effective_to?: string | null
  payment?: {
    type: string
    message: string
    mock_token?: string
  }
}

export const getBillingCatalog = () => {
  return http.get<BillingCatalogItem[]>('/wx/billing/catalog')
}

export const getBillingOverview = () => {
  return http.get<{
    plan: Record<string, any>
    catalog: BillingCatalogItem[]
    recent_orders: BillingOrder[]
  }>('/wx/billing/overview')
}

export const createBillingOrder = (data: {
  plan_tier: string
  months: number
  channel?: string
  note?: string
}) => {
  return http.post<BillingOrder>('/wx/billing/orders', data)
}

export const getMyBillingOrders = (params?: { status?: string; limit?: number }) => {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  query.set('limit', String(params?.limit || 50))
  return http.get<BillingOrder[]>(`/wx/billing/orders?${query.toString()}`)
}

export const payBillingOrder = (orderNo: string, data?: { provider_txn_id?: string; provider_payload?: string }) => {
  return http.post<BillingOrder>(`/wx/billing/orders/${orderNo}/pay`, data || {})
}

export const cancelBillingOrder = (orderNo: string, data?: { reason?: string }) => {
  return http.post<BillingOrder>(`/wx/billing/orders/${orderNo}/cancel`, data || {})
}

export const sweepExpiredSubscriptions = () => {
  return http.post<{ total: number; users: string[] }>('/wx/billing/subscriptions/sweep')
}

export const getAdminBillingOrders = (params?: { status?: string; limit?: number }) => {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  query.set('limit', String(params?.limit || 200))
  return http.get<BillingOrder[]>(`/wx/billing/orders/admin?${query.toString()}`)
}
