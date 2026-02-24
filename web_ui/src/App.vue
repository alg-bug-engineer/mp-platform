<template>
  <a-layout class="app-shell">
    <a-layout-content class="content">
      <router-view v-if="isAuthPage" />

      <div v-else class="workspace-main" :class="{ collapsed: navCollapsed }">
        <aside class="workspace-sidebar">
          <div class="sidebar-top">
            <button type="button" class="brand-zone" @click="navigateTo('/workspace/content')">
              <img :src="brandLogo" alt="Content Studio" class="brand-logo" />
              <div v-if="!navCollapsed" class="brand-text">
                <div class="brand-title">{{ appTitle }}</div>
                <div class="brand-subtitle">自媒体一站式创作平台</div>
              </div>
            </button>

            <a-button class="collapse-btn" shape="circle" size="small" @click="toggleSidebar">
              <template #icon>
                <component :is="navCollapsed ? IconMenuUnfold : IconMenuFold" />
              </template>
            </a-button>
          </div>

          <div class="sidebar-status">
            <a-tag :color="planColor" class="status-tag">{{ userPlanLabel }}</a-tag>
            <a-tag :color="wxAuthReady ? 'green' : 'orange'" class="status-tag">
              {{ wxAuthLabel }}
            </a-tag>
          </div>

          <nav class="sidebar-nav">
            <section v-for="group in visibleNavGroups" :key="group.key" class="nav-group">
              <div v-if="!navCollapsed" class="group-title">{{ group.label }}</div>
              <div class="group-items">
                <a-tooltip
                  v-for="item in group.items"
                  :key="item.key"
                  :content="`${item.label} · ${item.hint}`"
                  :disabled="!navCollapsed"
                  position="right"
                >
                  <button
                    type="button"
                    class="sidebar-item"
                    :class="{ active: item.active }"
                    @click="navigateToWithQuery(item.path, item.query)"
                  >
                    <span class="item-icon">
                      <component :is="item.icon" />
                    </span>
                    <span v-if="!navCollapsed" class="item-copy">
                      <span class="item-label">{{ item.label }}</span>
                      <span class="item-hint">{{ item.hint }}</span>
                    </span>
                  </button>
                </a-tooltip>
              </div>
            </section>
          </nav>

          <div class="sidebar-actions">
            <a-tooltip :content="wxAuthReady ? '已授权' : '扫码授权公众号'" :disabled="!navCollapsed" position="right">
              <a-button
                :long="!navCollapsed"
                :type="wxAuthReady ? 'secondary' : 'primary'"
                size="small"
                :disabled="wxAuthReady"
                @click="showAuthQrcode"
              >
                <template #icon>
                  <IconApps />
                </template>
                <span v-if="!navCollapsed">{{ wxAuthReady ? '已授权' : '扫码授权公众号' }}</span>
              </a-button>
            </a-tooltip>

            <a-dropdown>
              <a-button class="user-btn" :long="!navCollapsed" size="small">
                <template #icon>
                  <IconUser />
                </template>
                <span v-if="!navCollapsed">{{ userInfo.nickname || userInfo.username || '未登录' }}</span>
              </a-button>
              <template #content>
                <a-doption @click="navigateTo('/edit-user')">个人中心</a-doption>
                <a-doption @click="navigateTo('/change-password')">修改密码</a-doption>
                <a-doption @click="doLogout">退出登录</a-doption>
              </template>
            </a-dropdown>
          </div>
        </aside>

        <section class="workspace-display">
          <router-view />
        </section>
      </div>
    </a-layout-content>

    <WechatAuthQrcode ref="qrcodeRef" @success="handleAuthSuccess" />
  </a-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import {
  IconApps,
  IconBook,
  IconCommand,
  IconEdit,
  IconFile,
  IconGift,
  IconLock,
  IconMenuFold,
  IconMenuUnfold,
  IconMessage,
  IconSettings,
  IconTag,
  IconUser,
} from '@arco-design/web-vue/es/icon'
import { getCurrentUser, getWechatAuthStatus, logout, type CurrentUser } from '@/api/auth'
import WechatAuthQrcode from '@/components/WechatAuthQrcode.vue'
import brandLogo from '@/assets/logo.svg'
import { loadRuntimeSettings } from '@/utils/runtime'

