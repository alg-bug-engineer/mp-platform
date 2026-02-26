<template>
  <div class="notices-view">
    <a-page-header title="我的消息" subtitle="系统通知与任务结果">
      <template #extra>
        <a-space>
          <a-radio-group v-model="filterStatus" type="button" @change="onFilterChange">
            <a-radio :value="undefined">全部</a-radio>
            <a-radio :value="0">未读</a-radio>
            <a-radio :value="1">已读</a-radio>
          </a-radio-group>
          <a-button @click="handleMarkAllRead" :loading="markingAll">全部已读</a-button>
        </a-space>
      </template>
    </a-page-header>

    <a-card :bordered="false" class="notices-card" :body-style="{ padding: 0 }">
      <a-spin :loading="loading" style="display: block;">
        <template v-if="notices.length === 0">
          <a-empty description="暂无消息" style="padding: 60px 0;" />
        </template>

        <div v-else class="notice-list">
          <div
            v-for="notice in notices"
            :key="notice.id"
            class="notice-row"
            :class="{ 'notice-row--unread': notice.status === 0 }"
            @click="openDetail(notice)"
          >
            <!-- 未读指示条 -->
            <div class="unread-bar" :class="{ visible: notice.status === 0 }" />

            <!-- 左侧类型图标 -->
            <div class="notice-icon" :class="`notice-icon--${notice.notice_type}`">
              {{ noticeTypeIcon(notice.notice_type) }}
            </div>

            <!-- 中间内容区 -->
            <div class="notice-body">
              <div class="notice-title">{{ notice.title }}</div>
              <div class="notice-preview">{{ previewContent(notice.content) }}</div>
            </div>

            <!-- 右侧元信息 -->
            <div class="notice-meta">
              <a-tag :color="noticeTypeColor(notice.notice_type)" size="small">
                {{ noticeTypeLabel(notice.notice_type) }}
              </a-tag>
              <span class="notice-time">{{ formatTime(notice.created_at) }}</span>
              <a-popconfirm
                content="确认删除此条消息？"
                @ok.stop="handleDelete(notice)"
                @click.stop
              >
                <a-button size="mini" type="text" status="danger" @click.stop>删除</a-button>
              </a-popconfirm>
            </div>
          </div>
        </div>

        <div class="pagination-bar" v-if="total > pageSize">
          <a-pagination
            :current="page"
            :total="total"
            :page-size="pageSize"
            @change="handlePageChange"
            show-total
          />
        </div>
      </a-spin>
    </a-card>

    <!-- 详情弹窗 -->
    <a-modal
      v-model:visible="detailVisible"
      :title="detailNotice?.title"
      :footer="false"
      width="600px"
      @cancel="detailVisible = false"
    >
      <template v-if="detailNotice">
        <div class="detail-meta">
          <a-tag :color="noticeTypeColor(detailNotice.notice_type)" size="small">
            {{ noticeTypeLabel(detailNotice.notice_type) }}
          </a-tag>
          <span class="notice-time">{{ formatTime(detailNotice.created_at) }}</span>
        </div>
        <div class="detail-content">{{ detailNotice.content }}</div>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { listNotices, markRead, markAllRead, deleteNotice, type UserNotice } from '@/api/notice'

