<template>
  <div class="billing-page">
    <section class="hero">
      <div>
        <h1>套餐订阅中心</h1>
        <p>将套餐选购、订单管理、支付接入拆分为独立子页面，减少信息堆叠。</p>
      </div>
      <a-space>
        <a-button @click="refreshAll" :loading="loading">刷新</a-button>
        <a-button v-if="isAdmin" type="primary" @click="runSweep" :loading="sweeping">扫描到期并降级</a-button>
      </a-space>
    </section>

    <section class="billing-switcher">
      <a-space wrap>
        <a-button
          v-for="tab in billingTabs"
          :key="tab.key"
          size="small"
          :type="tab.key === activeView ? 'primary' : 'outline'"
          @click="setBillingView(tab.key)"
        >
          {{ tab.label }}
        </a-button>
      </a-space>
    </section>

    <a-card class="panel" :loading="loading" title="当前套餐状态">
      <a-space direction="vertical" fill>
        <a-tag :color="planColor">{{ overview.plan?.label || '-' }}</a-tag>
        <div class="line"><span>AI 配额</span><span>{{ overview.plan?.ai_used || 0 }}/{{ overview.plan?.ai_quota || 0 }}</span></div>
        <div class="line"><span>图片配额</span><span>{{ overview.plan?.image_used || 0 }}/{{ overview.plan?.image_quota || 0 }}</span></div>
        <div class="line"><span>到期时间</span><span>{{ overview.plan?.plan_expires_at || '未设置' }}</span></div>
      </a-space>
    </a-card>

    <a-card v-if="activeView === 'plans'" id="billing-plan-anchor" class="panel" title="套餐订阅（点击套餐卡片可直接下单）">
      <div class="plan-grid">
        <div
          v-for="item in overview.catalog || []"
          :key="item.tier"
          class="plan-item"
          :class="{ active: form.plan_tier === item.tier }"
          @click="form.plan_tier = item.tier"
        >
          <div class="name">{{ item.label }}</div>
          <div class="price">{{ item.monthly_price_text }}</div>
          <div class="desc">{{ item.description }}</div>
          <a-tag v-if="form.plan_tier === item.tier" color="arcoblue">已选择</a-tag>
          <a-space wrap>
            <a-tag color="arcoblue">AI {{ item.ai_quota }}/月</a-tag>
            <a-tag color="green">图片 {{ item.image_quota }}/月</a-tag>
          </a-space>
        </div>
      </div>
      <a-space style="margin-top: 14px;" wrap>
        <span class="line-label">订阅时长（月）</span>
        <a-input-number v-model="form.months" :min="1" :max="24" />
        <a-input v-model="form.note" placeholder="订单备注（可选）" style="width: 260px;" />
        <a-button type="primary" :loading="creating" @click="submitOrder">创建订单</a-button>
      </a-space>
      <a-alert v-if="latestPayHint" type="info" style="margin-top: 12px;">{{ latestPayHint }}</a-alert>
    </a-card>

    <a-card v-if="activeView === 'orders'" id="billing-orders-anchor" class="panel" title="我的订单">
      <a-table :columns="columns" :data="orders" :pagination="false" :row-class="orderRowClass">
        <template #orderNoCell="{ record }">
          <a-link @click="focusOrder(record.order_no)">{{ record.order_no }}</a-link>
        </template>
        <template #statusCell="{ record }">
          <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
        </template>
        <template #actionCell="{ record }">
          <a-space>
            <a-button v-if="record.status === 'pending'" size="mini" type="primary" @click="payOrder(record.order_no)">
              确认支付
            </a-button>
            <a-button v-if="record.status === 'pending'" size="mini" status="warning" @click="cancelOrder(record.order_no)">
              取消
            </a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-card v-if="activeView === 'integration'" id="billing-integration-anchor" class="panel" title="支付系统接入预留">
      <a-space direction="vertical" fill>
        <a-alert type="info">
          当前为支付接入预发布阶段，后续接入真实支付时仅需替换支付确认链路。
        </a-alert>
        <div class="integration-row"><span>1. 支付渠道</span><span>预留微信支付 / 支付宝 / Stripe</span></div>
        <div class="integration-row"><span>2. 回调验签</span><span>按订单号验签并写入 `provider_txn_id`</span></div>
        <div class="integration-row"><span>3. 幂等处理</span><span>重复回调不重复生效套餐</span></div>
        <div class="integration-row"><span>4. 对账任务</span><span>定时核对订单状态并自动补偿</span></div>
      </a-space>
    </a-card>

    <a-card v-if="isAdmin && activeView === 'orders'" class="panel" title="管理员订单视图">
      <a-table :columns="adminColumns" :data="adminOrders" :pagination="false">
        <template #adminStatusCell="{ record }">
          <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getBillingOverview,
  createBillingOrder,
  getMyBillingOrders,
  payBillingOrder,
  cancelBillingOrder,
  sweepExpiredSubscriptions,
  getAdminBillingOrders,
} from '@/api/billing'
import { getCurrentUser } from '@/api/auth'