type NavNode = {
  key: string
  label: string
  hint: string
  path: string
  group: string
  icon: Component
  query?: Record<string, string>
  prefix?: boolean
  adminOnly?: boolean
  hideInAllFree?: boolean
}

type NavGroup = {
  key: string
  label: string
}

const SIDEBAR_COLLAPSE_KEY = 'workspace:sidebar:collapsed'

const groups: NavGroup[] = [
  { key: 'content', label: '内容与创作' },
  { key: 'billing', label: '套餐与支付' },
  { key: 'ops', label: '运营设置' },
  { key: 'account', label: '账号设置' },
  { key: 'admin', label: '管理员' },
]

const nodes: NavNode[] = [
  { key: 'content', label: '内容池', hint: '文章管理', path: '/workspace/content', group: 'content', icon: IconBook, prefix: true },
  { key: 'subs', label: '订阅源', hint: '公众号订阅', path: '/workspace/subscriptions', group: 'content', icon: IconApps, prefix: true },
  { key: 'studio', label: '创作中台', hint: '分析/创作/仿写', path: '/workspace/studio', group: 'content', icon: IconEdit, prefix: true },

  { key: 'bill-plan', label: '套餐选择', hint: '选择套餐并下单', path: '/workspace/billing', group: 'billing', icon: IconGift, query: { anchor: 'plans' }, prefix: true, hideInAllFree: true },
  { key: 'bill-orders', label: '我的订单', hint: '支付/取消/追踪', path: '/workspace/billing', group: 'billing', icon: IconGift, query: { anchor: 'orders' }, prefix: true, hideInAllFree: true },
  { key: 'bill-integration', label: '支付接入', hint: '支付系统接入', path: '/workspace/billing', group: 'billing', icon: IconGift, query: { anchor: 'integration' }, prefix: true, hideInAllFree: true },

  { key: 'ops-msg', label: '消息任务', hint: '任务队列', path: '/workspace/ops/messages', group: 'ops', icon: IconMessage, prefix: true },
  { key: 'ops-tags', label: '标签管理', hint: '内容分类', path: '/workspace/ops/tags', group: 'ops', icon: IconTag, prefix: true },
  { key: 'ops-config', label: '系统配置', hint: '系统参数', path: '/workspace/ops/configs', group: 'ops', icon: IconSettings, prefix: true },

  { key: 'account-profile', label: '个人中心', hint: '账号信息', path: '/edit-user', group: 'account', icon: IconUser },
  { key: 'account-password', label: '修改密码', hint: '安全设置', path: '/change-password', group: 'account', icon: IconLock },

  { key: 'admin-plans', label: '用户管理', hint: '用户/配额/授权', path: '/workspace/admin/plans', group: 'admin', icon: IconCommand, adminOnly: true, prefix: true },
  { key: 'admin-analytics', label: '数据统计', hint: '运营分析面板', path: '/workspace/admin/analytics', group: 'admin', icon: IconFile, adminOnly: true, prefix: true },
]

const route = useRoute()
const router = useRouter()
const qrcodeRef = ref()
const appTitle = computed(() => import.meta.env.VITE_APP_TITLE || 'Content Studio')
const isAuthPage = computed(() => route.path === '/login')

const userInfo = ref<CurrentUser>({
  username: '',
  nickname: '',
})
const wxAuthReady = ref(false)
const navCollapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === '1')
const runtimeSettings = ref({
  product_mode: 'all_free',
  is_all_free: true,
  billing_visible: false,
  analytics_enabled: true,
})

