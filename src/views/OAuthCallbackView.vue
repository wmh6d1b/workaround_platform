<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errorMessage } from '../api'
import { login } from '../store'

const route = useRoute()
const router = useRouter()
const error = ref('')

function safeRedirect(value: string | null) {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/'
}

onMounted(async () => {
  const providerError = String(route.query.error_description || route.query.error || '')
  if (providerError) {
    error.value = providerError
    return
  }
  const code = String(route.query.code || '')
  const state = String(route.query.state || '')
  if (!code || !state) {
    error.value = 'OAuth 回调缺少 code 或 state，请重新登录'
    return
  }
  try {
    const result = await api.post<{ access_token: string; permissions: string[]; user: { id: string; username: string; name: string; employee_id: string; is_superuser: boolean } }>('/auth/oauth/callback', { code, state })
    login({ id: result.user.id, username: result.user.username, name: result.user.name, employeeId: result.user.employee_id, role: result.user.is_superuser ? '系统管理员' : '项目成员', isSuperuser: result.user.is_superuser, permissions: result.permissions, demo: false }, result.access_token)
    const redirect = safeRedirect(sessionStorage.getItem('wmp-oauth-redirect'))
    sessionStorage.removeItem('wmp-oauth-redirect')
    ElMessage.success(`欢迎回来，${result.user.name}`)
    await router.replace(redirect)
  } catch (reason) {
    error.value = errorMessage(reason, '企业 OAuth 登录失败，请重试')
  }
})
</script>

<template>
  <main class="oauth-callback">
    <section class="callback-card">
      <div class="brand-mark">W</div>
      <template v-if="!error">
        <span class="loading-ring" />
        <h1>正在完成企业身份认证</h1>
        <p>正在校验授权信息并加载你的项目权限，请稍候。</p>
      </template>
      <template v-else>
        <h1>暂时无法登录</h1>
        <p class="error-text">{{ error }}</p>
        <el-button type="primary" @click="router.replace('/login')">返回登录页</el-button>
      </template>
    </section>
  </main>
</template>

<style scoped>
.oauth-callback { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f5f7fb; }
.callback-card { width: min(440px, 100%); padding: 42px; text-align: center; background: #fff; border: 1px solid #e8ecf3; border-radius: 18px; box-shadow: 0 18px 50px rgba(25, 42, 70, .08); }
.brand-mark { width: 42px; height: 42px; display: grid; place-items: center; margin: 0 auto 24px; border-radius: 12px; color: #fff; background: #315efb; font-weight: 700; }
h1 { margin: 20px 0 10px; color: #172033; font-size: 21px; }
p { margin: 0 0 24px; color: #7a8496; font-size: 13px; line-height: 1.8; }
.error-text { color: #c43d4b; overflow-wrap: anywhere; }
.loading-ring { display: block; width: 28px; height: 28px; margin: 0 auto; border: 3px solid #e4eaff; border-top-color: #315efb; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
