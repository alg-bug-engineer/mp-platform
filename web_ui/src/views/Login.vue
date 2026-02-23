<template>
  <div class="login-page">
    <div class="login-grid">
      <section class="hero">
        <div class="hero-pill">Content Studio</div>
        <h1>{{ title }}</h1>
        <p>围绕选题、创作、配图、草稿投递与复盘，打造自媒体博主可持续运营的完整工作流。</p>
        <div class="hero-metrics">
          <div class="metric">
            <div class="metric-value">一站式</div>
            <div class="metric-label">内容流水线</div>
          </div>
          <div class="metric">
            <div class="metric-value">多账号</div>
            <div class="metric-label">数据隔离</div>
          </div>
          <div class="metric">
            <div class="metric-value">可商业化</div>
            <div class="metric-label">套餐与配额</div>
          </div>
        </div>
      </section>

      <section class="card">
        <a-tabs v-model:active-key="activeTab">
          <a-tab-pane key="login" title="登录">
            <a-form :model="loginForm" layout="vertical" @submit="handleLogin">
              <a-form-item label="账号 / 手机号">
                <a-input v-model="loginForm.account" placeholder="请输入账号或手机号" />
              </a-form-item>
              <a-form-item label="密码">
                <a-input-password v-model="loginForm.password" placeholder="请输入密码" />
              </a-form-item>
              <a-button type="primary" html-type="submit" :loading="loading" long>登录</a-button>
            </a-form>
          </a-tab-pane>
          <a-tab-pane key="register" title="注册">
            <a-form :model="registerForm" layout="vertical" @submit="handleRegister">
              <a-form-item label="手机号">
                <a-input v-model="registerForm.phone" placeholder="请输入手机号" />
              </a-form-item>
              <a-form-item label="密码">
                <a-input-password v-model="registerForm.password" placeholder="至少 6 位" />
              </a-form-item>
              <a-form-item label="昵称(可选)">
                <a-input v-model="registerForm.nickname" placeholder="请输入昵称" />
              </a-form-item>
              <a-button type="primary" html-type="submit" :loading="loading" long>注册并登录</a-button>
            </a-form>
          </a-tab-pane>
        </a-tabs>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { login, register } from '@/api/auth'

const title = computed(() => import.meta.env.VITE_APP_TITLE || '商业化内容创作平台')
const router = useRouter()
const route = useRoute()
const activeTab = ref('login')
const loading = ref(false)

const loginForm = ref({
  account: '',
  password: '',
})

const registerForm = ref({
  phone: '',
  password: '',
  nickname: '',
})

const isPhone = (value: string) => /^1[3-9]\d{9}$/.test(value)

const doLogin = async (username: string, password: string) => {
  const res = await login({ username, password })
  localStorage.setItem('token', res.access_token)
  localStorage.setItem('token_expire', String(Date.now() + (res.expires_in * 1000)))
  await router.push('/')
}

const handleLogin = async () => {
  if (!(loginForm.value.account || '').trim()) {
    Message.error('请输入账号或手机号')
    return
  }
  loading.value = true
  try {
    await doLogin((loginForm.value.account || '').trim(), loginForm.value.password)
    Message.success('登录成功')
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  if (!isPhone(registerForm.value.phone)) {
    Message.error('请输入正确的手机号')
    return
  }
  if ((registerForm.value.password || '').length < 6) {
    Message.error('密码至少 6 位')
    return
  }
  loading.value = true
  try {
    await register({
      phone: registerForm.value.phone,
      password: registerForm.value.password,
      nickname: registerForm.value.nickname,
    })
    await doLogin(registerForm.value.phone, registerForm.value.password)
    Message.success('注册并登录成功')
  } finally {
    loading.value = false
  }
}

const consumeAuthNotice = async () => {
  const raw = route.query.error
  const code = Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
  if (!code) return
  if (code === 'session_expired') {
    Message.warning('登录状态已过期，请重新登录')
  } else if (code === 'unauthorized') {
    Message.info('请先登录后访问目标页面')
  }
  const nextQuery: Record<string, any> = { ...route.query }
  delete nextQuery.error
  await router.replace({ path: route.path, query: nextQuery, hash: route.hash })
}

onMounted(() => {
  consumeAuthNotice()
})
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 12% 8%, rgba(37, 99, 235, 0.14), transparent 36%),
    radial-gradient(circle at 86% 2%, rgba(2, 132, 199, 0.12), transparent 32%),
    #f8fbff;
  padding: 16px;
}

.login-grid {
  width: min(1080px, 100%);
  display: grid;
  grid-template-columns: 1.1fr 460px;
  gap: 20px;
}

.hero {
  border: 1px solid #dce6f8;
  border-radius: 18px;
  padding: 28px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(8px);
  color: #1f2937;
}

.hero-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
  border: 1px solid rgba(37, 99, 235, 0.35);
  font-size: 12px;
  color: #1d4ed8;
}

h1 {
  margin: 12px 0 10px;
  font-size: 28px;
  color: #0f172a;
  line-height: 1.25;
}

p {
  color: #475569;
  line-height: 1.7;
}

.hero-metrics {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.metric {
  border: 1px solid #dce6f8;
  border-radius: 12px;
  padding: 10px;
  background: #f8fbff;
}

.metric-value {
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

.metric-label {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.card {
  width: 100%;
  border-radius: 18px;
  padding: 22px;
  border: 1px solid #dce6f8;
  background: #ffffff;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
}

:deep(.arco-form-item-label-col > label) {
  color: #334155;
}

:deep(.arco-tabs-nav-tab-title) {
  color: #334155;
}

@media (max-width: 980px) {
  .login-grid {
    grid-template-columns: 1fr;
  }

  .hero {
    display: none;
  }
}
</style>