const userPlanLabel = computed(() => {
  if (navCollapsed.value) return userInfo.value?.plan?.tier?.toUpperCase?.() || 'FREE'
  return userInfo.value?.plan?.label || '免费用户'
})
const wxAuthLabel = computed(() => {
  if (navCollapsed.value) return wxAuthReady.value ? '已授权' : '未授权'
  return wxAuthReady.value ? '公众号已授权' : '公众号未授权'
})
const isAdmin = computed(() => userInfo.value?.role === 'admin')
const isAllFreeMode = computed(() => !!runtimeSettings.value?.is_all_free)
const planColor = computed(() => {
  const tier = userInfo.value?.plan?.tier || 'free'
  if (tier === 'premium') return 'purple'
  if (tier === 'pro') return 'orange'
  return 'green'
})

const getQueryText = (key: string) => {
  const value = route.query[key]
  return Array.isArray(value) ? String(value[0] || '') : String(value || '')
}

const isNodeActive = (node: NavNode) => {
  const pathMatch = node.prefix ? route.path.startsWith(node.path) : route.path === node.path
  if (!pathMatch) return false
  if (!node.query) return true

  return Object.entries(node.query).every(([key, expected]) => {
    const current = getQueryText(key)
    if (key === 'anchor' && expected === 'plans') {
      return !current || current === expected
    }
    return current === expected
  })
}

const visibleNavGroups = computed(() => {
  const visibleNodes = nodes.filter((node) => {
    if (node.adminOnly && !isAdmin.value) return false
    if (isAllFreeMode.value && node.hideInAllFree) return false
    return true
  })
  return groups
    .map((group) => {
      const items = visibleNodes
        .filter((node) => node.group === group.key)
        .map((node) => ({
          ...node,
          active: isNodeActive(node),
        }))
      return {
        ...group,
        items,
      }
    })
    .filter((group) => group.items.length > 0)
})

const showAuthQrcode = () => {
  if (wxAuthReady.value) {
    Message.success('公众号已授权')
    return
  }
  qrcodeRef.value?.startAuth()
}

provide('showAuthQrcode', showAuthQrcode)
provide('wxAuthReady', wxAuthReady)

const toggleSidebar = () => {
  navCollapsed.value = !navCollapsed.value
}

const navigateTo = async (path: string) => {
  const target = router.resolve(path)
  if (target.fullPath === route.fullPath) return
  try {
    await router.push(target)
  } catch (err) {
    console.warn('导航失败:', err)
  }
}

const navigateToWithQuery = async (path: string, query?: Record<string, string>) => {
  const nextQuery = query ? { ...query } : {}
  const target = router.resolve({ path, query: nextQuery })
  if (target.fullPath === route.fullPath) return
  try {
    await router.push(target)
  } catch (err) {
    console.warn('导航失败:', err)
  }
}

const consumeRouteNotice = () => {
  const notice = getQueryText('notice')
  if (!notice) return
  if (notice === 'forbidden') {
    Message.warning('当前账号权限不足，已返回可访问页面')
  } else if (notice === 'billing_hidden') {
    Message.info('当前处于全站免费模式，套餐与支付面板已隐藏')
  } else {
    return
  }
  const nextQuery: Record<string, any> = { ...route.query }
  delete nextQuery.notice
  delete nextQuery.target
  router.replace({ path: route.path, query: nextQuery, hash: route.hash })
}

const fetchUser = async () => {
  if (!localStorage.getItem('token')) {
    wxAuthReady.value = false
    userInfo.value = { username: '', nickname: '' }
    return
  }
  try {
    const previousUsername = String(userInfo.value?.username || '').trim()
    const data = await getCurrentUser()
    userInfo.value = data || { username: '', nickname: '' }
    const currentUsername = String(userInfo.value?.username || '').trim()
    const strict = !!currentUsername && currentUsername !== previousUsername
    const auth = await getWechatAuthStatus(strict)
    wxAuthReady.value = !!auth?.authorized
  } catch {
    wxAuthReady.value = false
  }
}

