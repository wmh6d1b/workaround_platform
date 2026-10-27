import { createRouter, createWebHistory } from 'vue-router'
import { can, store } from './store'
import { ElMessage } from 'element-plus'
import AppLayout from './layouts/AppLayout.vue'
import LoginView from './views/LoginView.vue'
import OAuthCallbackView from './views/OAuthCallbackView.vue'
import HomeView from './views/HomeView.vue'
import WorkbenchView from './views/WorkbenchView.vue'
import DebugBuildView from './views/DebugBuildView.vue'
import ReleaseBuildView from './views/ReleaseBuildView.vue'
import StatisticsView from './views/StatisticsView.vue'
import SystemView from './views/SystemView.vue'
import WkdDetailView from './views/WkdDetailView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/oauth/callback', name: 'oauth-callback', component: OAuthCallbackView, meta: { public: true } },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', name: 'home', component: HomeView, meta: { title: '首页', permission: 'home.view' } },
        { path: 'workbench', name: 'workbench', component: WorkbenchView, meta: { title: '工作台', permission: 'wkd.view' } },
        { path: 'wkd/new', name: 'wkd-new', component: WkdDetailView, meta: { title: '新建 WKD', permission: 'wkd.create' } },
        { path: 'wkd/:id', name: 'wkd-detail', component: WkdDetailView, meta: { title: 'WKD 详情', permission: 'wkd.view' } },
        { path: 'build/debug', name: 'debug-build', component: DebugBuildView, meta: { title: '调试构建', permission: 'build.debug.view' } },
        { path: 'build/release', name: 'release-build', component: ReleaseBuildView, meta: { title: '正式构建', permission: 'build.release.view' } },
        { path: 'statistics', name: 'statistics', component: StatisticsView, meta: { title: '数据统计', permission: 'stats.view' } },
        { path: 'system/:tab?', name: 'system', component: SystemView, meta: { title: '系统管理' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  if (!to.meta.public && !store.session) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && store.session) return { name: 'home' }
  let permission = to.meta.permission as string | undefined
  if (to.name === 'system') {
    const tab = String(to.params.tab || 'business')
    permission = tab === 'members' ? 'system.member.view' : tab === 'roles' ? 'system.role.view' : 'system.business.view'
  }
  if (permission && !can(permission)) {
    ElMessage.warning('当前项目角色没有此模块的访问权限')
    return to.name === 'home' ? true : { name: 'home' }
  }
})

export default router
