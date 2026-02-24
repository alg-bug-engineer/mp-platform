<template>
  <div class="edit-user">
    <a-page-header
      title="修改个人信息"
      subtitle="更新您的账户信息"
      :show-back="true"
      @back="goBack"
    />
    
    <a-card>
      <a-form
        :model="form"
        :rules="rules"
        @submit="handleSubmit"
        layout="vertical"
      >
        <a-form-item label="头像">
          <a-upload
            :custom-request="handleUploadChange"
            :file-list="fileList"
            :show-file-list="false"
            accept="image/*"
            :limit="1"
            :max-size="2048"
            @exceed="handleExceed"
            @error="handleUploadError"
          >
            <template #upload-button>
              <div class="avatar-upload">
                <a-avatar :size="80">
                  <img 
                    v-if="form.avatar" 
                    :src="form.avatar" 
                    alt="avatar"
                    @error="handleImageError"
                  >
                  <icon-user v-else />
                </a-avatar>
                <div class="upload-mask">
                  <icon-edit />
                </div>
              </div>
            </template>
          </a-upload>
        </a-form-item>
        
        <a-form-item label="用户名" field="username">
          <a-input
            v-model="form.username"
            placeholder="请输入用户名"
            allow-clear
          >
            <template #prefix><icon-user /></template>
          </a-input>
        </a-form-item>
        
        <a-form-item label="昵称" field="nickname">
          <a-input
            v-model="form.nickname"
            placeholder="请输入昵称"
            allow-clear
          >
            <template #prefix><icon-user /></template>
          </a-input>
        </a-form-item>
        
        <a-form-item label="邮箱" field="email">
          <a-input
            v-model="form.email"
            placeholder="请输入邮箱"
            allow-clear
          >
            <template #prefix><icon-email /></template>
          </a-input>
        </a-form-item>

        <a-divider orientation="left">公众号接口配置</a-divider>
        <a-alert style="margin-bottom: 12px;" type="info">
          这里填写公众号 AppID / AppSecret 后，AI 草稿同步会自动读取；未填写时，同步会提示先到个人中心配置。
        </a-alert>
        <a-form-item label="公众号 AppID">
          <a-input
            v-model="form.wechat_app_id"
            placeholder="wx..."
            allow-clear
          />
        </a-form-item>
        <a-form-item label="公众号 AppSecret">
          <a-input-password
            v-model="form.wechat_app_secret"
            placeholder="留空表示不修改"
            allow-clear
          />
          <div class="muted-tip">
            已配置状态：{{ form.wechat_app_secret_set ? '已设置' : '未设置' }}
          </div>
          <a-checkbox v-model="form.clear_wechat_app_secret">清空已保存的 AppSecret</a-checkbox>
        </a-form-item>
        
        <a-form-item>
          <a-space>
            <a-button type="primary" html-type="submit" :loading="loading">
              保存修改
            </a-button>
            <a-button @click="resetForm">重置</a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { getUserInfo, updateUserInfo, uploadAvatar } from '@/api/user'

const router = useRouter()
const loading = ref(false)
const fileList = ref([])

const form = ref({
  username: '',
  nickname: '',
  email: '',
  avatar: '',
  wechat_app_id: '',
  wechat_app_secret: '',
  wechat_app_secret_set: false,
  clear_wechat_app_secret: false,
})

const rules = {
  username: [{ required: true, message: '请输入用户名' }],
  email: [
    { required: true, message: '请输入邮箱' },
    { type: 'email', message: '请输入有效的邮箱地址' }
  ]
}

const handleUploadChange = async (options: any) => {
  const file = options.fileItem?.file || options.file
  
  // 文件类型验证
  if (!file?.type?.startsWith('image/')) {
    Message.error('请选择图片文件 (JPEG/PNG)')
    return
  }

  // 文件大小验证 (2MB)
  if (file.size > 2 * 1024 * 1024) {
    Message.error('图片大小不能超过2MB')
    return
  }

  try {
    const res = await uploadAvatar(file)
    form.value.avatar = res.avatar
  } catch (error) {
    console.error('上传错误:', error)
    Message.error(`上传失败: ${error.response?.data?.message || error.message || '服务器错误'}`)
  } 
  return false
}

const handleExceed = () => {
  Message.warning('只能上传一个头像文件')
}

const handleUploadError = (error: Error) => {
  Message.error(`上传出错: ${error.message || '文件上传失败'}`)
}

const handleImageError = (e: Event) => {
  const img = e.target as HTMLImageElement
  img.src = '/default-avatar.png'
}

const fetchUserInfo = async () => {
  loading.value = true
  try {
    const res = await getUserInfo()
    form.value = {
      username: res.username,
      nickname: res.nickname || res.username,
      email: res.email || '',
      avatar: res.avatar,
      wechat_app_id: res.wechat_app_id || '',
      wechat_app_secret: '',
      wechat_app_secret_set: !!res.wechat_app_secret_set,
      clear_wechat_app_secret: false,
    }
  } catch (error) {
    router.push('/login')
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
    let response=await updateUserInfo(form.value)
    if (response.code === 0){
      Message.success(response?.message || '更新成功')
      form.value.wechat_app_secret = ''
      form.value.clear_wechat_app_secret = false
      await fetchUserInfo()
    }
}

const resetForm = () => {
  fetchUserInfo()
}

const goBack = () => {
  router.go(-1)
}

onMounted(() => {
  fetchUserInfo()
})
</script>

<style scoped>
.edit-user {
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
}

.avatar-upload {
  position: relative;
  width: 80px;
  height: 80px;
  cursor: pointer;
}

.upload-mask {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s;
}

.avatar-upload:hover .upload-mask {
  opacity: 1;
}

.arco-form-item {
  margin-bottom: 20px;
}

.muted-tip {
  color: #8a8a8a;
  font-size: 12px;
  margin-top: 6px;
}
</style>