const loading = ref(false)
const markingAll = ref(false)
const notices = ref<UserNotice[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterStatus = ref<number | undefined>(undefined)

const detailVisible = ref(false)
const detailNotice = ref<UserNotice | null>(null)

const noticeTypeLabel = (type: string) => {
  const map: Record<string, string> = { task: '任务', compose: '创作', analytics: '分析', imitation: '仿写' }
  return map[type] || type || '通知'
}

const noticeTypeIcon = (type: string) => {
  const map: Record<string, string> = { task: '⚙', compose: '✍', analytics: '📊', imitation: '🔁' }
  return map[type] || '🔔'
}

const noticeTypeColor = (type: string) => {
  const map: Record<string, string> = { task: 'blue', compose: 'green', analytics: 'orange', imitation: 'purple' }
  return map[type] || 'gray'
}

const formatTime = (timeStr?: string | null) => {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  if (isNaN(d.getTime())) return timeStr
  const date = d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  return `${date} ${time}`
}

const previewContent = (content: string) => {
  if (!content) return ''
  const text = content.replace(/\n+/g, ' ').trim()
  return text.length > 80 ? text.slice(0, 80) + '…' : text
}

const fetchNotices = async () => {
  loading.value = true
  try {
    const res = await listNotices({ page: page.value, page_size: pageSize.value, status: filterStatus.value })
    notices.value = res.list || []
    total.value = res.total || 0
  } catch {
    Message.error('获取消息失败')
  } finally {
    loading.value = false
  }
}

const openDetail = async (notice: UserNotice) => {
  detailNotice.value = notice
  detailVisible.value = true
  if (notice.status === 0) {
    try {
      await markRead(notice.id)
      notice.status = 1
    } catch {
      // ignore
    }
  }
}

const handleMarkAllRead = async () => {
  markingAll.value = true
  try {
    await markAllRead()
    notices.value.forEach(n => { n.status = 1 })
    Message.success('已全部标记已读')
  } catch {
    Message.error('操作失败')
  } finally {
    markingAll.value = false
  }
}

const handleDelete = async (notice: UserNotice) => {
  try {
    await deleteNotice(notice.id)
    notices.value = notices.value.filter(n => n.id !== notice.id)
    total.value = Math.max(0, total.value - 1)
    if (detailNotice.value?.id === notice.id) detailVisible.value = false
    Message.success('已删除')
  } catch {
    Message.error('删除失败')
  }
}

const onFilterChange = () => {
  page.value = 1
  fetchNotices()
}

const handlePageChange = (newPage: number) => {
  page.value = newPage
  fetchNotices()
}

onMounted(() => {
  fetchNotices()
})
</script>

<style scoped>
.notices-view {
  padding: 20px;
}

.notices-card {
  border-radius: 12px;
  overflow: hidden;
}

/* ── 列表容器 ── */
.notice-list {
  display: flex;
  flex-direction: column;
}

/* ── 每行 ── */
.notice-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px 14px 20px;
  min-height: 72px;      /* 最小高度，内容撑开时自动扩展 */
  box-sizing: border-box;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.15s ease;
}

.notice-row:last-child {
  border-bottom: none;
}

.notice-row:hover {
  background: #f7f9ff;
}

.notice-row--unread {
  background: #f0f5ff;
}

.notice-row--unread:hover {
  background: #e8f0ff;
}

/* 左侧未读色条 */
.unread-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: transparent;
  border-radius: 0 2px 2px 0;
  transition: background 0.2s;
}

.unread-bar.visible {
  background: #2563eb;
}

/* 类型图标 */
.notice-icon {
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  background: #f0f4ff;
}

.notice-icon--task    { background: #e8f0fe; }
.notice-icon--compose { background: #e6f9f0; }
.notice-icon--analytics { background: #fff4e6; }
.notice-icon--imitation { background: #f3e8ff; }

/* 中间内容 */
.notice-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.notice-title {
  font-size: 13px;
  font-weight: 600;
  color: #1d2d48;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.notice-preview {
  font-size: 12px;
  color: #8a8a8a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 右侧元信息：固定宽度防止被挤压 */
.notice-meta {
  flex: 0 0 100px;
  width: 100px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}

.notice-time {
  font-size: 11px;
  color: #b0b0b0;
  white-space: nowrap;
}

/* 分页 */
.pagination-bar {
  display: flex;
  justify-content: center;
  padding: 20px 0 4px;
}

/* ── 弹窗详情 ── */
.detail-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.detail-content {
  font-size: 14px;
  color: #333;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 60vh;
  overflow-y: auto;
  padding: 16px;
  background: #f7f8fa;
  border-radius: 8px;
}
</style>
