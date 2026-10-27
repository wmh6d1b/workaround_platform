<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import WkdTable from '../components/WkdTable.vue'
import { wkdList } from '../data/mock'
import { can, ensureOptions, store } from '../store'
import { api, errorMessage, normalizeWkd, queryString } from '../api'
import type { Wkd } from '../types'
import { emptyWkdFilters, filterWkdRows, hasWkdFilters, stageFilterOptions, statusFilterOptions } from '../utils/wkdFilters'
import type { WkdFilterKey, WkdFilterOptions } from '../utils/wkdFilters'

const router = useRouter()
const activeTab = ref('all')
const search = ref('')
const filters = ref(emptyWkdFilters())
const currentPage = ref(1)
const pageSize = ref(10)
const rows = ref<Wkd[]>([])
const total = ref(0)
const loading = ref(false)
const counts = reactive<Record<string, number>>({ all: 0, pending: 0, created: 0, handled: 0 })
const visibleColumns = ref(['id', 'title', 'machine', 'subsystem', 'owner', 'stage', 'status'])
const columnOptions = [{ key:'id',label:'WKD 编号'},{key:'title',label:'WKD 标题'},{key:'machine',label:'机台'},{key:'subsystem',label:'子系统'},{key:'owner',label:'责任人'},{key:'stage',label:'执行阶段'},{key:'status',label:'工作流状态'},{key:'updatedAt',label:'更新时间'}]
const filterableColumns: WkdFilterKey[] = ['machine', 'subsystem', 'owner', 'stage', 'status']
const filterOptions = computed<WkdFilterOptions>(() => ({
  machine: store.options.machines.filter(item => item.project_id === store.projectId).map(item => ({ value: item.id, label: item.name })),
  subsystem: store.options.subsystems.filter(item => item.project_id === store.projectId).map(item => ({ value: item.id, label: item.name })),
  owner: store.options.users.map(item => ({ value: item.id, label: item.name })),
  stage: stageFilterOptions,
  status: statusFilterOptions,
}))

function demoRows(tab = activeTab.value) {
  const contextualRows = wkdList.filter(item => {
    const matchesTab = tab === 'all' || (tab === 'pending' && ['VERIFY','REVIEW','DISABLE_CONFIRM'].includes(item.status)) || (tab === 'created' && item.owner === store.session?.name) || (tab === 'handled' && item.owner === store.session?.name && item.status !== 'NEW_WKD')
    return item.projectId === store.projectId && item.versionId === store.versionId && matchesTab
  })
  return filterWkdRows(contextualRows, search.value, filters.value)
}

async function load() {
  loading.value = true
  try {
    if (store.demoMode) {
      Object.keys(counts).forEach(key => { counts[key] = demoRows(key).length })
      const filtered = demoRows()
      total.value = filtered.length
      rows.value = filtered.slice((currentPage.value - 1) * pageSize.value, currentPage.value * pageSize.value)
    } else {
      const result = await api.get<{ items: Record<string, unknown>[]; total: number; tab_counts: Record<string, number> }>(`/wkds${queryString({ project_id: store.projectId, version_id: store.versionId, machine_ids: filters.value.machine, subsystem_ids: filters.value.subsystem, owner_ids: filters.value.owner, stages: filters.value.stage, statuses: filters.value.status, q: search.value.trim(), tab: activeTab.value, page: currentPage.value, page_size: pageSize.value })}`)
      rows.value = result.items.map(normalizeWkd)
      total.value = result.total
      Object.assign(counts, result.tab_counts)
    }
  } catch (error) { ElMessage.error(errorMessage(error, 'WKD 列表加载失败')) }
  finally { loading.value = false }
}

async function refresh() {
  await load()
  ElMessage.success('列表已刷新')
}
function resetFilters() { search.value=''; filters.value=emptyWkdFilters(); currentPage.value=1; load() }
function filterChanged() { currentPage.value = 1; load() }
function headerFilterChanged(payload: { key: WkdFilterKey; values: string[] }) {
  filters.value[payload.key] = payload.values
  filterChanged()
}

onMounted(async () => {
  try { await ensureOptions() } catch (error) { ElMessage.error(errorMessage(error, '基础选项加载失败')) }
  await load()
})
watch(() => [store.projectId, store.versionId], () => { filters.value=emptyWkdFilters(); filterChanged() })
watch(activeTab, filterChanged)
watch([currentPage, pageSize], load)
</script>

<template>
  <div>
    <PageHeader title="工作台" description="集中检索与管理规避措施，跟踪每一项 WKD 的处理进度。">
      <el-button :loading="loading" @click="refresh"><el-icon><Refresh /></el-icon>刷新</el-button><el-button v-if="can('wkd.create')" type="primary" @click="router.push('/wkd/new')"><el-icon><Plus /></el-icon>新建 WKD</el-button>
    </PageHeader>
    <section class="surface-card">
      <el-tabs v-model="activeTab" class="table-tabs">
        <el-tab-pane name="all"><template #label>全部<span class="tab-count">{{ counts.all }}</span></template></el-tab-pane>
        <el-tab-pane name="pending"><template #label>待处理<span class="tab-count">{{ counts.pending }}</span></template></el-tab-pane>
        <el-tab-pane name="created"><template #label>我负责<span class="tab-count">{{ counts.created }}</span></template></el-tab-pane>
        <el-tab-pane name="handled"><template #label>曾处理<span class="tab-count">{{ counts.handled }}</span></template></el-tab-pane>
      </el-tabs>
      <div class="filter-bar">
        <el-input v-model="search" class="search-input" clearable placeholder="搜索 WKD 编号或标题" :prefix-icon="Search" @keyup.enter="filterChanged" @clear="filterChanged" />
        <el-button v-if="search || hasWkdFilters(filters)" text @click="resetFilters">重置</el-button>
        <div class="filter-spacer" />
        <el-popover placement="bottom-end" :width="210" trigger="click"><template #reference><el-button><el-icon><SetUp /></el-icon>显示字段<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button></template><div class="column-setting"><strong>自定义表格字段</strong><p>勾选需要在列表中展示的字段</p><el-checkbox-group v-model="visibleColumns"><el-checkbox v-for="col in columnOptions" :key="col.key" :value="col.key" :label="col.key" :disabled="['id','title'].includes(col.key)">{{ col.label }}</el-checkbox></el-checkbox-group></div></el-popover>
      </div>
      <WkdTable :rows="rows" :columns="visibleColumns" :loading="loading" :filterable="filterableColumns" :filters="filters" :filter-options="filterOptions" @filter-change="headerFilterChanged" />
      <div class="table-footer"><span>共 {{ total }} 条记录 · 当前上下文 {{ store.project }} / {{ store.version }}</span><el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" background layout="prev, pager, next, sizes" :page-sizes="[10,20,50]" :total="total" /></div>
    </section>
  </div>
</template>

<style scoped>
.column-setting strong { font-size: 13px; }.column-setting p { color: #98a2b3; font-size: 10px; margin: 5px 0 12px; }.column-setting :deep(.el-checkbox) { display: flex; margin-right: 0; height: 31px; }.column-setting :deep(.el-checkbox__label) { font-size: 11px; }
</style>
