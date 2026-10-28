<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demoLoginEnabled, login } from '../store'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { api, ApiError, errorMessage } from '../api'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const oauthLoading = ref(false)
const form = reactive({ username: '', password: '' })

async function submit() {
  if (!form.username.trim() || !form.password) return ElMessage.warning('请输入账号和密码')
  loading.value = true
  try {
    const result = await api.post<{ access_token: string; permissions: string[]; user: { id: string; username: string; employee_id: string; department?: string; is_superuser: boolean } }>('/auth/login', { username: form.username.trim(), password: form.password })
    login({ id: result.user.id, username: result.user.username, employeeId: result.user.employee_id, department: result.user.department, role: result.user.is_superuser ? '系统管理员' : '项目成员', isSuperuser: result.user.is_superuser, permissions: result.permissions, demo: false }, result.access_token)
    router.replace(String(route.query.redirect || '/'))
  } catch (error) {
    const backendUnavailable = !(error instanceof ApiError) || [404, 502, 503, 504].includes(error.status)
    if (demoLoginEnabled && backendUnavailable) {
      login({ id: 'demo-admin', username: 'Demo 管理员', employeeId: 'DEMO', role: '系统管理员', isSuperuser: true, demo: true })
      ElMessage.info('后端暂不可用，已进入显式启用的 Demo 模式')
      router.replace(String(route.query.redirect || '/'))
    } else {
      ElMessage.error(errorMessage(error, '登录失败，请检查账号、密码或服务状态'))
    }
  } finally {
    loading.value = false
  }
}

async function oauthLogin() {
  oauthLoading.value = true
  try {
    const result = await api.post<{ authorization_url: string }>('/auth/oauth/login')
    sessionStorage.setItem('wmp-oauth-redirect', String(route.query.redirect || '/'))
    window.location.assign(result.authorization_url)
  } catch (error) {
    ElMessage.error(errorMessage(error, '企业 OAuth 暂时不可用'))
    oauthLoading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-brand-panel">
      <div class="login-brand">
        <div class="brand-mark"><span>W</span></div>
        <div class="login-brand-copy">
          <h1>规避措施管理平台</h1>
          <p>Workaround Management Platform</p>
        </div>
      </div>
      <div class="brand-orbit orbit-one" /><div class="brand-orbit orbit-two" />
    </section>
    <section class="login-form-panel">
      <div class="login-form-wrap">
        <div class="mobile-login-brand"><div class="brand-mark"><span>W</span></div><strong>WMP</strong></div>
        <span class="login-welcome">欢迎回来</span>
        <h2>登录您的工作空间</h2>
        <p class="login-subtitle">使用本地账号，或通过企业身份认证登录</p>
        <el-form label-position="top" @submit.prevent="submit" class="login-form">
          <el-form-item label="用户名或工号"><el-input v-model="form.username" size="large" autocomplete="username" placeholder="请输入用户名或工号" :prefix-icon="User" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" size="large" type="password" show-password autocomplete="current-password" placeholder="请输入密码" :prefix-icon="Lock" /></el-form-item>
          <el-button type="primary" size="large" native-type="submit" :loading="loading" class="login-submit">进入平台<el-icon class="el-icon--right"><Right /></el-icon></el-button>
        </el-form>
        <div class="login-divider"><span>或</span></div>
        <el-button size="large" class="oauth-button" :loading="oauthLoading" @click="oauthLogin"><el-icon><Connection /></el-icon>企业 OAuth 登录</el-button>
        <p v-if="demoLoginEnabled" class="login-help">当前为显式启用的开发 Demo 模式</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(500px, 1.04fr) minmax(560px, .96fr); background: #fff; }
.login-brand-panel { background: #111b31; color: #fff; position: relative; overflow: hidden; padding: 56px; display: flex; align-items: center; }
.login-brand { display: flex; align-items: center; gap: 22px; position: relative; z-index: 1; }
#app .login-brand .brand-mark { width: 54px; height: 54px; flex: none; border-radius: 14px; font-size: 25px; }
#app .login-brand-copy h1 { margin: 0; color: #fff; font-size: clamp(28px, 2.6vw, 38px); font-weight: 600; line-height: 1.4; letter-spacing: 1px; }
#app .login-brand-copy p { margin: 10px 0 0; color: #8fa2c2; font-size: 13px; line-height: 1.5; letter-spacing: 1.5px; }
.brand-orbit { position: absolute; border: 1px solid rgba(112,142,255,.09); border-radius: 50%; }
.orbit-one { width: 600px; height: 600px; right: -320px; top: -190px; box-shadow: 0 0 0 100px rgba(71,100,200,.025), 0 0 0 200px rgba(71,100,200,.018); }
.orbit-two { width: 300px; height: 300px; left: -210px; bottom: -150px; }
.login-form-panel { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 35px; position: relative; }
.login-form-wrap { width: 370px; margin: auto; }
.login-welcome { font-size: 12px; color: #315efb; font-weight: 600; }
#app .login-form-wrap h2 { font-size: 26px; margin: 9px 0; letter-spacing: -.5px; }
.login-subtitle { font-size: 12px; color: #8a94a6; margin: 0 0 32px; }
.login-form :deep(.el-form-item) { margin-bottom: 19px; }
.login-form :deep(.el-form-item__label) { font-size: 12px; color: #475467; padding-bottom: 7px; }
.login-form :deep(.el-input__wrapper), .login-form :deep(.el-select__wrapper) { min-height: 43px; }
.login-form :deep(.el-select) { width: 100%; }
.login-submit, .oauth-button { width: 100%; height: 44px; margin: 0; }
.login-divider { height: 42px; display: flex; align-items: center; color: #a3abba; font-size: 10px; }
.login-divider::before, .login-divider::after { content: ''; flex: 1; height: 1px; background: #edf0f4; }
.login-divider span { margin: 0 14px; }
.oauth-button { border-color: #e1e5ec; color: #475467; }
.login-help { text-align: center; color: #a0a8b7; font-size: 10px; margin-top: 18px; }
.mobile-login-brand { display: none; }
</style>