const fetchRuntime = async () => {
  try {
    runtimeSettings.value = await loadRuntimeSettings()
  } catch {
    // ignored
  }
}

const handleAuthSuccess = () => {
  wxAuthReady.value = true
  fetchUser()
}

const doLogout = async () => {
  try {
    await logout()
  } finally {
    localStorage.removeItem('token')
    wxAuthReady.value = false
    userInfo.value = { username: '', nickname: '' }
    await router.push('/login')
    Message.success('已退出登录')
  }
}

watch(navCollapsed, (value) => {
  localStorage.setItem(SIDEBAR_COLLAPSE_KEY, value ? '1' : '0')
})

watch(
  () => route.fullPath,
  () => {
    consumeRouteNotice()
    fetchRuntime()
    fetchUser()
  }
)

onMounted(() => {
  fetchRuntime()
  fetchUser()
  consumeRouteNotice()
})
</script>

<style scoped>
.app-shell {
  height: 100vh;
  overflow: hidden;
  background: transparent;
}

.content {
  height: 100vh;
  padding: 12px;
  width: 100%;
  max-width: 100vw;
  overflow: hidden;
}

.workspace-main {
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr);
  gap: 12px;
  width: 100%;
  max-width: 100%;
  height: calc(100vh - 24px);
}

.workspace-main.collapsed {
  grid-template-columns: 88px minmax(0, 1fr);
}

.workspace-sidebar {
  border: 1px solid #dce5f5;
  border-radius: 14px;
  background: #ffffff;
  padding: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.brand-zone {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 0;
  min-width: 0;
}

.brand-logo {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
  flex: 0 0 auto;
}

.brand-text {
  text-align: left;
  min-width: 0;
}

.brand-title {
  color: var(--cs-text-strong);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brand-subtitle {
  color: var(--cs-text-muted);
  font-size: 12px;
  line-height: 1.2;
}

.collapse-btn {
  flex: 0 0 auto;
}

.sidebar-status {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
}

.status-tag {
  justify-content: center;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 2px;
}

.nav-group {
  margin-bottom: 12px;
}

.group-title {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  margin-bottom: 8px;
  padding-left: 2px;
}

.group-items {
  display: grid;
  gap: 8px;
}

.sidebar-item {
  width: 100%;
  border: 1px solid #dbe4f2;
  border-radius: 10px;
  background: #ffffff;
  text-align: left;
  padding: 9px 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 9px;
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.sidebar-item:hover {
  border-color: #8fb4f8;
  transform: translateY(-1px);
}

.sidebar-item.active {
  border-color: #2563eb;
  background: #eef4ff;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.12);
}

.item-icon {
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #1d4ed8;
  flex: 0 0 auto;
}

.item-copy {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.item-label {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.2;
}

.item-hint {
  font-size: 12px;
  color: #64748b;
  line-height: 1.2;
}

.workspace-main.collapsed .sidebar-item {
  justify-content: center;
  padding: 9px 8px;
}

.workspace-main.collapsed .sidebar-status {
  gap: 4px;
}

.workspace-main.collapsed .status-tag {
  font-size: 11px;
}

.sidebar-actions {
  display: grid;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px dashed #d7e3f7;
}

.user-btn {
  justify-content: flex-start;
}

.workspace-main.collapsed .user-btn {
  justify-content: center;
}

.workspace-display {
  min-width: 0;
  width: 100%;
  max-width: 100%;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 2px;
}

@media (max-width: 1080px) {
  .app-shell,
  .content {
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }

  .workspace-main,
  .workspace-main.collapsed {
    grid-template-columns: 1fr;
    height: auto;
  }

  .workspace-sidebar {
    overflow: visible;
  }

  .sidebar-nav {
    max-height: none;
  }

  .workspace-display {
    height: auto;
    overflow: visible;
  }
}

@media (max-width: 768px) {
  .content {
    padding: 8px;
  }

  .workspace-sidebar {
    padding: 10px;
  }
}
</style>
