<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import WkdTable from '../components/WkdTable.vue'
import WkdColumnSettings from '../components/WkdColumnSettings.vue'
import { artifacts as demoArtifacts, wkdList } from '../data/mock'
import type { ArtifactItem, Wkd } from '../types'
import { api, errorMessage, formatBytes, formatDateTime, normalizeWkd, openDownload, queryString, saveBlob } from '../api'
import { can, ensureOptions, store } from '../store'
import { emptyWkdFilters, filterWkdRows, optionsFromWkdRows } from '../utils/wkdFilters'
import type { WkdFilterKey } from '../utils/wkdFilters'
import { loadWkdColumns, saveWkdColumns } from '../utils/tablePreferences'
import { buildDemoExecutablePackage } from '../utils/demoPackage'

const search = ref('')
const machineId = ref('')
const filters = ref(emptyWkdFilters())
const selected = ref<Wkd[]>([])
const sourceRows = ref<Wkd[]>([])
const currentPage = ref(1)
const pageSize = ref(10)
const building = ref(false)
const loading = ref(false)
const recordsOpen = ref(false)
const artifactRows = ref<ArtifactItem[]>([])
const columnUserId = computed(() => store.session?.id || store.session?.username || 'anonymous')
const visibleColumns = ref(loadWkdColumns('debug-build', columnUserId.value))
const machineOptions = computed(() => store.options.machines.filter(item => item.project_id === store.projectId))
const filterOptions = computed(() => optionsFromWkdRows(sourceRows.value))
const filterableColumns: WkdFilterKey[] = ['subsystem', 'owner', 'executionType', 'activityScene', 'measureType', 'stage', 'status']
const filtered = computed(() => filterWkdRows(sourceRows.value, search.value, filters.value).sort((a,b) => a.createdAt.localeCompare(b.createdAt)))
const paged = computed(() => filtered.value.slice((currentPage.value-1)*pageSize.value, currentPage.value*pageSize.value))
const machineName = (id: string) => store.options.machines.find(item => item.id === id)?.name || id

function headerFilterChanged(payload: { key: WkdFilterKey; values: string[] }) {
  filters.value[payload.key] = payload.values
  currentPage.value = 1
}
async function loadEligible() {
  if (!machineId.value) { sourceRows.value = []; return }
  loading.value = true
  try {
    if (store.demoMode) sourceRows.value = wkdList.filter(item => item.projectId === store.projectId && item.machineIds?.includes(machineId.value) && ['VERIFY','REVIEW','APPROVED'].includes(item.status))
    else {
      const result = await api.get<{ items: Record<string, unknown>[] }>(`/builds/eligible${queryString({ kind: 'DEBUG', project_id: store.projectId, machine_id: machineId.value })}`)
      sourceRows.value = result.items.map(normalizeWkd)
    }
    selected.value = []
  } catch (error) { ElMessage.error(errorMessage(error, '可构建 WKD 加载失败')) }
  finally { loading.value = false }
}
async function loadRecords() {
  try {
    if (store.demoMode) artifactRows.value = demoArtifacts.filter(item => item.project_id === store.projectId && item.type === 'DEBUG')
    else artifactRows.value = await api.get<ArtifactItem[]>(`/artifacts${queryString({ project_id: store.projectId, kind: 'DEBUG' })}`)
  } catch (error) { ElMessage.error(errorMessage(error, '构建记录加载失败')) }
}
async function openRecords() { recordsOpen.value = true; await loadRecords() }
async function download(item: ArtifactItem) {
  try {
    if (store.demoMode) {
      if (!item.demoBlob) throw new Error('该历史 Demo 记录没有可下载制品，请重新构建')
      saveBlob(item.filename, item.demoBlob)
    } else {
      const result = await api.get<{ url: string }>(`/artifacts/${item.id}/download`)
      openDownload(result.url)
    }
  } catch (error) { ElMessage.error(errorMessage(error, '制品下载失败')) }
}
async function build() {
  if (!can('build.debug.build')) return ElMessage.error('当前项目角色无调试构建权限')
  if (!machineId.value) return ElMessage.warning('请选择目标机台')
  if (!selected.value.length) return ElMessage.warning('请至少选择一项可构建的 WKD')
  try { await ElMessageBox.confirm(`将按创建时间顺序打包已选 ${selected.value.length} 项规避措施。调试包仅用于测试验证，不可作为正式基线。`, '确认调试构建', { confirmButtonText: '开始构建', cancelButtonText: '取消', type: 'info' }) } catch { return }
  building.value = true
  try {
    let artifact: ArtifactItem
    if (store.demoMode) {
      const id = crypto.randomUUID()
      const content = await buildDemoExecutablePackage({ artifactId: id, kind: 'DEBUG', machineId: machineId.value, rows: selected.value })
      artifact = { id, number: `BUILD-DEBUG-${Date.now()}`, filename: `WMP_DEBUG_${id.slice(0,8)}.tar.gz`, project_id: store.projectId, machine_id: machineId.value, type: 'DEBUG', size: content.size, sha256: content.sha256, builder_id: store.session?.id || '', created_at: new Date().toISOString(), items: selected.value.map((item,index) => ({ wkd_id: item.id, position: index+1, snapshot: item.packageData })), demoBlob: content.blob }
      demoArtifacts.unshift(artifact)
    } else artifact = await api.post<ArtifactItem>('/builds/debug', { project_id: store.projectId, machine_id: machineId.value, wkd_ids: selected.value.map(item => item.id) })
    ElMessage.success('调试规避包已构建，开始下载')
    await download(artifact)
    selected.value = []
  } catch (error) { ElMessage.error(errorMessage(error, '调试构建失败')) }
  finally { building.value = false }
}
onMounted(async () => {
  try { await ensureOptions(); machineId.value = machineOptions.value[0]?.id || ''; await loadEligible() }
  catch (error) { ElMessage.error(errorMessage(error, '基础选项加载失败')) }
})
watch(() => store.projectId, async () => { machineId.value = machineOptions.value[0]?.id || ''; filters.value=emptyWkdFilters(); await loadEligible() })
watch(search, () => { currentPage.value = 1 })
watch(visibleColumns, columns => saveWkdColumns('debug-build', columnUserId.value, columns), { deep: true })
watch(columnUserId, userId => { visibleColumns.value = loadWkdColumns('debug-build', userId) })
</script>

