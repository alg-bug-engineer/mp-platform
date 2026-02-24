<template>
  <div class="subscription-page">
    <a-page-header
      title="订阅管理"
      subtitle="管理已添加账号、推荐账号与手动添加"
      :show-back="true"
      @back="goBack"
    />

    <a-row :gutter="16">
      <a-col :xs="24" :lg="14">
        <a-card title="已添加账号" class="panel-card">
          <template #extra>
            <a-space>
              <a-input-search
                v-model="existingKeyword"
                placeholder="搜索已添加公众号"
                style="width: 220px"
                allow-clear
                @search="loadSubscriptions"
              />
              <a-button @click="loadSubscriptions" :loading="loadingSubscriptions">刷新</a-button>
            </a-space>
          </template>

          <a-table
            :columns="subscriptionColumns"
            :data="subscriptionList"
            :loading="loadingSubscriptions"
            :pagination="pagination"
            @page-change="handlePageChange"
          >
            <template #mpCell="{ record }">
              <a-space>
                <a-avatar :size="28">
                  <img :src="Avatar(record.mp_cover || record.avatar || '')" />
                </a-avatar>
                <span>{{ record.mp_name || '-' }}</span>
              </a-space>
            </template>

            <template #actions="{ record }">
              <a-space>
                <a-button type="text" size="mini" @click="copyId(record.id)">复制ID</a-button>
                <a-button type="text" size="mini" status="danger" @click="removeSubscription(record)">删除</a-button>
              </a-space>
            </template>
          </a-table>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="10">
        <a-card title="推荐账号" class="panel-card">
          <a-space wrap>
            <a-tag
              v-for="item in recommendedAccounts"
              :key="item.name"
              color="arcoblue"
              style="cursor: pointer"
              @click="searchAndPick(item.name)"
            >
              {{ item.name }}
            </a-tag>
          </a-space>
          <div class="tip-text">点击推荐账号会自动触发搜索并填充候选。</div>
        </a-card>

        <a-card title="添加账号" class="panel-card">
          <a-form :model="form" layout="vertical" ref="formRef">
            <a-form-item label="通过文章链接识别公众号">
              <a-space>
                <a-input
                  v-model="articleLink"
                  placeholder="粘贴公众号文章链接（mp.weixin.qq.com/s/...）"
                  allow-clear
                  style="width: 280px"
                />
                <a-button :loading="extracting" @click="extractFromArticle">识别</a-button>
              </a-space>
            </a-form-item>

            <a-form-item label="搜索公众号候选">
              <a-input-search
                v-model="searchKeyword"
                placeholder="输入公众号名称检索"
                allow-clear
                :loading="searching"
                @search="searchCandidates"
              />
            </a-form-item>

            <div v-if="searchResults.length" class="candidate-list">
              <div class="candidate-row" v-for="item in searchResults" :key="item.fakeid">
                <a-space>
                  <a-avatar :size="28">
                    <img :src="Avatar(item.round_head_img || '')" />
                  </a-avatar>
                  <span>{{ item.nickname }}</span>
                </a-space>
                <a-button size="mini" @click="useCandidate(item)">使用</a-button>
              </div>
            </div>

            <a-form-item label="公众号名称" required>
              <a-input v-model="form.name" placeholder="请输入公众号名称" allow-clear />
            </a-form-item>

            <a-form-item label="公众号ID" required>
              <a-input v-model="form.wx_id" placeholder="请输入公众号ID" allow-clear />
            </a-form-item>

            <a-form-item label="头像地址" required>
              <a-input v-model="form.avatar" placeholder="请输入头像URL" allow-clear />
              <div class="avatar-preview" v-if="form.avatar">
                <a-avatar :size="48">
                  <img :src="Avatar(form.avatar)" />
                </a-avatar>
              </div>
            </a-form-item>

            <a-form-item label="简介">
              <a-textarea v-model="form.description" :auto-size="{ minRows: 2, maxRows: 4 }" allow-clear />
            </a-form-item>

            <a-space>
              <a-button type="primary" :loading="submitting" @click="submitForm">添加订阅</a-button>
              <a-button @click="resetForm">重置</a-button>
            </a-space>
          </a-form>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { Avatar } from '@/utils/constants'
import { getWechatAuthStatus } from '@/api/auth'
import {
  addSubscription,
  deleteMpApi,
  getSubscriptionInfo,
  getSubscriptions,
  searchBiz,
} from '@/api/subscription'

const router = useRouter()

const loadingSubscriptions = ref(false)
const submitting = ref(false)
const searching = ref(false)
const extracting = ref(false)

const existingKeyword = ref('')
const searchKeyword = ref('')
const articleLink = ref('')

const subscriptionList = ref<any[]>([])
const searchResults = ref<any[]>([])

const pagination = reactive({
  current: 1,
  pageSize: 8,
  total: 0,
})

const formRef = ref()
const form = reactive({
  name: '',
  wx_id: '',
  avatar: '',
  description: '',
})

