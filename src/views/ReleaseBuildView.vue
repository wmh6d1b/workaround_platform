<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import WkdTable from '../components/WkdTable.vue'
import { artifacts as demoArtifacts, wkdList } from '../data/mock'
import { can, ensureOptions, store } from '../store'
import { api, errorMessage, formatBytes, formatDateTime, normalizeWkd, openDownload, queryString, saveBlob } from '../api'
import type { ArtifactItem, Wkd } from '../types'
import { emptyWkdFilters, filterWkdRows, optionsFromWkdRows } from '../utils/wkdFilters'
import type { WkdFilterKey } from '../utils/wkdFilters'
import { buildDemoExecutablePackage } from '../utils/demoPackage'

const machineId = ref('')
const search = ref('')
const filters = ref(emptyWkdFilters())
const building = ref(false)
const loading = ref(false)
const selected = ref<Wkd[]>([])
const sourceRows = ref<Wkd[]>([])
const artifactRows = ref<ArtifactItem[]>([])
const machineOptions = computed(() => store.options.machines.filter(item => item.project_id === store.projectId))
const filterOptions = computed(() => optionsFromWkdRows(sourceRows.value))
const filterableColumns: WkdFilterKey[] = ['subsystem', 'owner', 'stage']
const rows = computed(() => filterWkdRows(sourceRows.value, search.value, filters.value))
const machineName = (id: string) => store.options.machines.find(item => item.id === id)?.name || id