type BillingView = 'plans' | 'orders' | 'integration'

const loading = ref(false)
const route = useRoute()
const router = useRouter()
const creating = ref(false)
const sweeping = ref(false)
const latestPayHint = ref('')
const userRole = ref('')
const orders = ref<any[]>([])
const adminOrders = ref<any[]>([])
const overview = reactive<any>({
  plan: {},
  catalog: [],
  recent_orders: [],
})

const form = reactive({
  plan_tier: 'pro',
  months: 1,
  note: '',
})

const isAdmin = computed(() => userRole.value === 'admin')
const planColor = computed(() => {
  const tier = overview.plan?.tier || 'free'
  if (tier === 'premium') return 'magenta'
  if (tier === 'pro') return 'orangered'
  return 'lime'
})

const columns = [
  { title: '订单号', dataIndex: 'order_no', slotName: 'orderNoCell', width: 220 },
  { title: '套餐', dataIndex: 'plan_tier', width: 120 },
  { title: '时长(月)', dataIndex: 'months', width: 100 },
  { title: '金额', dataIndex: 'amount_cents', width: 110, render: ({ record }: any) => `¥${((record.amount_cents || 0) / 100).toFixed(2)}` },
  { title: '状态', dataIndex: 'status', slotName: 'statusCell', width: 110 },
  { title: '生效至', dataIndex: 'effective_to', width: 220 },
  { title: '创建时间', dataIndex: 'created_at', width: 220 },
  { title: '操作', slotName: 'actionCell', width: 170 },
]

const adminColumns = [
  { title: '用户', dataIndex: 'owner_id', width: 120 },
  { title: '订单号', dataIndex: 'order_no', width: 220 },
  { title: '套餐', dataIndex: 'plan_tier', width: 120 },
  { title: '金额', dataIndex: 'amount_cents', width: 110, render: ({ record }: any) => `¥${((record.amount_cents || 0) / 100).toFixed(2)}` },
  { title: '状态', dataIndex: 'status', slotName: 'adminStatusCell', width: 110 },
  { title: '生效至', dataIndex: 'effective_to', width: 220 },
]

const statusColor = (status: string) => {
  if (status === 'paid') return 'green'
  if (status === 'canceled') return 'red'
  return 'orange'
}

const activeOrderNo = computed(() => {
  const raw = route.query.order_no
  return Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
})
const activeAnchor = computed(() => {
  const raw = route.query.anchor
  return Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
})
const billingTabs: Array<{ key: BillingView; label: string }> = [
  { key: 'plans', label: '套餐订阅' },
  { key: 'orders', label: '我的订单' },
  { key: 'integration', label: '支付接入' },
]
const activeView = computed<BillingView>(() => {
  if (activeAnchor.value === 'orders') return 'orders'
  if (activeAnchor.value === 'integration') return 'integration'
  return 'plans'
})

const setBillingView = (view: BillingView) => {
  const nextQuery: Record<string, any> = { ...route.query }
  nextQuery.anchor = view
  if (JSON.stringify(nextQuery) === JSON.stringify(route.query)) return
  router.push({ path: route.path, query: nextQuery })
}

const focusOrder = (orderNo: string) => {
  const nextQuery = { ...route.query }
  if (orderNo) nextQuery.order_no = orderNo
  else delete nextQuery.order_no
  if (JSON.stringify(nextQuery) === JSON.stringify(route.query)) return
  router.push({ path: route.path, query: nextQuery })
}

const orderRowClass = ({ record }: any) => {
  if (!activeOrderNo.value || !record) return ''
  return String(record.order_no || '') === activeOrderNo.value ? 'active-order-row' : ''
}

const loadRole = async () => {
  const user = await getCurrentUser()
  userRole.value = user?.role || ''
}

