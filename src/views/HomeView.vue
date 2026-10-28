<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { can, isInitializationProject, store } from '../store'
import { firstSystemPath, firstSystemPermission } from '../permissions'
import { artifacts, wkdList } from '../data/mock'
import { api, displayNumber, errorMessage, normalizeWkd, queryString } from '../api'
import type { Wkd } from '../types'
import StatusTag from '../components/StatusTag.vue'

const router = useRouter()
const loading = ref(false)
const summary = ref({ total: 0, approved: 0, pending: 0, monthly_new: 0, monthly_builds: 0 })
const recent = ref<Wkd[]>([])
const todos = ref<Wkd[]>([])
const greeting = computed(() => dayjs().hour() < 12 ? '上午好' : dayjs().hour() < 18 ? '下午好' : '晚上好')
const dateLabel = computed(() => dayjs().format('dddd · DD MMMM').toUpperCase())
const modules = computed(() => [
  { name: '工作台', en: 'WORKBENCH', desc: '检索、登记并跟进 WKD 全流程', icon: 'Grid', path: '/workbench', tone: 'blue', permission: 'wkd.view' },
  { name: '构建 / 发布', en: 'BUILD & RELEASE', desc: '调试构建与正式规避包交付', icon: 'Box', path: can('build.debug.view') ? '/build/debug' : '/build/release', tone: 'violet', permission: can('build.debug.view') ? 'build.debug.view' : 'build.release.view' },
  { name: '数据统计', en: 'ANALYTICS', desc: '多维分析规避措施执行数据', icon: 'DataAnalysis', path: '/statistics', tone: 'green', permission: '' },
  { name: '系统管理', en: 'ADMINISTRATION', desc: '项目内业务、成员与角色权限管理', icon: 'Setting', path: firstSystemPath(), tone: 'orange', permission: firstSystemPermission() },
].filter(item => (!item.permission || can(item.permission)) && (!isInitializationProject.value || !['工作台', '构建 / 发布'].includes(item.name))))

async function load() {
  loading.value = true
  try {
    if (store.demoMode) {
      const rows = wkdList.filter(item => item.projectId === store.projectId)
      summary.value = { total: rows.length, approved: rows.filter(item => item.status === 'APPROVED').length, pending: rows.filter(item => ['VERIFY','REVIEW','DISABLE_CONFIRM'].includes(item.status)).length, monthly_new: rows.filter(item => item.createdAt.slice(0, 7) === dayjs().format('YYYY-MM')).length, monthly_builds: artifacts.filter(item => item.project_id === store.projectId && item.created_at.slice(0, 7) === dayjs().format('YYYY-MM')).length }
      recent.value = [...rows].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, 5)
      todos.value = rows.filter(item => ['VERIFY','REVIEW','DISABLE_CONFIRM'].includes(item.status)).slice(0, 5)
    } else {
      const result = await api.get<{ total: number; approved: number; pending: number; monthly_new: number; monthly_builds: number; recent: Record<string, unknown>[]; todos: Record<string, unknown>[] }>(`/dashboard/summary${queryString({ project_id: store.projectId })}`)
      summary.value = { total: result.total, approved: result.approved, pending: result.pending, monthly_new: result.monthly_new, monthly_builds: result.monthly_builds }
      recent.value = result.recent.map(normalizeWkd)
      todos.value = result.todos.map(normalizeWkd)
    }
  } catch (error) { ElMessage.error(errorMessage(error, '首页数据加载失败')) }
  finally { loading.value = false }
}
onMounted(load)
watch(() => store.projectId, load)
</script>