<template>
  <div>
    <PageHeader title="调试构建" description="选择需要验证的规避措施，按创建时间从早到晚打包为调试软件包。"><el-button @click="openRecords"><el-icon><Document /></el-icon>构建记录</el-button><el-button type="primary" :loading="building" :disabled="!can('build.debug.build') || !selected.length || !machineId" @click="build"><el-icon><Box /></el-icon>构建已选<span v-if="selected.length">（{{ selected.length }}）</span></el-button></PageHeader>
    <div class="build-notice"><el-icon><InfoFilled /></el-icon><span>新建规避措施与已禁用状态不可勾选；正式交付请前往「正式构建」。</span><router-link to="/build/release">前往正式构建<el-icon><ArrowRight /></el-icon></router-link></div>
    <section class="surface-card"><div class="filter-bar"><el-input v-model="search" class="search-input" clearable placeholder="搜索 WKD 编号或标题" :prefix-icon="Search" /><el-select v-model="machineId" placeholder="目标机台" style="width:140px" @change="loadEligible"><el-option v-for="item in machineOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-button text :loading="loading" @click="loadEligible"><el-icon><Refresh /></el-icon></el-button><div class="filter-spacer" /><WkdColumnSettings v-model="visibleColumns" table-key="debug-build" /><span class="selection-summary">已选择 <strong>{{ selected.length }}</strong> 项</span></div><WkdTable :rows="paged" selectable :loading="loading" :columns="visibleColumns" :filterable="filterableColumns" :filters="filters" :filter-options="filterOptions" @filter-change="headerFilterChanged" @selection="selected = $event" /><div class="table-footer"><span>共 {{ filtered.length }} 条 · 列表按创建时间升序排列</span><el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" background layout="prev, pager, next, sizes" :page-sizes="[10,20,50]" :total="filtered.length" /></div></section>
    <el-drawer v-model="recordsOpen" title="调试构建记录" size="720px"><el-table :data="artifactRows"><el-table-column label="制品文件" min-width="230"><template #default="{row}"><span class="mono">{{ row.filename }}</span></template></el-table-column><el-table-column label="机台" width="100"><template #default="{row}">{{ machineName(row.machine_id) }}</template></el-table-column><el-table-column label="大小" width="90"><template #default="{row}">{{ formatBytes(row.size) }}</template></el-table-column><el-table-column label="构建时间" width="145"><template #default="{row}">{{ formatDateTime(row.created_at) }}</template></el-table-column><el-table-column label="操作" width="80"><template #default="{row}"><el-button text type="primary" @click="download(row)">下载</el-button></template></el-table-column></el-table></el-drawer>
  </div>
</template>

<style scoped>
.build-notice { min-height:40px; display:flex; align-items:center; gap:8px; color:#5f6f91; background:#eef3ff; border:1px solid #dfe7ff; border-radius:8px; padding:9px 13px; font-size:11px; margin-bottom:15px; }.build-notice>.el-icon { color:#315efb; }.build-notice a { margin-left:auto; color:#315efb; display:flex; align-items:center; gap:4px; }.selection-summary { font-size:11px; color:#8a94a6; }.selection-summary strong { color:#315efb; }
</style>
