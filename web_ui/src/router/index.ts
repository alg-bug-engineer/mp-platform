import { createRouter, createWebHistory } from 'vue-router'
import BasicLayout from '../components/Layout/BasicLayout.vue'
import ExportRecords from '../views/ExportRecords.vue'
import Login from '../views/Login.vue'
import ArticleList from '../views/ArticleList.vue'
import ChangePassword from '../views/ChangePassword.vue'
import EditUser from '../views/EditUser.vue'
import AddSubscription from '../views/AddSubscription.vue'
import WeChatMpManagement from '../views/WeChatMpManagement.vue'
import ConfigList from '../views/ConfigList.vue'
import ConfigDetail from '../views/ConfigDetail.vue'
import MessageTaskList from '../views/MessageTaskList.vue'
import MessageTaskForm from '../views/MessageTaskForm.vue'
import NovelReader from '../views/NovelReader.vue'
import AiStudio from '../views/AiStudio.vue'
import PlanManagement from '../views/PlanManagement.vue'
import BillingCenter from '../views/BillingCenter.vue'
import AnalyticsDashboard from '../views/AnalyticsDashboard.vue'
import { loadRuntimeSettings } from '@/utils/runtime'

const routes = [
  {
    path: '/',
    component: BasicLayout,
    children: [
      {
        path: '',
        name: 'Home',
        alias: ['/workspace/content'],
        component: ArticleList,
        meta: { requiresAuth: true }
      },
      {
        path: 'workspace',
        redirect: '/workspace/content',
      },
      {
        path: 'workspace/ops',
        redirect: '/workspace/ops/messages',
      },
      {
        path: 'change-password',
        name: 'ChangePassword',
        component: ChangePassword,
        meta: { requiresAuth: true }
      },
      {
        path: 'edit-user',
        name: 'EditUser',
        component: EditUser,
        meta: { requiresAuth: true }
      },
      {
        path: 'add-subscription',
        name: 'AddSubscription',
        alias: ['/workspace/subscriptions'],
        component: AddSubscription,
        meta: { requiresAuth: true }
      },
      {
        path: 'wechat/mp',
        name: 'WeChatMpManagement',
        component: WeChatMpManagement,
        meta: { 
          requiresAuth: true,
          permissions: ['wechat:manage'] 
        }
      },
      
      {
        path: 'configs',
        name: 'ConfigList',
        alias: ['/workspace/ops/configs'],
        component: ConfigList,
        meta: { 
          requiresAuth: true,
          permissions: ['admin'] 
        }
      },
      {
        path: 'export/records',
        name: 'ExportList',
        component: ExportRecords,
        meta: { 
          requiresAuth: true,
          permissions: ['config:view'] 
        }
      },
      {
        path: 'configs/:key',
        name: 'ConfigDetail',
        component: ConfigDetail,
        props: true,
        meta: { 
          requiresAuth: true,
          permissions: ['admin'] 
        }
      },
      {
        path: 'message-tasks',
        name: 'MessageTaskList',
        alias: ['/workspace/ops/messages'],
        component: MessageTaskList,
        meta: { 
          requiresAuth: true,
          permissions: ['message_task:view'] 
        }
      },
      {
        path: 'message-tasks/add',
        name: 'MessageTaskAdd',
        component: MessageTaskForm,
        meta: { 
          requiresAuth: true,
          permissions: ['message_task:edit'] 
        }
      },
      {
        path: 'message-tasks/edit/:id',
        name: 'MessageTaskEdit',
        component: MessageTaskForm,
        props: true,
        meta: { 
          requiresAuth: true,
          permissions: ['message_task:edit'] 
        }
      },
      {
        path: 'sys-info',
        name: 'SysInfo',
        component: () => import('@/views/SysInfo.vue'),
        meta: { 
          requiresAuth: true,
          permissions: ['admin'] 
        }
      },
      {
        path: 'ai/studio',
        name: 'AiStudio',
        alias: ['/workspace/studio'],
        component: AiStudio,
        meta: {
          requiresAuth: true
        }
      },
      {
        path: 'workspace/draftbox',
        redirect: '/workspace/studio',
      },
      {
        path: 'billing',
        name: 'BillingCenter',
        alias: ['/workspace/billing'],
        component: BillingCenter,
        meta: {
          requiresAuth: true,
          hideInAllFree: true,
        }
      },
      {
        path: 'admin/plans',
        name: 'PlanManagement',
        alias: ['/workspace/admin/plans'],
        component: PlanManagement,
        meta: {
          requiresAuth: true,
          permissions: ['admin']
        }
      },
      {
        path: 'admin/analytics',
        name: 'AnalyticsDashboard',
        alias: ['/workspace/admin/analytics'],
        component: AnalyticsDashboard,
        meta: {
          requiresAuth: true,
          permissions: ['admin'],
        }
      },
      {
        path: 'tags',
        name: 'TagList',
        alias: ['/workspace/ops/tags'],
        component: () => import('@/views/TagList.vue'),
        meta: { 
          requiresAuth: true,
          permissions: ['tag:view'] 
        }
      },
      {
        path: 'tags/add',
        name: 'TagAdd',
        component: () => import('@/views/TagForm.vue'),
        meta: { 
          requiresAuth: true,
          permissions: ['tag:edit'] 
        }
      },
      {
        path: 'tags/edit/:id',
        name: 'TagEdit',
        component: () => import('@/views/TagForm.vue'),
        props: true,
        meta: { 
          requiresAuth: true,
          permissions: ['tag:edit'] 
        }
      },
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: Login
  },
  {
        path: '/reader',
        name: 'NovelReader',
        component: NovelReader,
        meta: { requiresAuth: true }
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash }
    if (to.path !== from.path) return { top: 0 }
    return {}
  },
})