<template>
  <div v-loading="loading" class="home-page">
    <section class="welcome-section"><div><span class="welcome-overline">{{ dateLabel }}</span><h1>{{ greeting }}，{{ store.session?.username }}</h1><p>当前项目有 <strong>{{ summary.pending }} 项</strong> 规避措施等待处理，保持每一个交付清晰可控。</p></div><el-button v-if="can('wkd.create') && !isInitializationProject" type="primary" @click="router.push('/wkd/new')"><el-icon><Plus /></el-icon>登记 WKD</el-button></section>
    <el-alert v-if="isInitializationProject" title="当前为用户初始化项目，仅用于账号落地。请切换到真实项目处理 WKD 和构建；全局项目、成员与角色管理仍可使用。" type="info" :closable="false" show-icon class="initialization-note" />
    <section class="home-metrics metric-grid">
      <div class="metric-card"><div class="metric-card-top"><span>规避措施总数</span><span class="metric-icon"><el-icon><Files /></el-icon></span></div><div class="metric-card-value"><strong>{{ summary.total }}</strong><small>当前项目</small></div><div class="metric-card-note">本月新增 {{ summary.monthly_new }} 项</div></div>
      <div class="metric-card"><div class="metric-card-top"><span>当前审核通过</span><span class="metric-icon green"><el-icon><CircleCheck /></el-icon></span></div><div class="metric-card-value"><strong>{{ summary.approved }}</strong><small>可参与构建</small></div><div class="metric-card-note">仅统计当前有效状态</div></div>
      <div class="metric-card"><div class="metric-card-top"><span>待处理</span><span class="metric-icon orange"><el-icon><Clock /></el-icon></span></div><div class="metric-card-value"><strong>{{ summary.pending }}</strong><small class="warning-text">需关注</small></div><div class="metric-card-note">自验证与软件经理审核</div></div>
      <div class="metric-card"><div class="metric-card-top"><span>本月构建</span><span class="metric-icon violet"><el-icon><Box /></el-icon></span></div><div class="metric-card-value"><strong>{{ summary.monthly_builds }}</strong><small>构建制品</small></div><div class="metric-card-note">调试与正式构建合计</div></div>
    </section>

    <section class="module-section"><div class="section-title"><h2>核心工作区</h2><span>选择模块，快速开始工作</span></div><div class="module-grid"><button v-for="module in modules" :key="module.name" class="module-card" @click="router.push(module.path)"><span class="module-icon" :class="module.tone"><el-icon><component :is="module.icon" /></el-icon></span><span class="module-copy"><small>{{ module.en }}</small><strong>{{ module.name }}</strong><span>{{ module.desc }}</span></span><el-icon class="module-arrow"><ArrowRight /></el-icon></button></div></section>

    <section class="home-bottom-grid">
      <div class="surface-card recent-card"><div class="card-header"><div><h3>最近更新</h3><p>当前项目中最新的 WKD 动态</p></div><el-button text type="primary" @click="router.push('/workbench')">查看全部<el-icon><ArrowRight /></el-icon></el-button></div><div class="recent-list"><button v-for="item in recent" :key="item.id" class="recent-item" @click="router.push(`/wkd/${item.id}`)"><span class="recent-symbol"><el-icon><Document /></el-icon></span><span class="recent-main"><strong>{{ item.title }}</strong><small><span class="mono">{{ displayNumber(item) }}</span> · {{ item.machine }} · {{ item.owner }}</small></span><StatusTag :status="item.status" /><span class="recent-time">{{ item.updatedAt.slice(5, 16) }}</span><el-icon class="recent-arrow"><ArrowRight /></el-icon></button><el-empty v-if="!recent.length" description="暂无 WKD 动态" :image-size="60" /></div></div>
      <aside class="surface-card activity-card"><div class="card-header"><div><h3>我的待办</h3><p>当前项目待验证与待审核事项</p></div><span class="todo-total">{{ todos.length }}</span></div><div class="todo-list"><button v-for="item in todos" :key="item.id" class="todo-item" @click="router.push(`/wkd/${item.id}`)"><span class="todo-check" :class="{ urgent: item.status === 'REVIEW' }" /><div><strong>{{ item.title }}</strong><p>{{ displayNumber(item) }} · {{ item.status === 'REVIEW' ? '软件经理审核' : '自验证' }}</p><small>责任人 {{ item.owner }}</small></div></button><el-empty v-if="!todos.length" description="暂无待办" :image-size="60" /></div><button class="todo-all" @click="router.push('/workbench')">进入我的工作台<el-icon><ArrowRight /></el-icon></button></aside>
    </section>
  </div>
</template>

