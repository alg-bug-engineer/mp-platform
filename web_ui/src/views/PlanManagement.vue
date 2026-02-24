<template>
  <div class="plan-page">
    <a-card title="用户与套餐管理（管理员）">
      <a-space wrap style="margin-bottom: 12px;">
        <a-input-search
          v-model="keyword"
          placeholder="搜索用户名/手机号/昵称"
          style="width: 280px;"
          @search="handleSearch"
        />
        <a-button @click="handleSearch">查询</a-button>
        <a-button type="primary" status="success" @click="goAnalytics">数据统计</a-button>
        <a-button @click="fetchUsers" :loading="loading">刷新</a-button>
      </a-space>
      <a-table
        :columns="columns"
        :data="users"
        :pagination="pagination"
        :loading="loading"
        @page-change="onPageChange"
        @page-size-change="onPageSizeChange"
      >
        <template #statusCell="{ record }">
          <a-tag :color="record.is_active ? 'arcoblue' : 'red'">
            {{ record.is_active ? '启用' : '停用' }}
          </a-tag>
        </template>
        <template #wechatCell="{ record }">
          <a-tag :color="record.wechat_authorized ? 'green' : 'gray'">
            {{ record.wechat_authorized ? '已授权' : '未授权' }}
          </a-tag>
        </template>
        <template #quotaCell="{ record }">
          {{ Number(record.ai_used || 0) }}/{{ Number(record.ai_quota || 0) }}
        </template>
        <template #imageQuotaCell="{ record }">
          {{ Number(record.image_used || 0) }}/{{ Number(record.image_quota || 0) }}
        </template>
        <template #actions="{ record }">
          <a-space>
            <a-button size="mini" @click="openDetail(record)">授权详情</a-button>
            <a-button size="mini" @click="toggleStatus(record)">
              {{ record.is_active ? '停用' : '启用' }}
            </a-button>
            <a-button size="mini" @click="openEdit(record)">调整配额</a-button>
            <a-button size="mini" status="warning" @click="resetUsage(record)">重置消耗</a-button>
            <a-button size="mini" status="danger" @click="confirmDelete(record)">删除用户</a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-modal v-model:visible="editVisible" title="调整用户套餐" :on-before-ok="submitEdit">
      <a-form :model="editForm" layout="vertical">
        <a-form-item label="用户名">
          <a-input v-model="editForm.username" disabled />
        </a-form-item>
        <a-form-item label="套餐档位">
          <a-select v-model="editForm.plan_tier">
            <a-option value="free">免费用户</a-option>
            <a-option value="pro">付费用户</a-option>
            <a-option value="premium">高级用户</a-option>
          </a-select>
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="AI 月配额">
              <a-input-number v-model="editForm.monthly_ai_quota" :min="0" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="图片月配额">
              <a-input-number v-model="editForm.monthly_image_quota" :min="0" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="套餐到期时间（可选）">
          <a-input v-model="editForm.plan_expires_at" placeholder="YYYY-MM-DDTHH:mm:ss 或留空" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer v-model:visible="detailVisible" width="680px" title="用户授权详情" unmount-on-close>
      <a-spin :loading="detailLoading" style="width: 100%;">
        <template v-if="detail">
          <a-descriptions :column="2" bordered>
            <a-descriptions-item label="用户名">{{ detail.user?.username || '-' }}</a-descriptions-item>
            <a-descriptions-item label="角色">{{ detail.user?.role || '-' }}</a-descriptions-item>
            <a-descriptions-item label="状态">
              <a-tag :color="detail.user?.is_active ? 'arcoblue' : 'red'">
                {{ detail.user?.is_active ? '启用' : '停用' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="手机号">{{ detail.user?.phone || '-' }}</a-descriptions-item>
            <a-descriptions-item label="套餐">{{ detail.plan?.label || '-' }}</a-descriptions-item>
            <a-descriptions-item label="配额">
              AI {{ detail.plan?.ai_used || 0 }}/{{ detail.plan?.ai_quota || 0 }}，
              图 {{ detail.plan?.image_used || 0 }}/{{ detail.plan?.image_quota || 0 }}
            </a-descriptions-item>
            <a-descriptions-item label="订阅号">{{ detail.usage?.mp_count || 0 }}</a-descriptions-item>
            <a-descriptions-item label="文章">{{ detail.usage?.article_count || 0 }}</a-descriptions-item>
            <a-descriptions-item label="事件">{{ detail.usage?.event_count || 0 }}</a-descriptions-item>
            <a-descriptions-item label="最近活跃">{{ detail.usage?.last_active || '-' }}</a-descriptions-item>
            <a-descriptions-item label="授权公众号名称">{{ detail.wechat_auth?.wx_app_name || '-' }}</a-descriptions-item>
            <a-descriptions-item label="授权微信号">{{ detail.wechat_auth?.wx_user_name || '-' }}</a-descriptions-item>
          </a-descriptions>

          <a-divider>授权凭据（管理员可见）</a-divider>
          <a-form layout="vertical">
            <a-form-item label="Token">
              <a-textarea :model-value="detail.wechat_auth?.token || ''" :auto-size="{ minRows: 2, maxRows: 3 }" readonly />
            </a-form-item>
            <a-form-item label="Cookie">
              <a-textarea :model-value="detail.wechat_auth?.cookie || ''" :auto-size="{ minRows: 4, maxRows: 10 }" readonly />
            </a-form-item>
          </a-form>

          <a-divider>已授权订阅号列表</a-divider>
          <a-table
            size="small"
            :pagination="{ pageSize: 10 }"
            :columns="detailColumns"
            :data="detail.subscriptions || []"
          />
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { getCurrentUser } from '@/api/auth'
import {
  getUserList,
  updateUserPlan,
  resetUserPlanUsage,
  updateUserInfo,
  deleteUser,
  getUserAdminDetail,
  type UserListItem,
  type UserAdminDetail,
} from '@/api/user'

const loading = ref(false)
const users = ref<UserListItem[]>([])
const keyword = ref('')
const currentUsername = ref('')
const editVisible = ref(false)
const originalTier = ref('free')
const router = useRouter()
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<UserAdminDetail | null>(null)

const PLAN_DEFAULTS: Record<string, { ai: number; image: number }> = {
  free: { ai: 30, image: 5 },
  pro: { ai: 300, image: 80 },
  premium: { ai: 1200, image: 400 },
}

const editForm = reactive({
  username: '',
  plan_tier: 'free',
  monthly_ai_quota: 30,
  monthly_image_quota: 5,
  plan_expires_at: '',
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showPageSize: true,
  pageSizeOptions: ['20', '50', '100', '200'],
})

const columns = [
  { title: '用户名', dataIndex: 'username', width: 180 },
  { title: '角色', dataIndex: 'role', width: 100 },
  { title: '状态', slotName: 'statusCell', width: 90 },
  { title: '手机号', dataIndex: 'phone', width: 140 },
  { title: '公众号授权', slotName: 'wechatCell', width: 110 },
  { title: '套餐', dataIndex: 'plan_label', width: 170 },
  { title: 'AI用量', slotName: 'quotaCell', width: 140 },
  { title: '图片用量', slotName: 'imageQuotaCell', width: 140 },
  { title: '订阅号', dataIndex: 'mp_count', width: 90 },
  { title: '文章', dataIndex: 'article_count', width: 90 },
  { title: '事件', dataIndex: 'event_count', width: 90 },
  { title: '最近活跃', dataIndex: 'last_active', width: 180 },
  { title: '操作', slotName: 'actions', width: 360 },
]

const detailColumns = [
  { title: '公众号名称', dataIndex: 'mp_name' },
  { title: 'fakeid', dataIndex: 'faker_id', width: 160 },
  { title: '状态', dataIndex: 'status', width: 90 },
  { title: '创建时间', dataIndex: 'created_at', width: 180 },
]

const fetchUsers = async () => {
  loading.value = true
  try {
    const data = await getUserList(
      Number(pagination.current || 1),
      Number(pagination.pageSize || 20),
      keyword.value,
    )
    users.value = data.list || []
    pagination.total = Number(data.total || 0)
    pagination.current = Number(data.page || pagination.current || 1)
    pagination.pageSize = Number(data.page_size || pagination.pageSize || 20)
  } finally {
    loading.value = false
  }
}

const onPageChange = async (page: number) => {
  pagination.current = page
  await fetchUsers()
}

const onPageSizeChange = async (size: number) => {
  pagination.pageSize = size
  pagination.current = 1
  await fetchUsers()
}

const handleSearch = async () => {
  pagination.current = 1
  await fetchUsers()
}

const goAnalytics = () => {
  router.push('/workspace/admin/analytics')
}

const openEdit = (record: UserListItem) => {
  editForm.username = record.username || ''
  editForm.plan_tier = record.plan_tier || 'free'
  originalTier.value = editForm.plan_tier
  editForm.monthly_ai_quota = Number(record.ai_quota || 0)
  editForm.monthly_image_quota = Number(record.image_quota || 0)
  editForm.plan_expires_at = ''
  editVisible.value = true
}

const submitEdit = async () => {
  if (!editForm.username) return false
  await updateUserPlan(editForm.username, {
    plan_tier: editForm.plan_tier,
    monthly_ai_quota: editForm.monthly_ai_quota,
    monthly_image_quota: editForm.monthly_image_quota,
    plan_expires_at: editForm.plan_expires_at || null,
  })
  Message.success('套餐已更新')
  await fetchUsers()
  return true
}

const resetUsage = async (record: UserListItem) => {
  if (!record.username) return
  await resetUserPlanUsage(record.username)
  Message.success(`已重置 ${record.username} 的配额消耗`)
  await fetchUsers()
}

const toggleStatus = async (record: UserListItem) => {
  const username = String(record.username || '').trim()
  if (!username) return
  const next = !record.is_active
  await updateUserInfo({
    username,
    is_active: next,
  })
  Message.success(`${username} 已${next ? '启用' : '停用'}`)
  await fetchUsers()
}

const openDetail = async (record: UserListItem) => {
  const username = String(record.username || '').trim()
  if (!username) return
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getUserAdminDetail(username, false)
  } finally {
    detailLoading.value = false
  }
}

const confirmDelete = (record: UserListItem) => {
  const username = String(record.username || '').trim()
  if (!username) return
  if (username === currentUsername.value) {
    Message.warning('不允许删除当前登录管理员账号')
    return
  }
  Modal.confirm({
    title: '删除用户',
    content: `确认删除用户「${username}」以及其关联的订阅、文章、授权与统计数据吗？`,
    onOk: async () => {
      await deleteUser(username)
      Message.success(`已删除用户 ${username}`)
      if (users.value.length === 1 && pagination.current > 1) {
        pagination.current -= 1
      }
      await fetchUsers()
    },
  })
}

onMounted(async () => {
  try {
    const me = await getCurrentUser()
    currentUsername.value = String(me?.username || '').trim()
  } catch {
    currentUsername.value = ''
  }
  await fetchUsers()
})

watch(
  () => editForm.plan_tier,
  (nextTier, prevTier) => {
    if (!editVisible.value) return
    if (!nextTier || nextTier === prevTier) return
    if (nextTier === originalTier.value) return
    const defaults = PLAN_DEFAULTS[nextTier]
    if (!defaults) return
    editForm.monthly_ai_quota = defaults.ai
    editForm.monthly_image_quota = defaults.image
  }
)
</script>

<style scoped>
.plan-page {
  padding: 16px;
}
</style>