const recommendedAccounts = [
  { name: '新智元' },
  { name: '机器之心' },
  { name: '量子位' },
  { name: '极客公园' },
  { name: '人人都是产品经理' },
]

const subscriptionColumns = [
  { title: '公众号', slotName: 'mpCell', width: 220 },
  { title: '描述', dataIndex: 'mp_intro', ellipsis: true },
  { title: '创建时间', dataIndex: 'created_at', width: 190 },
  { title: '操作', slotName: 'actions', width: 150 },
]

const loadSubscriptions = async () => {
  try {
    loadingSubscriptions.value = true
    const data = await getSubscriptions({
      page: pagination.current - 1,
      pageSize: pagination.pageSize,
      kw: existingKeyword.value.trim(),
    } as any)
    subscriptionList.value = data.list || []
    pagination.total = data.total || 0
  } finally {
    loadingSubscriptions.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.current = page
  loadSubscriptions()
}

const searchCandidates = async () => {
  const kw = searchKeyword.value.trim()
  if (!kw) {
    searchResults.value = []
    return
  }
  searching.value = true
  try {
    const data = await searchBiz(kw, { page: 0, pageSize: 10 })
    searchResults.value = data.list || []
  } catch (e: any) {
    Message.warning(String(e || '公众号检索失败，请先扫码授权后重试'))
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

const useCandidate = (item: any) => {
  form.name = item.nickname || ''
  form.wx_id = item.fakeid || ''
  form.avatar = item.round_head_img || ''
  form.description = item.signature || ''
}

const searchAndPick = async (name: string) => {
  searchKeyword.value = name
  await searchCandidates()
  if (searchResults.value.length) {
    useCandidate(searchResults.value[0])
  }
}

const extractFromArticle = async () => {
  const url = articleLink.value.trim()
  if (!url) {
    Message.warning('请先输入公众号文章链接')
    return
  }
  extracting.value = true
  try {
    const data = await getSubscriptionInfo(url)
    const info = data?.mp_info
    if (!info) {
      Message.warning('未识别到公众号信息，请确认链接有效')
      return
    }
    form.name = info.mp_name || ''
    form.wx_id = info.biz || ''
    form.avatar = info.logo || ''
    form.description = info.mp_name || ''
    Message.success('已提取公众号信息')
  } catch (e: any) {
    Message.error(String(e || '识别失败，请检查文章链接'))
  } finally {
    extracting.value = false
  }
}

const validateForm = () => {
  if (!form.name.trim()) {
    Message.warning('请输入公众号名称')
    return false
  }
  if (!form.wx_id.trim()) {
    Message.warning('请输入公众号ID')
    return false
  }
  if (!form.avatar.trim()) {
    Message.warning('请输入头像地址')
    return false
  }
  return true
}

const submitForm = async () => {
  if (!validateForm()) return
  submitting.value = true
  try {
    const data: any = await addSubscription({
      mp_name: form.name.trim(),
      mp_id: form.wx_id.trim(),
      avatar: form.avatar.trim(),
      mp_intro: form.description.trim(),
    })
    Message.success('订阅添加成功')
    if (data?.fetch_scheduled === false) {
      Message.warning('订阅已添加，但首次抓取未启动，请先确认当前账号公众号授权状态')
    }
    resetForm()
    await loadSubscriptions()
  } catch (e: any) {
    Message.error(String(e || '订阅添加失败'))
  } finally {
    submitting.value = false
  }
}

const resetForm = () => {
  form.name = ''
  form.wx_id = ''
  form.avatar = ''
  form.description = ''
  searchKeyword.value = ''
  articleLink.value = ''
  searchResults.value = []
}

const copyId = async (id: string) => {
  try {
    await navigator.clipboard.writeText(id)
    Message.success('ID 已复制')
  } catch (e) {
    Message.warning('复制失败，请手动复制')
  }
}

const removeSubscription = (record: any) => {
  Modal.confirm({
    title: '删除订阅',
    content: `确认删除「${record.mp_name}」及其关联文章吗？`,
    onOk: async () => {
      await deleteMpApi(record.id)
      Message.success('删除成功')
      await loadSubscriptions()
    },
  })
}

const goBack = () => {
  router.go(-1)
}

onMounted(loadSubscriptions)
onMounted(async () => {
  try {
    const auth = await getWechatAuthStatus(true)
    if (!auth?.authorized) {
      Message.warning('当前账号公众号授权已失效，请先重新扫码授权后再检索公众号')
    }
  } catch {
    // ignored
  }
})
</script>

<style scoped>
.subscription-page {
  padding: 20px;
}

.panel-card {
  margin-bottom: 16px;
}

.tip-text {
  margin-top: 10px;
  color: var(--color-text-3);
  font-size: 12px;
}

.candidate-list {
  margin-bottom: 12px;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  max-height: 240px;
  overflow: auto;
}

.candidate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border-2);
}

.candidate-row:last-child {
  border-bottom: 0;
}

.avatar-preview {
  margin-top: 8px;
}
</style>
