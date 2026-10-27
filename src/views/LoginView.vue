<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../store'
import type { Session } from '../types'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { api, ApiError, errorMessage } from '../api'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const oauthLoading = ref(false)
const form = reactive({ username: 'admin', password: 'wmp2026', role: '系统管理员' as Session['role'], remember: true })

async function submit() {
  if (!form.username || !form.password) return ElMessage.warning('请输入账号和密码')
  loading.value = true
  try {
    const result = await api.post<{ access_token: string; permissions: string[]; user: { id: string; username: string; name: string; employee_id: string; is_superuser: boolean } }>('/auth/login', { username: form.username, password: form.password })
    login({ id: result.user.id, username: result.user.username, name: result.user.name, employeeId: result.user.employee_id, role: result.user.is_superuser ? '系统管理员' : '项目成员', isSuperuser: result.user.is_superuser, permissions: result.permissions, demo: false }, result.access_token)
    router.replace(String(route.query.redirect || '/'))
  } catch (error) {
    if (error instanceof ApiError && ![404, 502, 503, 504].includes(error.status)) ElMessage.error(error.message)
    else {
      login({ id: form.username === 'admin' ? 'demo-admin' : `demo-${form.username}`, username: form.username, name: form.username === 'admin' ? '张明' : form.username, employeeId: 'E1024', role: form.role, isSuperuser: form.role === '系统管理员', demo: true })
      ElMessage.info('后端暂不可用，已进入 Demo 模式')
      router.replace(String(route.query.redirect || '/'))
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

async function forgotPassword() {
  try {
    const result = await api.post<{ message: string }>('/auth/password/forgot')
    ElMessage.info(result.message)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) ElMessage.info('Demo 模式：本地管理员密码请联系系统管理员重置')
    else ElMessage.error(errorMessage(error, '无法获取密码重置说明'))
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-brand-panel">
      <div class="login-brand"><div class="brand-mark"><span>W</span></div><strong>WMP</strong></div>
      <div class="login-story">
        <span class="story-kicker">WORKAROUND MANAGEMENT</span>
        <h1>让每一项临时措施，<br />都有迹可循。</h1>
        <p>从登记、验证到审核通过与禁用，为工业软件提供<br />清晰、可靠、可审计的规避措施全生命周期管理。</p>
        <div class="story-flow">
          <div><span>01</span><strong>登记</strong><small>标准化 WKD</small></div><i />
          <div><span>02</span><strong>验证</strong><small>自验证与审核</small></div><i />
          <div><span>03</span><strong>交付</strong><small>可追溯构建</small></div>
        </div>
      </div>
      <div class="login-brand-footer"><span class="release-dot" /> 为工程团队而生 <span>·</span> WMP v1.4</div>
      <div class="brand-orbit orbit-one" /><div class="brand-orbit orbit-two" />
    </section>
    <section class="login-form-panel">
      <div class="login-form-wrap">
        <div class="mobile-login-brand"><div class="brand-mark"><span>W</span></div><strong>WMP</strong></div>
        <span class="login-welcome">欢迎回来</span>
        <h2>登录您的工作空间</h2>
        <p class="login-subtitle">使用调试账号继续，或通过企业身份认证登录</p>
        <el-form label-position="top" @submit.prevent="submit" class="login-form">
          <el-form-item label="账号"><el-input v-model="form.username" size="large" placeholder="请输入用户名或工号" :prefix-icon="User" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" size="large" type="password" show-password placeholder="请输入密码" :prefix-icon="Lock" /></el-form-item>
          <el-form-item label="调试角色"><el-select v-model="form.role" size="large"><el-option v-for="role in ['开发人员','软件经理','项目管理员','系统管理员']" :key="role" :label="role" :value="role" /></el-select></el-form-item>
          <div class="login-options"><el-checkbox v-model="form.remember">记住登录状态</el-checkbox><button type="button" @click="forgotPassword">忘记密码？</button></div>
          <el-button type="primary" size="large" native-type="submit" :loading="loading" class="login-submit">进入平台<el-icon class="el-icon--right"><Right /></el-icon></el-button>
        </el-form>
        <div class="login-divider"><span>或</span></div>
        <el-button size="large" class="oauth-button" :loading="oauthLoading" @click="oauthLogin"><el-icon><Connection /></el-icon>企业 OAuth 登录</el-button>
        <p class="login-help">调试环境账号已预填，可直接登录</p>
      </div>
      <footer>© 2026 WMP · 内部工程系统 <span>隐私与安全</span></footer>
    </section>
  </div>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(500px, 1.04fr) minmax(560px, .96fr); background: #fff; }
.login-brand-panel { background: #111b31; color: #fff; position: relative; overflow: hidden; padding: 40px 56px; display: flex; flex-direction: column; }
.login-brand { display: flex; align-items: center; gap: 13px; position: relative; z-index: 1; }
.login-brand strong { font-size: 21px; letter-spacing: 2px; }
.login-story { margin: auto 0; position: relative; z-index: 1; padding: 55px 0; }
.story-kicker { font-size: 10px; letter-spacing: 2.6px; color: #7795ff; font-weight: 600; }
.login-story h1 { font-size: clamp(36px, 3.4vw, 52px); line-height: 1.38; letter-spacing: -2px; font-weight: 600; margin: 22px 0; }
.login-story > p { color: #9aa8bf; font-size: 14px; line-height: 2; margin: 0; }
.story-flow { display: flex; align-items: center; margin-top: 62px; max-width: 500px; }
.story-flow > div { display: flex; flex-direction: column; gap: 5px; }
.story-flow span { font-size: 10px; color: #6488ff; }
.story-flow strong { font-size: 14px; font-weight: 500; }
.story-flow small { font-size: 10px; color: #708098; }
.story-flow > i { flex: 1; min-width: 25px; height: 1px; background: #2b3952; margin: 0 22px; }
.login-brand-footer { display: flex; gap: 10px; align-items: center; color: #77869f; font-size: 11px; position: relative; z-index: 1; }
.brand-orbit { position: absolute; border: 1px solid rgba(112,142,255,.09); border-radius: 50%; }
.orbit-one { width: 600px; height: 600px; right: -320px; top: -190px; box-shadow: 0 0 0 100px rgba(71,100,200,.025), 0 0 0 200px rgba(71,100,200,.018); }
.orbit-two { width: 300px; height: 300px; left: -210px; bottom: -150px; }
.login-form-panel { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 35px; position: relative; }
.login-form-wrap { width: 370px; margin: auto; }
.login-welcome { font-size: 12px; color: #315efb; font-weight: 600; }
.login-form-wrap h2 { font-size: 26px; margin: 9px 0; letter-spacing: -.5px; }
.login-subtitle { font-size: 12px; color: #8a94a6; margin: 0 0 32px; }
.login-form :deep(.el-form-item) { margin-bottom: 19px; }
.login-form :deep(.el-form-item__label) { font-size: 12px; color: #475467; padding-bottom: 7px; }
.login-form :deep(.el-input__wrapper), .login-form :deep(.el-select__wrapper) { min-height: 43px; }
.login-form :deep(.el-select) { width: 100%; }
.login-options { display: flex; align-items: center; justify-content: space-between; margin: -2px 0 22px; }
.login-options :deep(.el-checkbox__label) { font-size: 11px; color: #667085; }
.login-options button { border: 0; background: none; color: #315efb; font-size: 11px; }
.login-submit, .oauth-button { width: 100%; height: 44px; margin: 0; }
.login-divider { height: 42px; display: flex; align-items: center; color: #a3abba; font-size: 10px; }
.login-divider::before, .login-divider::after { content: ''; flex: 1; height: 1px; background: #edf0f4; }
.login-divider span { margin: 0 14px; }
.oauth-button { border-color: #e1e5ec; color: #475467; }
.login-help { text-align: center; color: #a0a8b7; font-size: 10px; margin-top: 18px; }
.login-form-panel footer { width: 100%; display: flex; justify-content: space-between; font-size: 10px; color: #a0a8b7; }
.mobile-login-brand { display: none; }
</style>
