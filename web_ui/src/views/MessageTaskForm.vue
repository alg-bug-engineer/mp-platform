<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMessageTask, createMessageTask, updateMessageTask } from '@/api/messageTask'
import type { MessageTaskCreate } from '@/types/messageTask'
import cronExpressionPicker from '@/components/CronExpressionPicker.vue'
import MpMultiSelect from '@/components/MpMultiSelect.vue'
import { Message } from '@arco-design/web-vue'
import ACodeEditor from '@/components/ACodeEditor.vue'

const route = useRoute()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const isEditMode = ref(false)
const taskId = ref<string | null>(null)
const showCronPicker = ref(false)
const showMpSelector = ref(false)

const cronPickerRef = ref<InstanceType<typeof cronExpressionPicker> | null>(null)
const mpSelectorRef = ref<InstanceType<typeof MpMultiSelect> | null>(null)

// task_type: 'crawl' | 'publish'
const taskType = ref<string>('crawl')
const isCrawl = computed(() => taskType.value !== 'publish')

// Platform checkboxes for publish task
const platformWechat = ref(false)
const platformCsdn = ref(false)

const formData = ref<MessageTaskCreate & { publish_platforms?: string[] }>({
  name: '',
  message_type: 0,
  message_template: '',
  web_hook_url: '',
  mps_id: [],
  status: 1,
  cron_exp: '*/5 * * * *',
  auto_compose_sync_enabled: 0,
  auto_compose_platform: 'wechat',
  auto_compose_instruction: '',
  auto_compose_topk: 1,
  csdn_publish_enabled: 0,
  csdn_publish_topk: 3,
  task_type: 'crawl',
  publish_platforms: [],
})

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

const selectedMpsDisplay = computed(() => {
  const arr = formData.value.mps_id || []
  if (!Array.isArray(arr) || arr.length === 0) return '（未选择，留空对所有公众号生效）'
  return arr.map((m: any) => String(m.name || m.mp_name || m.id || '')).filter(Boolean).join('、')
})

const fetchTaskDetail = async (id: string) => {
  loading.value = true
  try {
    const res = await getMessageTask(id)
    let parsedMps: any[] = []
    try {
      parsedMps = JSON.parse(String(res.mps_id || '[]'))
      if (!Array.isArray(parsedMps)) parsedMps = []
    } catch {
      parsedMps = []
    }

    let parsedPlatforms: string[] = []
    try {
      const raw = res.publish_platforms
      parsedPlatforms = typeof raw === 'string'
        ? JSON.parse(raw)
        : (Array.isArray(raw) ? raw : [])
      if (!Array.isArray(parsedPlatforms)) parsedPlatforms = []
    } catch {
      parsedPlatforms = []
    }

    taskType.value = String(res.task_type || 'crawl') || 'crawl'
    platformWechat.value = parsedPlatforms.includes('wechat_mp')
    platformCsdn.value = parsedPlatforms.includes('csdn')

    formData.value = {
      name: res.name || '',
      message_type: Number(res.message_type || 0),
      message_template: res.message_template || '',
      web_hook_url: res.web_hook_url || '',
      mps_id: parsedMps,
      status: Number(res.status ?? 1),
      cron_exp: res.cron_exp || '*/5 * * * *',
      auto_compose_sync_enabled: Number(res.auto_compose_sync_enabled || 0),
      auto_compose_platform: String(res.auto_compose_platform || 'wechat'),
      auto_compose_instruction: String(res.auto_compose_instruction || ''),
      auto_compose_topk: Number(res.auto_compose_topk || 1),
      csdn_publish_enabled: Number(res.csdn_publish_enabled || 0),
      csdn_publish_topk: Number(res.csdn_publish_topk || 3),
      task_type: taskType.value,
      publish_platforms: parsedPlatforms,
    }
    nextTick(() => {
      cronPickerRef.value?.parseExpression(formData.value.cron_exp)
      mpSelectorRef.value?.parseSelected(formData.value.mps_id)
    })
  } finally {
    loading.value = false
  }
}

