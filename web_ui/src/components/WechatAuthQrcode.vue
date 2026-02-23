<template>
  <a-modal
    v-model:visible="visible"
    title="微信授权"
    :footer="false"
    :mask-closable="false"
    width="400px"
    @cancel="clearTimer"
  >
    <div class="qrcode-container">
      <div v-if="loading" class="loading">
        <a-spin size="large" />
        <p>正在获取二维码...</p>
      </div>
      <div v-else-if="qrcodeUrl" class="qrcode" style="text-align:center;">
        <img :src="qrcodeUrl" alt="微信授权二维码" />
        <a-tooltip content="扫码请选择公众号或者服务号，如果没有帐号，请点击下方注册" placement="top">
        <p>请使用微信扫码授权</p>
        </a-tooltip>
        <p>如果提示没有可用帐号码，请点此
          <a-tooltip content="注册时请选择公众号或者服务号" placement="top">
          <a-link href="https://mp.weixin.qq.com/cgi-bin/registermidpage?action=index&weblogo=1&lang=zh_CN" target="_blank">注册</a-link><br/>
          </a-tooltip>
        </p>
      </div>
      <div v-else class="error">
        <a-alert type="error" :message="errorMessage" />
        <a-button type="primary" @click="startAuth">重试</a-button>
      </div>
    </div>
  </a-modal>
</template>

<script lang="ts" setup>
import { onBeforeUnmount, ref } from 'vue'
import { QRCode, checkQRCodeStatus, stopQRCodeStatusCheck } from '@/api/auth'

const emit = defineEmits(['success', 'error'])

const visible = ref(false)
const loading = ref(false)
const qrcodeUrl = ref('')
const errorMessage = ref('')

const normalizeError = (err: unknown) => {
  if (typeof err === 'string') return err
  if (err instanceof Error) return err.message || '操作失败，请重试'
  return '操作失败，请重试'
}

const startAuth = async () => {
  clearTimer()
  try {
    visible.value = true
    loading.value = true
    qrcodeUrl.value = ''
    errorMessage.value = ''
    
    // 获取二维码
    const res = await QRCode()
    if (!res?.code) {
      throw new Error(res?.msg || '二维码生成失败')
    }
    qrcodeUrl.value = String(res.code)
    loading.value = false

    // 开始检查授权状态
    checkQRCodeStatus().then((statusRes) => {
      if (statusRes?.login_status) {
        clearTimer()
        emit('success', statusRes)
        visible.value = false
      }
    }).catch((err) => {
      qrcodeUrl.value = ''
      errorMessage.value = normalizeError(err) || '授权失败，请重试'
      emit('error', err)
    })
  } catch (err) {
    loading.value = false
    errorMessage.value = normalizeError(err) || '获取二维码失败，请重试'
    emit('error', err)
  }
}

const clearTimer = () => {
  stopQRCodeStatusCheck()
}

defineExpose({
  startAuth
})

onBeforeUnmount(clearTimer)
</script>

<style scoped>
.qrcode-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
}

.loading,
.qrcode,
.error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.qrcode img {
  width: 200px;
  height: 200px;
}
</style>
