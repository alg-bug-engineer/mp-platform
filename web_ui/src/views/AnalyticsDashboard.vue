<template>
  <div class="analytics-page">
    <section class="hero">
      <div>
        <h1>运营数据分析</h1>
        <p>覆盖访问、使用、输入与接口耗时，支持按窗口周期持续跟踪产品运营效果。</p>
      </div>
      <a-space wrap>
        <a-select v-model="windowDays" style="width: 130px;" @change="refresh">
          <a-option :value="7">近 7 天</a-option>
          <a-option :value="14">近 14 天</a-option>
          <a-option :value="30">近 30 天</a-option>
        </a-select>
        <a-button :loading="loading" @click="refresh">刷新</a-button>
      </a-space>
    </section>

    <a-card class="panel" title="运营模式">
      <a-space wrap>
        <a-radio-group v-model="runtimeMode" type="button">
          <a-radio value="all_free">全站免费开放</a-radio>
          <a-radio value="commercial">商业化套餐模式</a-radio>
        </a-radio-group>
        <a-button type="primary" :loading="savingMode" @click="saveRuntimeMode">保存模式</a-button>
      </a-space>
      <div class="mode-desc">当前模式：{{ summary.runtime?.product_mode || runtimeMode }}</div>
    </a-card>

    <a-row :gutter="12" class="metric-row">
      <a-col :xs="12" :md="6" v-for="item in overviewCards" :key="item.label">
        <a-card class="metric-card" :loading="loading">
          <div class="metric-value">{{ item.value }}</div>
          <div class="metric-label">{{ item.label }}</div>
        </a-card>
      </a-col>
    </a-row>

    <a-card class="panel" title="注册用户与使用情况" :loading="userLoading">
      <a-space wrap style="margin-bottom: 10px;">
        <a-input-search
          v-model="userKeyword"
          placeholder="搜索用户名/手机号/昵称"
          style="width: 280px;"
          @search="searchUsers"
        />
        <a-button @click="searchUsers">查询</a-button>
      </a-space>
      <a-table
        :columns="registeredUserColumns"
        :data="registeredUsers"
        :loading="userLoading"
        :pagination="userPagination"
        size="small"
        @page-change="onUserPageChange"
        @page-size-change="onUserPageSizeChange"
      >
        <template #authCell="{ record }">
          <a-tag :color="record.wechat_authorized ? 'green' : 'gray'">
            {{ record.wechat_authorized ? '已授权' : '未授权' }}
          </a-tag>
        </template>
        <template #activeCell="{ record }">
          <a-tag :color="record.is_active ? 'arcoblue' : 'red'">
            {{ record.is_active ? '启用' : '停用' }}
          </a-tag>
        </template>
      </a-table>
    </a-card>

    <a-row :gutter="12">
      <a-col :xs="24" :md="8">
        <a-card class="panel" title="Top 页面" :loading="loading">
          <a-table :columns="pageColumns" :data="summary.top_pages" :pagination="false" size="small" />
        </a-card>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-card class="panel" title="Top 功能" :loading="loading">
          <a-table :columns="featureColumns" :data="summary.top_features" :pagination="false" size="small" />
        </a-card>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-card class="panel" title="Top 用户" :loading="loading">
          <a-table :columns="topUserColumns" :data="summary.top_users" :pagination="false" size="small" />
        </a-card>
      </a-col>
    </a-row>

    <a-card class="panel" title="趋势数据" :loading="loading">
      <a-table :columns="trendColumns" :data="summary.daily_trend" :pagination="false" size="small" />
    </a-card>

    <a-card class="panel" title="最近事件" :loading="loading">
      <a-table :columns="recentColumns" :data="summary.recent_events" :pagination="{ pageSize: 10 }" size="small" />
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  getAnalyticsUsers,
  getAnalyticsSummary,
  updateRuntimeMode,
  type AnalyticsUserUsage,
  type AnalyticsSummary,
  type ProductMode,
} from '@/api/analytics'
import { clearRuntimeCache } from '@/utils/runtime'

const loading = ref(false)
const savingMode = ref(false)
const windowDays = ref(7)
const runtimeMode = ref<ProductMode>('all_free')
const userLoading = ref(false)
const userKeyword = ref('')
const registeredUsers = ref<AnalyticsUserUsage[]>([])
const userPagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showPageSize: true,
  pageSizeOptions: ['20', '50', '100', '200'],
})

const summary = ref<AnalyticsSummary>({
  window_days: 7,
  overview: {
    total_events: 0,
    page_views: 0,
    api_requests: 0,
    input_events: 0,
    login_events: 0,
    unique_users: 0,
    avg_api_duration_ms: 0,
    p95_api_duration_ms: 0,
    avg_session_seconds: 0,
  },
  top_pages: [],
  top_features: [],
  top_users: [],
  daily_trend: [],
  recent_events: [],
})

const overviewCards = computed(() => {
  const o = summary.value.overview
  return [
    { label: '事件总量', value: o.total_events || 0 },
    { label: '页面访问', value: o.page_views || 0 },
    { label: 'API 调用', value: o.api_requests || 0 },
    { label: '输入行为', value: o.input_events || 0 },
    { label: '活跃用户', value: o.unique_users || 0 },
    { label: '注册用户', value: o.registered_users_total || 0 },
    { label: '已授权用户', value: o.authorized_users_total || 0 },
    { label: '平均会话时长(秒)', value: o.avg_session_seconds || 0 },
    { label: '平均接口耗时(ms)', value: o.avg_api_duration_ms || 0 },
    { label: 'P95 接口耗时(ms)', value: o.p95_api_duration_ms || 0 },
  ]
})

