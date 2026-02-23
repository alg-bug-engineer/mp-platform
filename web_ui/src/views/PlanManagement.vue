<template>
  <div class="plan-page">
    <a-card title="套餐管理（管理员）">
      <a-space style="margin-bottom: 12px;">
        <a-button @click="fetchUsers" :loading="loading">刷新</a-button>
      </a-space>
      <a-table :columns="columns" :data="users" :pagination="false" :loading="loading">
        <template #actions="{ record }">
          <a-space>
            <a-button size="mini" @click="openEdit(record)">调整套餐</a-button>
            <a-button size="mini" status="warning" @click="resetUsage(record)">重置消耗</a-button>
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getUserList, updateUserPlan, resetUserPlanUsage, type UserListItem } from '@/api/user'

const loading = ref(false)
const users = ref<UserListItem[]>([])
const editVisible = ref(false)
const originalTier = ref('free')

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

const columns = [
  { title: '用户名', dataIndex: 'username', width: 180 },
  { title: '角色', dataIndex: 'role', width: 100 },
  { title: '手机号', dataIndex: 'phone', width: 140 },
  { title: '套餐', dataIndex: 'plan_label', width: 170 },
  { title: 'AI配额', dataIndex: 'ai_quota', width: 120 },
  { title: '图片配额', dataIndex: 'image_quota', width: 120 },
  { title: '操作', slotName: 'actions', width: 180 },
]

const fetchUsers = async () => {
  loading.value = true
  try {
    const data = await getUserList(1, 200)
    users.value = data.list || []
  } finally {
    loading.value = false
  }
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

onMounted(fetchUsers)

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