<style scoped>
.welcome-section { display:flex; justify-content:space-between; align-items:center; margin:5px 0 25px; }.welcome-overline { font-size:9px; letter-spacing:1.6px; color:#8e99ab; }.welcome-section h1 { font-size:25px; margin:7px 0 6px; letter-spacing:-.5px; }.welcome-section p { font-size:12px; color:#7c8798; margin:0; }.welcome-section p strong { color:#315efb; font-weight:600; }.metric-icon.green { color:#14966b; background:#ebf8f2; }.metric-icon.orange { color:#d27a12; background:#fff5e8; }.metric-icon.violet { color:#7957d5; background:#f3efff; }.warning-text { color:#c67a16 !important; }.section-title { display:flex; align-items:baseline; gap:12px; margin:26px 0 13px; }.section-title h2 { font-size:14px; margin:0; }.section-title span { color:#98a2b3; font-size:10px; }.module-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:15px; }.module-card { position:relative; background:#fff; border:1px solid var(--line); border-radius:11px; text-align:left; padding:22px 18px; display:flex; gap:13px; min-height:135px; transition:border-color .2s,transform .2s,box-shadow .2s; cursor:pointer; }.module-card:hover { border-color:#bdcaff; transform:translateY(-2px); box-shadow:0 8px 24px rgba(33,48,85,.06); }.module-icon { width:39px; height:39px; flex-shrink:0; display:grid; place-items:center; border-radius:10px; font-size:19px; background:#edf0ff; color:#315efb; }.module-icon.violet { color:#7957d5; background:#f3efff; }.module-icon.green { color:#14966b; background:#ebf8f2; }.module-icon.orange { color:#d27a12; background:#fff5e8; }.module-copy { display:flex; flex-direction:column; }.module-copy small { font-size:8px; letter-spacing:1px; color:#a0a8b7; margin:1px 0 5px; }.module-copy strong { font-size:14px; font-weight:600; }.module-copy>span { color:#7f8999; font-size:10px; line-height:1.7; margin-top:10px; white-space:nowrap; }.module-arrow { position:absolute; right:15px; top:22px; color:#c2c9d4; font-size:13px; }.module-card:hover .module-arrow { color:#315efb; }.home-bottom-grid { display:grid; grid-template-columns:minmax(0,1.8fr) minmax(290px,.8fr); gap:16px; margin-top:24px; }.recent-list { padding:3px 20px 8px; }.recent-item { width:100%; display:flex; align-items:center; gap:12px; background:transparent; border:0; border-bottom:1px solid #f0f2f5; text-align:left; padding:12px 0; cursor:pointer; }.recent-item:last-child { border-bottom:0; }.recent-symbol { width:30px; height:30px; display:grid; place-items:center; color:#7b8bab; background:#f5f7fb; border-radius:7px; }.recent-main { flex:1; display:flex; flex-direction:column; gap:4px; min-width:0; }.recent-main strong { font-size:11px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.recent-main small { font-size:9px; color:#98a2b3; }.recent-time { font-size:9px; color:#a0a8b7; }.recent-arrow { color:#c2c9d4; }.recent-item:hover .recent-main strong,.recent-item:hover .recent-arrow { color:#315efb; }.todo-total { font-size:10px; min-width:22px; height:22px; border-radius:6px; display:grid; place-items:center; background:#edf0ff; color:#315efb; }.todo-list { padding:8px 20px; }.todo-item { display:flex; gap:11px; padding:12px 0; width:100%; text-align:left; border:0; background:transparent; cursor:pointer; }.todo-check { width:7px; height:7px; margin-top:5px; background:#315efb; box-shadow:0 0 0 4px #edf0ff; border-radius:50%; flex-shrink:0; }.todo-check.urgent { background:#f79009; box-shadow:0 0 0 4px #fff5e8; }.todo-item strong { font-size:11px; font-weight:500; }.todo-item p { font-size:9px; color:#8b95a5; margin:5px 0; }.todo-item small { color:#b0b7c3; font-size:9px; }.todo-all { border:0; border-top:1px solid var(--line); background:#fafbfc; color:#667085; width:100%; height:40px; border-radius:0 0 11px 11px; font-size:10px; display:flex; align-items:center; justify-content:center; gap:8px; cursor:pointer; }.todo-all:hover { color:#315efb; }
.initialization-note { margin:-10px 0 20px; }
@media(max-width:1100px){.module-grid{grid-template-columns:repeat(2,1fr)}.home-bottom-grid{grid-template-columns:1fr}}
</style>