const pageColumns = [
  { title: '页面', dataIndex: 'page' },
  { title: '访问量', dataIndex: 'visits', width: 100 },
]

const featureColumns = [
  { title: '功能', dataIndex: 'feature' },
  { title: '事件量', dataIndex: 'events', width: 100 },
]

const topUserColumns = [
  { title: '用户', dataIndex: 'username' },
  { title: '事件', dataIndex: 'events', width: 90 },
  { title: '访问', dataIndex: 'page_views', width: 90 },
  { title: '调用', dataIndex: 'api_requests', width: 90 },
]

const registeredUserColumns = [
  { title: '用户名', dataIndex: 'username', width: 140 },
  { title: '手机号', dataIndex: 'phone', width: 130 },
  { title: '昵称', dataIndex: 'nickname', width: 120 },
  { title: '角色', dataIndex: 'role', width: 90 },
  { title: '状态', slotName: 'activeCell', width: 90 },
  { title: '套餐', dataIndex: 'plan_label', width: 180 },
  {
    title: 'AI 用量',
    dataIndex: 'ai_used',
    width: 160,
    render: ({ record }: any) => `${record.ai_used || 0}/${record.ai_quota || 0} (${record.ai_usage_rate || 0}%)`,
  },
  {
    title: '图片用量',
    dataIndex: 'image_used',
    width: 170,
    render: ({ record }: any) => `${record.image_used || 0}/${record.image_quota || 0} (${record.image_usage_rate || 0}%)`,
  },
  { title: '公众号授权', slotName: 'authCell', width: 110 },
  { title: '累计事件', dataIndex: 'event_count', width: 100 },
  { title: '最近活跃', dataIndex: 'last_active', width: 180 },
  { title: '创建时间', dataIndex: 'created_at', width: 180 },
]

const trendColumns = [
  { title: '日期', dataIndex: 'date', width: 120 },
  { title: '事件总量', dataIndex: 'events', width: 110 },
  { title: '页面访问', dataIndex: 'page_views', width: 110 },
  { title: 'API 调用', dataIndex: 'api_requests', width: 110 },
  { title: '输入行为', dataIndex: 'inputs', width: 110 },
  { title: '活跃用户', dataIndex: 'users', width: 110 },
]

const recentColumns = [
  { title: '时间', dataIndex: 'created_at', width: 200 },
  { title: '用户', dataIndex: 'username', width: 120 },
  { title: '类型', dataIndex: 'event_type', width: 120 },
  { title: '页面', dataIndex: 'page', width: 180 },
  { title: '功能', dataIndex: 'feature', width: 150 },
  { title: '动作', dataIndex: 'action', width: 130 },
  { title: '路径', dataIndex: 'path' },
  { title: '耗时(ms)', dataIndex: 'duration_ms', width: 100 },
]

const refreshSummary = async () => {
  loading.value = true
  try {
    const data = await getAnalyticsSummary(windowDays.value, 20)
    summary.value = data
    const mode = String(data?.runtime?.product_mode || runtimeMode.value) as ProductMode
    runtimeMode.value = mode
  } finally {
    loading.value = false
  }
}

const fetchRegisteredUsers = async () => {
  userLoading.value = true
  try {
    const data = await getAnalyticsUsers(
      Number(userPagination.value.current || 1),
      Number(userPagination.value.pageSize || 20),
      userKeyword.value,
    )
    registeredUsers.value = data.list || []
    userPagination.value.total = Number(data.total || 0)
    userPagination.value.current = Number(data.page || 1)
    userPagination.value.pageSize = Number(data.page_size || userPagination.value.pageSize || 20)
  } finally {
    userLoading.value = false
  }
}

const refresh = async () => {
  await Promise.all([refreshSummary(), fetchRegisteredUsers()])
}

const searchUsers = async () => {
  userPagination.value.current = 1
  await fetchRegisteredUsers()
}

const onUserPageChange = async (page: number) => {
  userPagination.value.current = page
  await fetchRegisteredUsers()
}

const onUserPageSizeChange = async (size: number) => {
  userPagination.value.pageSize = size
  userPagination.value.current = 1
  await fetchRegisteredUsers()
}

const saveRuntimeMode = async () => {
  savingMode.value = true
  try {
    const data = await updateRuntimeMode(runtimeMode.value)
    runtimeMode.value = String(data.product_mode || runtimeMode.value) as ProductMode
    clearRuntimeCache()
    Message.success('运营模式已更新')
    await refresh()
  } catch (e: any) {
    Message.error(String(e || '模式更新失败'))
  } finally {
    savingMode.value = false
  }
}

onMounted(() => {
  void refresh()
})
</script>

<style scoped>
.analytics-page {
  padding: 8px;
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  padding: 16px 18px;
  border-radius: 12px;
  background: linear-gradient(130deg, #edf7ff 0%, #f8fbff 58%, #eefcf6 100%);
  border: 1px solid #d6e7ff;
}

.hero h1 {
  margin: 0;
  font-size: 24px;
}

.hero p {
  margin: 6px 0 0;
  color: #475569;
}

.mode-desc {
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.panel {
  margin-bottom: 12px;
}

.metric-row {
  margin-bottom: 12px;
}

.metric-card {
  border: 1px solid #e6edf8;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
}

.metric-label {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}
</style>
