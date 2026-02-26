<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { listMessageTasks, deleteMessageTask, FreshJobApi, RunMessageTask, listMessageTaskLogs } from '@/api/messageTask'
import type { MessageTask } from '@/types/messageTask'
import type { MessageTaskExecutionLog } from '@/api/messageTask'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import {
  getNotificationEnabled,
  enableBrowserNotification,
  disableBrowserNotification,
  initBrowserNotification
} from '@/utils/browserNotification'

const router = useRouter()
const loading = ref(false)
const taskList = ref<MessageTask[]>([])
const logsVisible = ref(false)
const logsLoading = ref(false)
const logsTaskName = ref('')
const logsTaskId = ref('')
const logs = ref<MessageTaskExecutionLog[]>([])
const freshJobLoading = ref(false)
const browserNotificationEnabled = ref(false)

const crawlTasks = computed(() => taskList.value.filter(t => (t.task_type || 'crawl') !== 'publish'))
const publishTasks = computed(() => taskList.value.filter(t => t.task_type === 'publish'))

const parseCronExpression = (exp: string) => {
  if (!exp) return ''
  const parts = exp.split(' ')
  if (parts.length !== 5) return exp
  const [minute, hour, day, month, week] = parts
  let result = ''
  if (minute === '*') result += '每分钟'
  else if (minute.includes('/')) result += `每${minute.split('/')[1]}分钟`
  else result += `在${minute}分`
  if (hour === '*') result += '每小时'
  else if (hour.includes('/')) result += `每${hour.split('/')[1]}小时`
  else result += ` ${hour}时`
  if (day === '*') result += ' 每天'
  else if (day.includes('/')) result += ` 每${day.split('/')[1]}天`
  else result += ` ${day}日`
  if (month === '*') result += ' 每月'
  else if (month.includes('/')) result += ` 每${month.split('/')[1]}个月`
  else result += ` ${month}月`
  if (week !== '*') result += ` 星期${week}`
  return result || exp
}

const getMpsNames = (task: MessageTask): string[] => {
  try {
    const arr = JSON.parse(String(task.mps_id || '[]'))
    if (!Array.isArray(arr)) return []
    return arr.map((m: any) => String(m.name || m.mp_name || m.id || '')).filter(Boolean)
  } catch {
    return []
  }
}

const getPlatformNames = (task: MessageTask): string[] => {
  try {
    const raw = task.publish_platforms
    const arr = typeof raw === 'string' ? JSON.parse(raw) : (Array.isArray(raw) ? raw : [])
    if (!Array.isArray(arr)) return []
    return arr.map((p: string) => p === 'wechat_mp' ? '微信公众号' : p === 'csdn' ? 'CSDN' : p)
  } catch {
    return []
  }
}

const fetchTaskList = async () => {
  loading.value = true
  try {
    const res = await listMessageTasks({ offset: 0, limit: 100 })
    taskList.value = res.list
  } finally {
    loading.value = false
  }
}

const FreshJob = async () => {
  freshJobLoading.value = true
  try {
    const data = await FreshJobApi()
    Message.success(data?.message || '刷新任务成功')
  } catch (error: any) {
    Message.error(String(error || '刷新任务失败'))
  } finally {
    freshJobLoading.value = false
  }
}

const toggleNotification = async () => {
  if (browserNotificationEnabled.value) {
    disableBrowserNotification()
    browserNotificationEnabled.value = false
    Message.success('浏览器通知已关闭')
  } else {
    const success = await enableBrowserNotification()
    if (success) {
      browserNotificationEnabled.value = true
      Message.success('浏览器通知已开启，将每分钟检查新文章')
    } else {
      Message.error('开启浏览器通知失败')
    }
  }
}

const handleDelete = async (id: string) => {
  Modal.confirm({
    title: '确认删除',
    content: '确定要删除这条任务吗？删除后无法恢复',
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteMessageTask(id)
        Message.success('删除成功')
        fetchTaskList()
      } catch {
        Message.error('删除失败')
      }
    }
  })
}

const runTask = async (id: string) => {
  Modal.confirm({
    title: '确认执行',
    content: '确定要立即执行这条任务吗？',
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        const res = await RunMessageTask(id, false)
        Message.success(res?.message || '执行成功')
      } catch {
        Message.error('执行失败')
      }
    }
  })
}