const canonicalPathMap: Record<string, string> = {
  '/add-subscription': '/workspace/subscriptions',
  '/ai/studio': '/workspace/studio',
  '/draftbox': '/workspace/studio',
  '/workspace/draftbox': '/workspace/studio',
  '/billing': '/workspace/billing',
  '/ops': '/workspace/ops',
  '/message-tasks': '/workspace/ops/messages',
  '/tags': '/workspace/ops/tags',
  '/configs': '/workspace/ops/configs',
  '/admin/plans': '/workspace/admin/plans',
  '/admin/analytics': '/workspace/admin/analytics',
}

router.beforeEach(async (to, from, next) => {
  const canonicalPath = canonicalPathMap[to.path]
  if (canonicalPath && canonicalPath !== to.path) {
    return next({
      path: canonicalPath,
      query: to.query,
      hash: to.hash,
      replace: true,
    })
  }

  const token = localStorage.getItem('token')
  if (to.path === '/login' && token) {
    return next((to.query.redirect as string) || '/workspace/content')
  }

  // 不需要认证的路由直接放行
  if (!to.meta.requiresAuth) {
    return next()
  }

  // 未登录则跳转登录页
  if (!token) {
    return next({
      path: '/login',
      query: {
        redirect: to.fullPath, // 保存目标路由用于登录后跳转
        error: 'unauthorized',
      }
    })
  }

  // 已登录状态，验证token有效性
  try {
    // 确保从正确路径导入verifyToken
    const { verifyToken, getCurrentUser } = await import('@/api/auth')
    await verifyToken()

    const runtime = await loadRuntimeSettings()
    if (runtime?.is_all_free && to.meta.hideInAllFree) {
      return next({
        path: '/workspace/content',
        query: {
          notice: 'billing_hidden',
          target: to.path,
        },
      })
    }

    const requiredPermissions = (to.meta.permissions || []) as string[]
    if (requiredPermissions.length > 0) {
      const user = await getCurrentUser()
      const role = user?.role || ''
      // 当前版本保持与原有行为一致：仅对 admin 进行硬拦截，
      // 其余细粒度权限由后端接口返回控制。
      if (requiredPermissions.includes('admin') && role !== 'admin') {
        return next({
          path: '/workspace/content',
          query: {
            notice: 'forbidden',
            target: to.path,
          },
        })
      }
    }
    next()
  } catch (error) {
    console.error('Token验证失败:', error)
    // token无效时清除并跳转登录
    localStorage.removeItem('token')
    next({
      path: '/login',
      query: { 
        redirect: to.fullPath,
        error: 'session_expired'
      }
    })
  }
})

export default router