const loadOverview = async () => {
  const data = await getBillingOverview()
  overview.plan = data.plan || {}
  overview.catalog = data.catalog || []
  if (overview.catalog.length && !overview.catalog.find((x: any) => x.tier === form.plan_tier)) {
    form.plan_tier = overview.catalog[0].tier
  }
}

const loadOrders = async () => {
  orders.value = await getMyBillingOrders({ limit: 100 })
  scrollToActiveOrder('auto')
}

const loadAdminOrders = async () => {
  if (!isAdmin.value) return
  adminOrders.value = await getAdminBillingOrders({ limit: 200 })
}

const refreshAll = async () => {
  loading.value = true
  try {
    await loadRole()
    await Promise.all([loadOverview(), loadOrders()])
    await loadAdminOrders()
  } finally {
    loading.value = false
  }
}

const scrollToActiveOrder = (behavior: ScrollBehavior = 'smooth') => {
  if (!activeOrderNo.value) return
  nextTick(() => {
    const el = document.querySelector('.active-order-row')
    if (el && 'scrollIntoView' in el) {
      ;(el as HTMLElement).scrollIntoView({ behavior, block: 'center' })
    }
  })
}

const submitOrder = async () => {
  creating.value = true
  try {
    const order = await createBillingOrder({
      plan_tier: form.plan_tier,
      months: form.months,
      channel: 'sandbox',
      note: form.note,
    })
    latestPayHint.value = order?.payment?.message || ''
    Message.success(`订单创建成功：${order.order_no}`)
    focusOrder(order.order_no)
    await refreshAll()
  } catch (e: any) {
    Message.error(String(e || '创建订单失败'))
  } finally {
    creating.value = false
  }
}

const payOrder = async (orderNo: string) => {
  await payBillingOrder(orderNo, { provider_txn_id: `sandbox-${Date.now()}` })
  Message.success('支付成功，套餐已生效')
  focusOrder(orderNo)
  await refreshAll()
}

const cancelOrder = async (orderNo: string) => {
  await cancelBillingOrder(orderNo, { reason: '用户取消' })
  Message.info('订单已取消')
  await refreshAll()
}

const runSweep = async () => {
  sweeping.value = true
  try {
    const res = await sweepExpiredSubscriptions()
    Message.info(`扫描完成：降级 ${res.total} 个账号`)
    await refreshAll()
  } finally {
    sweeping.value = false
  }
}

watch(activeOrderNo, () => {
  scrollToActiveOrder('auto')
})

onMounted(async () => {
  await refreshAll()
})
</script>

<style scoped>
.billing-page {
  padding: 4px;
  color: var(--text-2);
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border-radius: 14px;
  margin-bottom: 14px;
  background: linear-gradient(130deg, #eef5ff 0%, #f8fbff 62%, #f0f9ff 100%);
  border: 1px solid #d9e5fb;
  color: var(--text-1);
}

.hero h1 {
  margin: 0;
  font-size: 24px;
}

.hero p {
  margin: 6px 0 0;
  color: var(--text-3);
}

.billing-switcher {
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid #d9e5fb;
  border-radius: 12px;
  background: #f8fbff;
}

.panel {
  margin-bottom: 14px;
}

.line {
  display: flex;
  justify-content: space-between;
  color: var(--text-2);
}

.line-label {
  color: var(--text-3);
  font-size: 13px;
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.plan-item {
  border: 1px solid #dce6f8;
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  background: #ffffff;
  transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
  display: grid;
  gap: 8px;
}

.plan-item:hover {
  border-color: #8fb4f8;
  transform: translateY(-1px);
}

.plan-item.active {
  border-color: #2563eb;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.14);
}

.name {
  font-size: 16px;
  font-weight: 700;
}

.price {
  margin-top: 4px;
  color: #2563eb;
  font-weight: 700;
}

.desc {
  margin: 6px 0 10px;
  color: var(--text-3);
  font-size: 12px;
}

.integration-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;
  border-bottom: 1px dashed #dce6f8;
  padding-bottom: 8px;
}

.integration-row:last-child {
  border-bottom: 0;
}

@media (max-width: 768px) {
  .billing-page {
    padding: 0;
  }
  .hero {
    flex-direction: column;
    align-items: flex-start;
  }
}

:deep(.active-order-row > td) {
  background: #edf4ff !important;
}
</style>