const buildPublishPlatforms = (): string[] => {
  const p: string[] = []
  if (platformWechat.value) p.push('wechat_mp')
  if (platformCsdn.value) p.push('csdn')
  return p
}

const handleSubmit = async () => {
  loading.value = true
  try {
    await formRef.value.validate()
  } catch (error: any) {
    Message.error(error?.errors?.join('\n') || '表单验证失败，请检查输入内容')
    loading.value = false
    return
  }
  try {
    const platforms = buildPublishPlatforms()
    const submitData = {
      ...formData.value,
      task_type: taskType.value,
      publish_platforms: platforms,
      // For publish tasks, set enabled flags based on platform selection
      auto_compose_sync_enabled: taskType.value === 'publish'
        ? (platformWechat.value ? 1 : 0)
        : Number(formData.value.auto_compose_sync_enabled || 0),
      csdn_publish_enabled: taskType.value === 'publish'
        ? (platformCsdn.value ? 1 : 0)
        : Number(formData.value.csdn_publish_enabled || 0),
      auto_compose_platform: String(formData.value.auto_compose_platform || 'wechat'),
      auto_compose_instruction: String(formData.value.auto_compose_instruction || ''),
      auto_compose_topk: Math.max(1, Number(formData.value.auto_compose_topk || 1)),
      csdn_publish_topk: Math.max(1, Number(formData.value.csdn_publish_topk || 3)),
      mps_id: JSON.stringify(formData.value.mps_id || []),
    }
    if (isEditMode.value && taskId.value) {
      await updateMessageTask(taskId.value, submitData)
      Message.success('更新任务成功，点击应用按钮后任务才会生效')
    } else {
      await createMessageTask(submitData)
      Message.success('创建任务成功，点击应用按钮后任务才会生效')
    }
    setTimeout(() => router.push('/message-tasks'), 1200)
  } catch (error) {
    console.error(error)
    Message.error('提交失败')
  } finally {
    loading.value = false
  }
}

const rules = {
  name: [
    { required: true, message: '请输入任务名称' },
    { min: 2, max: 50, message: '任务名称长度应在2-50个字符之间' }
  ]
}

onMounted(() => {
  // Read task type from route query (new task) or from task data (edit)
  const queryType = String(route.query.type || '')
  if (queryType === 'publish' || queryType === 'crawl') {
    taskType.value = queryType
    formData.value.task_type = queryType
  }
  if (route.params.id) {
    isEditMode.value = true
    taskId.value = String(route.params.id)
    fetchTaskDetail(taskId.value)
  }
})
</script>

