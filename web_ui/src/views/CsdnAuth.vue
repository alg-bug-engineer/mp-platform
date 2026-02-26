<template>
  <div class="csdn-auth">
    <a-page-header
      title="CSDN 扫码登录"
      subtitle="扫码绑定 CSDN 账号，启用文章自动推送"
      :show-back="true"
      @back="$router.back()"
    />

    <a-card>
      <!-- 当前授权状态 -->
      <a-descriptions :column="1" style="margin-bottom: 20px;">
        <a-descriptions-item label="授权状态">
          <a-tag v-if="authStatus?.authorized" color="green">已授权</a-tag>
          <a-tag v-else color="red">未授权 / 已失效</a-tag>
        </a-descriptions-item>
        <a-descriptions-item v-if="authStatus?.csdn_username" label="CSDN 用户">
          {{ authStatus.csdn_username }}
        </a-descriptions-item>
        <a-descriptions-item v-if="authStatus?.updated_at" label="授权时间">
          {{ authStatus.updated_at }}
        </a-descriptions-item>
      </a-descriptions>

      <!-- 操作区 -->
      <a-space>
        <a-button
          type="primary"
          :loading="startingQr"
          @click="handleStartQr"
        >
          {{ sessionStatus === 'pending' ? '重新获取二维码' : '扫码登录 CSDN' }}
        </a-button>
        <a-button
          v-if="sessionStatus === 'pending'"
          @click="handleRefreshQr"
          :loading="refreshingQr"
        >
          刷新二维码
        </a-button>
        <a-button
          v-if="sessionStatus === 'pending' || sessionStatus === 'starting'"
          status="warning"
          @click="handleCancelQr"
        >
          取消扫码
        </a-button>
        <a-button
          v-if="authStatus?.authorized"
          status="danger"
          @click="handleClearAuth"
        >
          解除授权
        </a-button>
      </a-space>

      <!-- 浏览器启动中提示 -->
      <div v-if="sessionStatus === 'starting'" class="qr-section">
        <a-divider />
        <a-spin dot>
          <div style="padding: 40px; color: var(--color-text-3); font-size: 14px;">
            浏览器启动中，正在获取二维码，请稍候…
          </div>
        </a-spin>
      </div>

      <!-- QR 图片 -->
      <div v-if="qrImage" class="qr-section">
        <a-divider />
        <p class="qr-hint">
          <template v-if="sessionStatus === 'pending'">
            请使用 <strong>CSDN App</strong> 扫描下方二维码完成登录
          </template>
          <template v-else-if="sessionStatus === 'success'">
            <a-tag color="green">扫码成功！</a-tag> 授权已保存，即将自动推送文章。
          </template>
          <template v-else-if="sessionStatus === 'timeout'">
            <a-tag color="orange">二维码已超时</a-tag> 请点击「扫码登录 CSDN」重新获取。
          </template>
        </p>
        <img :src="qrImage" class="qr-image" alt="CSDN 登录二维码" />
        <p v-if="sessionStatus === 'pending'" class="qr-timeout-hint">
          二维码 {{ expiresIn }}s 后过期
        </p>
      </div>

      <!-- 使用说明 -->
      <a-divider />
      <a-alert type="info" style="margin-top: 12px;">
        <template #title>使用说明</template>
        <ul style="margin: 8px 0 0 16px; padding: 0;">
          <li>点击「扫码登录 CSDN」，系统会在后台启动浏览器（约 5-15 秒）并展示二维码。</li>
          <li>用 CSDN App 扫码登录后，系统保存浏览器会话状态，自动推送文章无需再次扫码。</li>
          <li>当推送失败提示「登录态失效」时，请回此页面重新扫码。</li>
          <li>页面显示的是浏览器截图，若二维码模糊请点击「刷新二维码」。</li>
        </ul>
      </a-alert>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { csdnApi, type CsdnAuthStatus } from '@/api/csdn'

const authStatus = ref<CsdnAuthStatus | null>(null)
const qrImage = ref('')
const sessionStatus = ref<string>('none')
const expiresIn = ref(300)
const startingQr = ref(false)
const refreshingQr = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null
let imageTimer: ReturnType<typeof setInterval> | null = null
let countdownTimer: ReturnType<typeof setInterval> | null = null

// ── 初始化 ──────────────────────────────────────────────────────────────────
// 注意：http 拦截器在 code===0 时已将 response.data.data 解包，
// 所以 await csdnApi.xxx() 直接返回业务数据，无需再检查 res.data.code。
async function loadAuthStatus() {
  try {
    const res = await csdnApi.getAuthStatus()
    // res 已是 CsdnAuthStatus 对象
    if (res) authStatus.value = res
  } catch (e) {
    // ignore
  }
}