const showTaskLogs = async (record: MessageTask) => {
  logsTaskId.value = String(record?.id || '')
  logsTaskName.value = String(record?.name || '')
  logsVisible.value = true
  logsLoading.value = true
  try {
    const resp = await listMessageTaskLogs(logsTaskId.value, { limit: 100, offset: 0 })
    logs.value = resp.list || []
  } catch {
    Message.error('加载执行日志失败')
  } finally {
    logsLoading.value = false
  }
}

onMounted(() => {
  fetchTaskList()
  browserNotificationEnabled.value = getNotificationEnabled()
  initBrowserNotification()
})
</script>

<template>
  <div class="task-manager">
    <!-- 顶部操作栏 -->
    <div class="header">
      <h2>任务管理</h2>
      <div class="header-actions">
        <a-tooltip :content="browserNotificationEnabled ? '点击关闭浏览器通知' : '开启后有新文章时浏览器标题会闪烁并播放提示音'" class="desktop-only">
          <a-button
            class="desktop-only"
            :type="browserNotificationEnabled ? 'primary' : 'outline'"
            :status="browserNotificationEnabled ? 'success' : 'normal'"
            @click="toggleNotification"
          >
            <template #icon><icon-notification /></template>
            {{ browserNotificationEnabled ? '通知已开启' : '开启浏览器通知' }}
          </a-button>
        </a-tooltip>
        <a-tooltip content="点击应用按钮后任务才会生效">
          <a-button :loading="freshJobLoading" @click="FreshJob">应用</a-button>
        </a-tooltip>
        <a-dropdown trigger="click">
          <a-button type="primary">
            新建任务
            <template #icon><icon-down /></template>
          </a-button>
          <template #content>
            <a-doption @click="router.push('/message-tasks/add?type=crawl')">
              <template #icon><icon-sync /></template>
              新建抓取任务
            </a-doption>
            <a-doption @click="router.push('/message-tasks/add?type=publish')">
              <template #icon><icon-send /></template>
              新建发布任务
            </a-doption>
          </template>
        </a-dropdown>
      </div>
    </div>

    <a-alert type="info" closable style="margin-bottom: 16px">
      抓取任务定时拉取公众号文章；发布任务独立触发 AI 创作或 CSDN 推送，不执行抓取。点击「应用」后任务才会生效。
    </a-alert>

    <!-- 双栏主体 -->
    <a-spin :loading="loading" style="width: 100%; display: block;">
      <div class="two-panel">
        <!-- 左侧：抓取任务 -->
        <div class="panel panel-crawl">
          <div class="panel-header">
            <icon-sync class="panel-icon crawl-icon" />
            <span class="panel-title">抓取任务</span>
            <a-tag color="blue" size="small" style="margin-left: 6px">{{ crawlTasks.length }}</a-tag>
            <a-button
              type="text"
              size="mini"
              style="margin-left: auto"
              @click="router.push('/message-tasks/add?type=crawl')"
            >
              <template #icon><icon-plus /></template>
              新建
            </a-button>
          </div>

          <div v-if="crawlTasks.length === 0" class="panel-empty">
            <a-empty description="暂无抓取任务" />
          </div>

          <div class="task-list">
            <div
              v-for="task in crawlTasks"
              :key="task.id"
              class="task-item crawl-item"
            >
              <div class="item-top">
                <span class="item-name">{{ task.name }}</span>
                <div class="item-badges">
                  <a-tag color="arcoblue" size="small">抓取</a-tag>
                  <a-tag :color="task.status === 1 ? 'green' : 'red'" size="small">
                    {{ task.status === 1 ? '启用' : '禁用' }}
                  </a-tag>
                </div>
              </div>
              <div class="item-meta">
                <span v-if="task.cron_exp">{{ parseCronExpression(task.cron_exp) }}</span>
                <template v-if="getMpsNames(task).length">
                  <span class="meta-sep">·</span>
                  <span>公众号：</span>
                  <a-tag
                    v-for="n in getMpsNames(task)"
                    :key="n"
                    size="small"
                    color="arcoblue"
                    class="meta-tag"
                  >{{ n }}</a-tag>
                </template>
              </div>
              <div class="item-actions">
                <a-button size="mini" type="dashed" @click="runTask(task.id)">执行</a-button>
                <a-button size="mini" type="primary" @click="router.push(`/message-tasks/edit/${task.id}`)">编辑</a-button>
                <a-button size="mini" @click="showTaskLogs(task)">日志</a-button>
                <a-button size="mini" status="danger" @click="handleDelete(task.id)">删除</a-button>
              </div>
            </div>
          </div>
        </div>

        <!-- 中间分割线 -->
        <div class="panel-divider" />

        <!-- 右侧：发布任务 -->
        <div class="panel panel-publish">
          <div class="panel-header">
            <icon-send class="panel-icon publish-icon" />
            <span class="panel-title">发布任务</span>
            <a-tag color="purple" size="small" style="margin-left: 6px">{{ publishTasks.length }}</a-tag>
            <a-button
              type="text"
              size="mini"
              style="margin-left: auto"
              @click="router.push('/message-tasks/add?type=publish')"
            >
              <template #icon><icon-plus /></template>
              新建
            </a-button>
          </div>

          <div v-if="publishTasks.length === 0" class="panel-empty">
            <a-empty description="暂无发布任务" />
          </div>

          <div class="task-list">
            <div
              v-for="task in publishTasks"
              :key="task.id"
              class="task-item publish-item"
            >
              <div class="item-top">
                <span class="item-name">{{ task.name }}</span>
                <div class="item-badges">
                  <a-tag color="purple" size="small">发布</a-tag>
                  <a-tag :color="task.status === 1 ? 'green' : 'red'" size="small">
                    {{ task.status === 1 ? '启用' : '禁用' }}
                  </a-tag>
                </div>
              </div>
              <div class="item-meta">
                <span v-if="task.cron_exp">{{ parseCronExpression(task.cron_exp) }}</span>
                <template v-if="getMpsNames(task).length">
                  <span class="meta-sep">·</span>
                  <span>公众号：</span>
                  <a-tag
                    v-for="n in getMpsNames(task)"
                    :key="n"
                    size="small"
                    color="arcoblue"
                    class="meta-tag"
                  >{{ n }}</a-tag>
                </template>
              </div>
              <div v-if="getPlatformNames(task).length" class="item-platforms">
                <span class="platform-label">平台：</span>
                <a-tag
                  v-for="p in getPlatformNames(task)"
                  :key="p"
                  size="small"
                  color="purple"
                  class="meta-tag"
                >{{ p }}</a-tag>
              </div>
              <div class="item-actions">
                <a-button size="mini" type="dashed" @click="runTask(task.id)">执行</a-button>
                <a-button size="mini" type="primary" @click="router.push(`/message-tasks/edit/${task.id}`)">编辑</a-button>
                <a-button size="mini" @click="showTaskLogs(task)">日志</a-button>
                <a-button size="mini" status="danger" @click="handleDelete(task.id)">删除</a-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </a-spin>

    <!-- 日志弹窗 -->
    <a-modal
      v-model:visible="logsVisible"
      :title="`执行日志 - ${logsTaskName || logsTaskId}`"
      width="920px"
      :footer="false"
    >
      <a-spin :loading="logsLoading">
        <a-table :data="logs" :pagination="false" :scroll="{ y: 420 }">
          <a-table-column title="时间" data-index="created_at" :width="200" />
          <a-table-column title="公众号ID" data-index="mps_id" :width="180" />
          <a-table-column title="更新数" data-index="update_count" :width="90" />
          <a-table-column title="状态" :width="90">
            <template #cell="{ record }">
              <a-tag :color="Number(record.status || 0) === 1 ? 'green' : 'red'">
                {{ Number(record.status || 0) === 1 ? '成功' : '失败' }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="日志详情">
            <template #cell="{ record }">
              <pre class="task-log-pre">{{ record.log }}</pre>
            </template>
          </a-table-column>
        </a-table>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.task-manager {
  padding: 24px 32px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.header h2 {
  margin: 0;
  font-size: 20px;
  color: var(--color-text-1);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── 双栏容器：用 Grid 严格均分，杜绝内容撑开问题 ── */
.two-panel {
  display: grid;
  grid-template-columns: 1fr 24px 1fr;
  align-items: start;
  min-height: 300px;
  width: 100%;
}

/* 左侧抓取区 */
.panel-crawl {
  min-width: 0;
  box-sizing: border-box;
  padding: 0 24px 24px;
  background: linear-gradient(180deg, rgba(var(--arcoblue-1), 0.5) 0%, transparent 100px);
  border-radius: 10px;
  border: 1px solid rgba(var(--arcoblue-3), 0.5);
  display: flex;
  flex-direction: column;
}

/* 右侧发布区 */
.panel-publish {
  min-width: 0;
  box-sizing: border-box;
  padding: 0 24px 24px;
  background: linear-gradient(180deg, rgba(var(--purple-1), 0.5) 0%, transparent 100px);
  border-radius: 10px;
  border: 1px solid rgba(var(--purple-3), 0.5);
  display: flex;
  flex-direction: column;
}

/* 中间竖分割线：在 24px 列中居中显示 1px 线 */
.panel-divider {
  align-self: stretch;
  width: 1px;
  margin: 0 auto;
  background: linear-gradient(
    180deg,
    transparent 0%,
    var(--color-border-2) 10%,
    var(--color-border-2) 90%,
    transparent 100%
  );
}

/* ── 面板头部 ── */
.panel-header {
  display: flex;
  align-items: center;
  padding: 14px 0 12px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--color-border-1);
}

.panel-icon {
  font-size: 16px;
  margin-right: 6px;
  flex-shrink: 0;
}

.crawl-icon  { color: rgb(var(--arcoblue-6)); }
.publish-icon { color: rgb(var(--purple-6)); }

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-1);
  white-space: nowrap;
}