<template>
  <a-spin :loading="loading">
    <div class="task-form-page">
      <a-page-header
        :title="isEditMode ? '编辑任务' : (taskType === 'publish' ? '新建发布任务' : '新建抓取任务')"
        :show-back="true"
        @back="router.go(-1)"
      />

      <a-form :model="formData" :rules="rules" ref="formRef" layout="vertical">

        <!-- ① 基本信息 -->
        <a-card title="基本信息" class="form-card">
          <a-row :gutter="16">
            <a-col :span="16">
              <a-form-item label="任务名称" field="name" required>
                <a-input v-model="formData.name" placeholder="请输入任务名称" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="状态">
                <a-switch
                  :model-value="formData.status === 1"
                  @change="(v) => formData.status = v ? 1 : 0"
                  checked-text="启用"
                  unchecked-text="禁用"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>

        <!-- 抓取任务 —— ② 抓取配置 -->
        <template v-if="isCrawl">
          <a-card title="抓取配置" class="form-card">
            <a-form-item label="订阅公众号">
              <div class="selector-row">
                <span class="selector-preview">{{ selectedMpsDisplay }}</span>
                <a-button @click="showMpSelector = true">选择</a-button>
              </div>
            </a-form-item>
            <a-form-item label="执行计划" field="cron_exp" required>
              <div class="selector-row">
                <a-input
                  v-model="formData.cron_exp"
                  placeholder="cron 表达式"
                  readonly
                  style="width: 200px"
                />
                <span style="color: var(--color-text-3); font-size: 13px;">{{ parseCronExpression(formData.cron_exp) }}</span>
                <a-button @click="showCronPicker = true">修改</a-button>
              </div>
            </a-form-item>
          </a-card>

          <!-- ③ 消息通知 -->
          <a-collapse :default-active-key="[]" class="form-card notice-collapse">
            <a-collapse-item key="notice" header="消息通知（可选）">
              <a-form-item label="通知类型" field="message_type">
                <a-radio-group v-model="formData.message_type" type="button">
                  <a-radio :value="0">Message</a-radio>
                  <a-radio :value="1">WebHook</a-radio>
                </a-radio-group>
              </a-form-item>
              <a-form-item label="消息模板" field="message_template">
                <a-code-editor
                  v-model="formData.message_template"
                  placeholder="请输入消息模板内容"
                  language="custom"
                />
                <a-space style="margin-top: 8px">
                  <a-button
                    v-if="formData.message_type === 0"
                    type="outline"
                    size="small"
                    @click="formData.message_template = '### {{feed.mp_name}} 订阅消息：\n{% if articles %}\n{% for article in articles %}\n- [**{{ article.title }}**]({{article.url}}) ({{ article.publish_time }})\n{% endfor %}\n{% else %}\n- 暂无文章\n{% endif %}'"
                  >
                    使用示例消息模板
                  </a-button>
                  <a-button
                    v-else
                    type="outline"
                    size="small"
                    @click="formData.message_template = `{\n    'articles': [\n    {% for article in articles %}\n    {{article}}\n    {% if not loop.last %},{% endif %}\n    {% endfor %}\n    ]\n}`"
                  >
                    使用示例 WebHook 模板
                  </a-button>
                </a-space>
              </a-form-item>
              <a-form-item label="WebHook 地址" field="web_hook_url">
                <a-input v-model="formData.web_hook_url" placeholder="请输入 WebHook 地址" />
                <a-link href="https://open.dingtalk.com/document/orgapp/obtain-the-webhook-address-of-a-custom-robot" target="_blank">如何获取 WebHook</a-link>
              </a-form-item>
            </a-collapse-item>
          </a-collapse>
        </template>

        <!-- 发布任务 —— ② 来源与规模 -->
        <template v-else>
          <a-card title="来源与规模" class="form-card">
            <a-form-item label="来源公众号">
              <div class="selector-row">
                <span class="selector-preview">{{ selectedMpsDisplay }}</span>
                <a-button @click="showMpSelector = true">选择</a-button>
              </div>
            </a-form-item>
            <a-form-item label="检查最新 N 篇">
              <a-input-number
                v-model="formData.auto_compose_topk"
                :min="1"
                :max="20"
                style="width: 120px"
              />
              <span style="margin-left: 8px; color: var(--color-text-3);">从最新 N 篇文章中选取未发布的文章</span>
            </a-form-item>
          </a-card>

          <!-- ③ 发布平台 -->
          <a-card title="发布平台" class="form-card">
            <a-alert type="info" style="margin-bottom: 16px">
              勾选需要发布的平台。各平台需提前在个人中心完成配置。
            </a-alert>

            <!-- 微信公众号草稿箱 -->
            <div class="platform-card" :class="{ active: platformWechat }">
              <div class="platform-header">
                <a-checkbox v-model="platformWechat">
                  <span class="platform-title">微信公众号草稿箱（AI 创作）</span>
                </a-checkbox>
              </div>
              <div v-if="platformWechat" class="platform-detail">
                <a-form-item label="创作指令（可选）" style="margin-bottom: 0">
                  <a-textarea
                    v-model="formData.auto_compose_instruction"
                    :auto-size="{ minRows: 2, maxRows: 4 }"
                    placeholder="例如：强调实操建议，语气专业克制，避免模板化表达"
                  />
                </a-form-item>
              </div>
            </div>

            <!-- CSDN -->
            <div class="platform-card" :class="{ active: platformCsdn }" style="margin-top: 10px">
              <div class="platform-header">
                <a-checkbox v-model="platformCsdn">
                  <span class="platform-title">CSDN</span>
                </a-checkbox>
              </div>
              <div v-if="platformCsdn" class="platform-detail">
                <a-alert type="info" :show-icon="false">
                  需先完成「CSDN 扫码登录」授权后方可使用。
                  <a-link href="/csdn/auth" target="_blank">前往扫码授权 →</a-link>
                </a-alert>
                <a-form-item label="创作指令（可选）" style="margin: 8px 0 0 0">
                  <a-textarea
                    v-model="formData.auto_compose_instruction"
                    :auto-size="{ minRows: 2, maxRows: 4 }"
                    placeholder="例如：强调实操建议，语气专业克制，避免模板化表达"
                  />
                </a-form-item>
                <div style="color: var(--color-text-3); font-size: 12px; margin-top: 4px;">
                  系统将对抓取内容进行 AI 创作后推送到 CSDN，默认配图 2 张
                </div>
              </div>
            </div>
          </a-card>

          <!-- ④ 执行计划 -->
          <a-card title="执行计划" class="form-card">
            <a-form-item label="Cron 表达式" field="cron_exp" required>
              <div class="selector-row">
                <a-input
                  v-model="formData.cron_exp"
                  placeholder="cron 表达式"
                  readonly
                  style="width: 200px"
                />
                <span style="color: var(--color-text-3); font-size: 13px;">{{ parseCronExpression(formData.cron_exp) }}</span>
                <a-button @click="showCronPicker = true">修改</a-button>
              </div>
            </a-form-item>
          </a-card>
        </template>

        <!-- 提交按钮 -->
        <div class="form-footer">
          <a-space>
            <a-button type="primary" html-type="submit" :loading="loading" @click="handleSubmit">
              {{ isEditMode ? '保存修改' : '创建任务' }}
            </a-button>
            <a-button @click="router.go(-1)">取消</a-button>
          </a-space>
        </div>
      </a-form>

      <!-- Cron 选择器 -->
      <a-modal v-model:visible="showCronPicker" title="选择 Cron 表达式" :footer="false" width="800px">
        <cronExpressionPicker ref="cronPickerRef" v-model="formData.cron_exp" />
        <template #footer>
          <a-button type="primary" @click="showCronPicker = false">确定</a-button>
        </template>
      </a-modal>

      <!-- 公众号选择器 -->
      <a-modal v-model:visible="showMpSelector" title="选择公众号" :footer="false" width="800px">
        <MpMultiSelect ref="mpSelectorRef" v-model="formData.mps_id" />
        <template #footer>
          <a-button type="primary" @click="showMpSelector = false">确定</a-button>
        </template>
      </a-modal>
    </div>
  </a-spin>
</template>

<style scoped>
.task-form-page {
  padding: 20px;
  max-width: 860px;
  margin: 0 auto;
}

.form-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.notice-collapse {
  border-radius: 8px;
  overflow: hidden;
}

.selector-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.selector-preview {
  color: var(--color-text-2);
  font-size: 13px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-card {
  border: 1px solid var(--color-border-2);
  border-radius: 6px;
  padding: 12px 16px;
  transition: border-color 0.2s;
}

.platform-card.active {
  border-color: rgb(var(--primary-6));
}

.platform-header {
  display: flex;
  align-items: center;
}

.platform-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-1);
}

.platform-detail {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border-1);
}

.form-footer {
  margin-top: 8px;
  padding-bottom: 24px;
}
</style>