// ── 启动扫码 ─────────────────────────────────────────────────────────────────
async function handleStartQr() {
  startingQr.value = true
  stopPolling()
  stopImagePolling()
  qrImage.value = ''
  try {
    // res 已是 { status, message, expires_in }
    const res = await csdnApi.startQr()
    expiresIn.value = (res as any)?.expires_in || 300
    sessionStatus.value = (res as any)?.status || 'starting'
    // 后台浏览器已启动，轮询 /qr/image 直到截图就绪
    startImagePolling()
    startPolling()
  } catch (e: any) {
    Message.error(e?.message || e || '启动扫码失败')
  } finally {
    startingQr.value = false
  }
}

// ── 轮询 QR 图片（starting → pending 阶段） ──────────────────────────────────
function startImagePolling() {
  stopImagePolling()
  imageTimer = setInterval(async () => {
    try {
      // res 已是 { status, qr_image }
      const res = await csdnApi.getQrImage() as any
      const img = res?.qr_image
      if (img) {
        qrImage.value = img
        sessionStatus.value = res?.status || 'pending'
        stopImagePolling()
        startCountdown()
      }
    } catch (e) {
      // ignore network blips
    }
  }, 2000)
}

function stopImagePolling() {
  if (imageTimer) {
    clearInterval(imageTimer)
    imageTimer = null
  }
}

// ── 刷新二维码 ───────────────────────────────────────────────────────────────
async function handleRefreshQr() {
  refreshingQr.value = true
  try {
    const res = await csdnApi.getQrImage() as any
    qrImage.value = res?.qr_image || qrImage.value
  } catch (e) {
    // ignore
  } finally {
    refreshingQr.value = false
  }
}

// ── 取消扫码 ─────────────────────────────────────────────────────────────────
async function handleCancelQr() {
  stopPolling()
  stopImagePolling()
  try {
    await csdnApi.cancelQr()
  } catch (e) {
    // ignore
  }
  sessionStatus.value = 'none'
  qrImage.value = ''
}

// ── 解除授权 ─────────────────────────────────────────────────────────────────
async function handleClearAuth() {
  try {
    await csdnApi.clearAuth()
    Message.success('CSDN 授权已清除')
    authStatus.value = null
    qrImage.value = ''
    sessionStatus.value = 'none'
  } catch (e: any) {
    Message.error(e?.message || e || '清除授权失败')
  }
}

// ── 轮询登录状态 ──────────────────────────────────────────────────────────────
function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      // res 已是 CsdnQrStatusResult: { session_status, csdn_username?, csdn_auth? }
      const res = await csdnApi.getQrStatus() as any
      const st = res?.session_status
      if (!st || st === 'starting') return  // 浏览器仍在启动中，继续等待
      if (st === 'success') {
        sessionStatus.value = 'success'
        stopPolling()
        stopImagePolling()
        Message.success(`CSDN 登录成功！${res.csdn_username ? `（${res.csdn_username}）` : ''}`)
        await loadAuthStatus()
      } else if (st === 'timeout' || st === 'failed') {
        sessionStatus.value = st
        stopPolling()
        stopImagePolling()
        Message.warning('二维码已超时，请重新获取')
      } else if (st === 'cancelled') {
        sessionStatus.value = 'none'
        qrImage.value = ''
        stopPolling()
        stopImagePolling()
      }
    } catch (e) {
      // ignore network blips
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    if (expiresIn.value > 0) {
      expiresIn.value -= 1
    } else {
      clearInterval(countdownTimer!)
      countdownTimer = null
    }
  }, 1000)
}

// ── 生命周期 ──────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadAuthStatus()
  // 页面刷新后，检查后台是否有活跃会话
  try {
    const res = await csdnApi.getQrStatus() as any
    const st = res?.session_status
    if (st === 'starting') {
      sessionStatus.value = 'starting'
      startImagePolling()
      startPolling()
    } else if (st === 'pending') {
      sessionStatus.value = 'pending'
      const imgRes = await csdnApi.getQrImage() as any
      qrImage.value = imgRes?.qr_image || ''
      startPolling()
    }
  } catch (e) {
    // ignore
  }
})

onUnmounted(() => {
  stopPolling()
  stopImagePolling()
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<style scoped>
.csdn-auth {
  max-width: 640px;
  margin: 0 auto;
}

.qr-section {
  text-align: center;
  margin-top: 16px;
}

.qr-hint {
  margin-bottom: 12px;
  font-size: 14px;
  color: var(--color-text-2);
}

.qr-image {
  width: 280px;
  height: auto;
  border: 1px solid var(--color-border-2);
  border-radius: 4px;
}

.qr-timeout-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-3);
}
</style>