.panel-empty {
  padding: 40px 0;
  display: flex;
  justify-content: center;
}

/* ── 任务列表：使用 Grid 均匀分布 ── */
.task-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  grid-auto-rows: 185px;
  gap: 16px;
  width: 100%;
}

.task-item {
  box-sizing: border-box;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid transparent;
  transition: box-shadow 0.15s, border-color 0.15s;
  width: 100%;
  height: 185px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.crawl-item {
  background: var(--color-bg-2);
  border-color: rgba(var(--arcoblue-3), 0.35);
}
.crawl-item:hover {
  border-color: rgba(var(--arcoblue-5), 0.7);
  box-shadow: 0 2px 8px rgba(var(--arcoblue-6), 0.1);
}

.publish-item {
  background: var(--color-bg-2);
  border-color: rgba(var(--purple-3), 0.35);
}
.publish-item:hover {
  border-color: rgba(var(--purple-5), 0.7);
  box-shadow: 0 2px 8px rgba(var(--purple-6), 0.1);
}

/* ── 任务卡片内部 ── */
.item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

/* 使卡片内容区域自动填充 */
.task-item > .item-meta,
.task-item > .item-platforms {
  flex: 1;
}

.task-item > .item-actions {
  margin-top: auto;
  padding-top: 16px;
}

.item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-1);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-badges {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.item-meta,
.item-platforms {
  font-size: 12px;
  color: var(--color-text-3);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px;
  margin-bottom: 4px;
}

.meta-sep { margin: 0 2px; }
.meta-tag { margin: 0; }

.item-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

/* ── 日志 ── */
.task-log-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  max-height: 180px;
  overflow: auto;
}

/* ── 响应式 ── */
.desktop-only { display: block; }

@media (max-width: 768px) {
  .desktop-only { display: none !important; }

  .task-manager {
    padding: 16px;
  }

  .two-panel {
    grid-template-columns: 1fr;
    grid-template-rows: auto 24px auto;
  }

  .panel-crawl {
    border-radius: 10px;
    border: 1px solid rgba(var(--arcoblue-3), 0.5);
    padding: 0 16px 16px;
  }

  .panel-publish {
    border-radius: 10px;
    border: 1px solid rgba(var(--purple-3), 0.5);
    padding: 0 16px 16px;
  }

  .panel-divider {
    width: auto;
    height: 1px;
    margin: auto 0;
    background: linear-gradient(90deg, transparent 0%, var(--color-border-2) 10%, var(--color-border-2) 90%, transparent 100%);
  }
}
</style>