function headerFilterChanged(payload: { key: WkdFilterKey; values: string[] }) {
  filters.value[payload.key] = payload.values
}
async function loadEligible() {
  if (!machineId.value) { sourceRows.value = []; return }
  if (store.demoMode) sourceRows.value = wkdList.filter(item => item.projectId === store.projectId && item.machineIds?.includes(machineId.value) && item.status === 'APPROVED')
  else {
    const result = await api.get<{ items: Record<string, unknown>[] }>(`/builds/eligible${queryString({ kind: 'RELEASE', project_id: store.projectId, machine_id: machineId.value })}`)
    sourceRows.value = result.items.map(normalizeWkd)
  }
}
async function loadArtifacts() {
  if (store.demoMode) artifactRows.value = demoArtifacts.filter(item => item.project_id === store.projectId && item.type === 'RELEASE' && (!machineId.value || item.machine_id === machineId.value))
  else artifactRows.value = await api.get<ArtifactItem[]>(`/artifacts${queryString({ project_id: store.projectId, machine_id: machineId.value, kind: 'RELEASE' })}`)
}
async function load() {
  loading.value = true
  try { await Promise.all([loadEligible(), loadArtifacts()]) }
  catch (error) { ElMessage.error(errorMessage(error, '构建数据加载失败')) }
  finally { loading.value = false }
}
async function machineChanged() { selected.value = []; await load() }
async function build() {
  if (!can('build.release.build')) return ElMessage.error('当前角色无正式构建权限')
  if (!selected.value.length) return ElMessage.warning('请至少选择一项审核通过的 WKD')
  try { await ElMessageBox.confirm(`将基于 ${store.project} / ${machineName(machineId.value)} 下已选的 ${selected.value.length} 项 WKD 生成正式基线制品。`, '确认正式构建', { confirmButtonText: '确认构建', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  building.value = true
  try {
    if (store.demoMode) {
      const id = crypto.randomUUID()
      const content = await buildDemoExecutablePackage({ artifactId: id, kind: 'RELEASE', machineId: machineId.value, rows: selected.value })
      demoArtifacts.unshift({ id, number: `BUILD-DEMO-${Date.now()}`, filename: `WMP_RELEASE_${id.slice(0,8)}.tar.gz`, project_id: store.projectId, machine_id: machineId.value, type: 'RELEASE', size: content.size, sha256: content.sha256, builder_id: store.session?.id || '', created_at: new Date().toISOString(), items: selected.value.map((item, index) => ({ wkd_id: item.id, position: index + 1, snapshot: item.packageData })), demoBlob: content.blob })
    } else await api.post('/builds/release', { project_id: store.projectId, machine_id: machineId.value, wkd_ids: selected.value.map(item => item.id) })
    ElMessage.success('正式构建完成，制品已生成')
    await load()
  } catch (error) { ElMessage.error(errorMessage(error, '正式构建失败')) }
  finally { building.value = false }
}
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

onMounted(async () => {
  try {
    await ensureOptions()
    machineId.value = machineOptions.value[0]?.id || ''
    await load()
  } catch (error) { ElMessage.error(errorMessage(error, '基础选项加载失败')) }
})
watch(() => store.projectId, async () => { machineId.value = machineOptions.value[0]?.id || ''; filters.value=emptyWkdFilters(); await load() })
</script>

<template>
  <div>
    <PageHeader title="正式构建" description="基于审核通过的规避措施生成正式基线制品，确保交付内容一致且可追溯。"><el-tooltip :disabled="can('build.release.build')" content="仅具有正式构建权限的项目角色可执行" placement="bottom"><span><el-button type="primary" :disabled="!can('build.release.build') || !selected.length" :loading="building" @click="build"><el-icon><Lock v-if="!can('build.release.build')" /><Box v-else /></el-icon>正式构建</el-button></span></el-tooltip></PageHeader>
    <div v-if="!can('build.release.build')" class="permission-notice"><el-icon><Lock /></el-icon>当前项目角色仅有查看与下载权限；后端接口会同步校验构建权限。</div>
    <section class="surface-card release-source"><div class="card-header"><div><h3>构建内容</h3><p>展示当前项目与所选机台下审核通过的 WKD，默认全选</p></div><div class="release-context"><span>{{ store.project }}</span><el-icon><ArrowRight /></el-icon><span>{{ machineName(machineId) }}</span></div></div><div class="filter-bar"><span class="filter-label">目标机台</span><el-select v-model="machineId" filterable style="width:170px" @change="machineChanged"><el-option v-for="item in machineOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-input v-model="search" class="search-input" clearable placeholder="搜索审核通过的 WKD 编号或标题" :prefix-icon="Search" /><div class="filter-spacer" /><span class="active-count"><i />已选 {{ selected.length }} / {{ rows.length }} 项</span></div><WkdTable :rows="rows" selectable preselect :loading="loading" :columns="['id','title','machine','subsystem','owner','stage','status']" :filterable="filterableColumns" :filters="filters" :filter-options="filterOptions" @filter-change="headerFilterChanged" @selection="selected = $event" /></section>
    <section class="surface-card artifact-section"><div class="card-header"><div><h3>基线制品</h3><p>正式构建生成的软件包与校验信息</p></div><el-button text type="primary" :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新列表</el-button></div><el-table v-loading="loading" :data="artifactRows" class="data-table"><el-table-column label="制品文件" min-width="310"><template #default="{ row }"><div class="artifact-name"><span><el-icon><Files /></el-icon></span><div><strong class="mono">{{ row.filename }}</strong><small>SHA256 {{ row.sha256.slice(0,8) }}...{{ row.sha256.slice(-4) }}</small></div></div></template></el-table-column><el-table-column label="机台" width="100"><template #default="{row}">{{ machineName(row.machine_id) }}</template></el-table-column><el-table-column label="WKD 数量" width="95" align="center"><template #default="{row}">{{ row.items.length }}</template></el-table-column><el-table-column label="大小" width="90"><template #default="{row}">{{ formatBytes(row.size) }}</template></el-table-column><el-table-column label="构建时间" width="145"><template #default="{row}">{{ formatDateTime(row.created_at) }}</template></el-table-column><el-table-column label="操作" width="85" align="right"><template #default="{ row }"><el-button v-if="can('build.release.download')" text type="primary" @click="download(row)"><el-icon><Download /></el-icon>下载</el-button></template></el-table-column></el-table></section>
  </div>
</template>

<style scoped>
.permission-notice { display:flex; gap:8px; align-items:center; padding:11px 14px; background:#fff7e9; color:#9b670f; border:1px solid #f8e7c6; border-radius:8px; font-size:11px; margin-bottom:15px; }.release-context { display:flex; gap:7px; align-items:center; font-size:10px; color:#7b879a; }.release-context .el-icon { font-size:9px; }.release-source { margin-bottom:20px; }.active-count { font-size:11px; color:#16865b; display:flex; align-items:center; gap:6px; }.active-count i { width:6px; height:6px; border-radius:50%; background:#20ad78; }.artifact-section { margin-top:20px; }.artifact-name { display:flex; align-items:center; gap:10px; }.artifact-name>span { width:30px; height:30px; display:grid; place-items:center; background:#f0f3ff; color:#315efb; border-radius:7px; }.artifact-name>div { display:flex; flex-direction:column; gap:3px; min-width:0; }.artifact-name strong { font-size:10px; font-weight:500; }.artifact-name small { color:#a0a8b7; font-size:9px; }
</style>
