<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  listConfigs, 
  createConfig, 
  updateConfig, 
  deleteConfig 
} from '@/api/configManagement'
import type { ConfigManagement } from '@/types/configManagement'
import { getCurrentUser } from '@/api/auth'
import { Message, Modal } from '@arco-design/web-vue'

const columns = [
  { title: '配置键', dataIndex: 'config_key' },
  { title: '配置值', dataIndex: 'config_value', width: '30%', ellipsis: true },
  { title: '描述', dataIndex: 'description' },
  { title: '操作', slotName: 'action', width: 220 }
]

const router = useRouter()
const configList = ref<any>([])
const loading = ref(false)
const error = ref('')
const canEdit = ref(false)
const editingMasked = ref(false)
const keyword = ref('')
const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const visible = ref(false)
const modalTitle = ref('添加配置')
const form = reactive({
  config_key: '',
  config_value: '',
  description: ''
})

const fetchPermission = async () => {
  try {
    const user = await getCurrentUser()
    const permissions = Array.isArray(user?.permissions) ? user.permissions : []
    canEdit.value =
      user?.role === 'admin' ||
      permissions.includes('admin') ||
      permissions.includes('config:edit')
  } catch {
    canEdit.value = false
  }
}

const fetchConfigs = async () => {
  try {
    loading.value = true
    const res= await listConfigs({
      page: pagination.current,
      pageSize: pagination.pageSize,
      keyword: keyword.value
    })
    configList.value = res.list
    pagination.total = res.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '获取配置列表失败'
  } finally {
    loading.value = false
  }
}

const showAddModal = () => {
  modalTitle.value = '添加配置'
  editingMasked.value = false
  Object.keys(form).forEach(key => {
    form[key] = ''
  })
  visible.value = true
}

const editConfig = (record: ConfigManagement) => {
  if (!canEdit.value) return
  modalTitle.value = '编辑配置'
  editingMasked.value = !!record.is_masked
  form.config_key = record.config_key || ''
  form.config_value = record.is_masked ? '' : (record.config_value || '')
  form.description = record.description || ''
  visible.value = true
}

const viewConfig = (key: string) => {
  router.push(`/configs/${encodeURIComponent(key)}`)
}

const handleSubmit = async () => {
  if (!canEdit.value) return
  if (!String(form.config_key || '').trim()) {
    Message.error('配置键不能为空')
    return
  }
  if (modalTitle.value === '编辑配置' && editingMasked.value && !String(form.config_value || '').trim()) {
    Message.error('该配置为敏感项，请输入新值后再保存')
    return
  }
  try {
    if (modalTitle.value === '添加配置') {
      await createConfig(form)
    } else {
      await updateConfig(form.config_key, form)
    }
    Message.success('保存成功')
    visible.value = false
    fetchConfigs()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存配置失败'
  }
}

const deleteConfigItem = async (key: string) => {
  if (!canEdit.value) return
  Modal.confirm({
    title: '确认删除',
    content: '确定要删除此配置吗？',
    okText: '删除',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteConfig(key)
        Message.success('删除成功')
        fetchConfigs()
      } catch (err) {
        error.value = err instanceof Error ? err.message : '删除配置失败'
      }
    }
  })
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchConfigs()
}

const handleSearch = () => {
  pagination.current = 1
  fetchConfigs()
}

const handleResetSearch = () => {
  keyword.value = ''
  pagination.current = 1
  fetchConfigs()
}

onMounted(() => {
  fetchPermission()
  fetchConfigs()
})
</script>

<template>
  <div class="config-management">
    <a-card title="配置" :bordered="false">
      <a-space direction="vertical" fill>
        <a-alert v-if="error" type="error" show-icon>{{ error }}</a-alert>
        <a-alert v-if="!canEdit" type="info" show-icon>当前账号仅支持查看配置，如需修改请授予 `config:edit` 权限或使用管理员账号。</a-alert>
        <a-space>
          <a-button v-if="canEdit" type="primary" @click="showAddModal">添加配置</a-button>
          <a-input
            v-model="keyword"
            :style="{ width: '320px' }"
            allow-clear
            placeholder="搜索配置参数（如 ip，支持部分匹配）"
            @press-enter="handleSearch"
          />
          <a-button type="primary" @click="handleSearch">搜索</a-button>
          <a-button @click="handleResetSearch">重置</a-button>
        </a-space>
        
        <a-table
          :columns="columns"
          :data="configList"
          :loading="loading"
          :pagination="pagination"
          @page-change="handlePageChange"
          row-key="config_key"
        >
          <template #action="{ record }">
            <a-space>
              <a-link @click="viewConfig(record.config_key)">详情</a-link>
              <a-button v-if="canEdit" type="text" size="small" @click="editConfig(record)">编辑</a-button>
              <a-button v-if="canEdit" type="text" status="danger" size="small" @click="deleteConfigItem(record.config_key)">删除</a-button>
            </a-space>
          </template>
        </a-table>
      </a-space>
    </a-card>

    <a-modal
      v-model:visible="visible"
      :title="modalTitle"
      @ok="handleSubmit"
      @cancel="visible = false"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="配置键" field="config_key" required>
          <a-input v-model="form.config_key" :disabled="modalTitle === '编辑配置'" />
        </a-form-item>
        <a-form-item label="配置值" field="config_value" required>
          <a-input v-model="form.config_value" :placeholder="editingMasked ? '该项已脱敏，请输入新值' : ''" />
        </a-form-item>
        <a-form-item label="描述" field="description">
          <a-textarea v-model="form.description" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.config-management {
  padding: 20px;
}
</style>
