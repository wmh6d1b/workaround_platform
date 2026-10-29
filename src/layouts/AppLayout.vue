<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { can, ensureOptions, isInitializationProject, logout, refreshIdentity, refreshPermissions, selectProject, store } from '../store'
import { api, errorMessage } from '../api'
import { firstSystemPath, hasSystemAccess as checkSystemAccess } from '../permissions'

const route = useRoute()
const router = useRouter()
const activeMenu = computed(() => route.path.startsWith('/build') ? route.path : route.path.startsWith('/wkd') ? '/workbench' : route.path)
const breadcrumb = computed(() => route.path.startsWith('/build') ? ['构建 / 发布', route.meta.title as string] : [route.meta.title as string])
const hasSystemAccess = computed(checkSystemAccess)
const versionOptions = computed(() => store.options.versions.filter(item => item.project_id === store.projectId))

async function signOut() {
  try { if (!store.demoMode) await api.post('/auth/logout') } catch { /* 本地令牌仍需清除 */ }
  logout()
  router.replace('/login')
}
function unauthorized() {
  logout()
  router.replace('/login')
  ElMessage.warning('登录已过期，请重新登录')
}
function versionChanged(id: string) {
  store.version = store.options.versions.find(item => item.id === id)?.name || ''
}
function guardBusinessRoute() {
  if (isInitializationProject.value && ['workbench', 'wkd-new', 'wkd-detail', 'debug-build', 'release-build'].includes(String(route.name))) {
    ElMessage.info('用户初始化项目不承载实际业务，已返回首页')
    void router.replace('/')
  }
}
watch(isInitializationProject, guardBusinessRoute)

const contextReady = ref(false)
onMounted(async () => {
  window.addEventListener('wmp:unauthorized', unauthorized)
  try {
    await refreshIdentity()
    await ensureOptions()
    guardBusinessRoute()
    await refreshPermissions()
    contextReady.value = true
  } catch (error) { ElMessage.error(errorMessage(error, '项目上下文加载失败')) }
})
onBeforeUnmount(() => window.removeEventListener('wmp:unauthorized', unauthorized))
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-is-collapsed': store.sidebarCollapsed }">
    <aside class="app-sidebar">
      <router-link to="/" class="brand"><div class="brand-mark"><span>W</span></div><div v-show="!store.sidebarCollapsed" class="brand-copy"><strong>WMP</strong><small>规避措施管理平台</small></div></router-link>
      <div class="sidebar-caption" v-show="!store.sidebarCollapsed">工作空间</div>
      <el-menu :default-active="activeMenu" :collapse="store.sidebarCollapsed" :collapse-transition="false" menu-trigger="click" router class="sidebar-menu">
        <el-menu-item v-if="can('home.view')" index="/"><el-icon><HomeFilled /></el-icon><template #title>首页</template></el-menu-item>
        <el-menu-item v-if="can('wkd.view') && !isInitializationProject" index="/workbench"><el-icon><Grid /></el-icon><template #title>工作台</template></el-menu-item>
        <el-sub-menu v-if="!store.sidebarCollapsed && !isInitializationProject && (can('build.debug.view') || can('build.release.view'))" index="/build"><template #title><el-icon><Box /></el-icon><span>构建 / 发布</span></template><el-menu-item v-if="can('build.debug.view')" index="/build/debug">调试构建</el-menu-item><el-menu-item v-if="can('build.release.view')" index="/build/release">正式构建</el-menu-item></el-sub-menu>
        <el-menu-item v-else-if="!isInitializationProject && (can('build.debug.view') || can('build.release.view'))" :index="can('build.debug.view') ? '/build/debug' : '/build/release'"><el-icon><Box /></el-icon><template #title>构建 / 发布</template></el-menu-item>
        <el-menu-item index="/statistics"><el-icon><DataAnalysis /></el-icon><template #title>数据统计</template></el-menu-item>
        <el-menu-item v-if="hasSystemAccess" :index="firstSystemPath()"><el-icon><Setting /></el-icon><template #title>系统管理</template></el-menu-item>
      </el-menu>
      <div class="sidebar-bottom"><button class="collapse-button" @click="store.sidebarCollapsed = !store.sidebarCollapsed" :title="store.sidebarCollapsed ? '展开导航' : '收起导航'"><el-icon><Expand v-if="store.sidebarCollapsed" /><Fold v-else /></el-icon><span v-show="!store.sidebarCollapsed">收起导航</span></button></div>
    </aside>

    <div class="app-body">
      <header class="topbar">
        <div class="topbar-context"><span class="context-label">当前上下文</span><el-select :model-value="store.projectId" class="global-select project-select" aria-label="选择项目" filterable :loading="store.optionsLoading" @change="selectProject"><el-option v-for="item in store.options.projects" :key="item.id" :label="item.name" :value="item.id" /></el-select><span class="context-divider" /><el-select v-model="store.versionId" class="global-select version-select" aria-label="选择版本" filterable @change="versionChanged"><el-option v-for="item in versionOptions" :key="item.id" :label="item.number || item.name" :value="item.id" /></el-select></div>
        <div class="topbar-right">
          <span class="topbar-separator" />
          <el-dropdown trigger="click" @command="signOut"><button class="user-trigger"><el-avatar :size="34" class="user-avatar">{{ store.session?.username.slice(0, 1) }}</el-avatar><span class="user-meta"><strong>{{ store.session?.username }}</strong><small>{{ store.session?.role }}</small></span><el-icon class="user-chevron"><ArrowDown /></el-icon></button><template #dropdown><el-dropdown-menu><div class="user-dropdown-head"><strong>{{ store.session?.username }}</strong><span>工号 {{ store.session?.employeeId }}</span></div><el-dropdown-item divided command="logout"><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
        </div>
      </header>
      <main class="main-content"><div class="breadcrumb-row"><span>WMP</span><template v-for="item in breadcrumb" :key="item"><el-icon><ArrowRight /></el-icon><strong>{{ item }}</strong></template></div><div v-if="!contextReady" v-loading="true" style="min-height:240px" /><router-view v-else v-slot="{ Component }"><transition name="page" mode="out-in"><component :is="Component" /></transition></router-view></main>
    </div>
  </div>
</template>

<style scoped>
.notification-panel>div:first-child { display:flex; align-items:center; justify-content:space-between; }.notification-panel>div:first-child>strong { font-size:13px; }
</style>
