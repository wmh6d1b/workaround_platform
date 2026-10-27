<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import dayjs from 'dayjs'
import type { EChartsOption } from 'echarts'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import StatusTag from '../components/StatusTag.vue'
import { wkdList } from '../data/mock'
import { can, ensureOptions, store } from '../store'
import { api, displayNumber, errorMessage, normalizeWkd, queryString, saveBlob } from '../api'
import type { BootstrapOptions, Wkd, WkdStatus } from '../types'

const filters = reactive({ project_id: store.projectId, version_id: '', machine_id: '', subsystem_id: '', dates: [] as string[] })
const options = ref<BootstrapOptions>(store.options)
const loading = ref(false)
const stats = reactive({ total: 0, approved: 0, approval_rate: 0, average_processing_days: 0, covered_subsystems: 0, status_counts: { NEW_WKD: 0, VERIFY: 0, REVIEW: 0, APPROVED: 0, DISABLE_CONFIRM: 0, DISABLED: 0 } as Record<WkdStatus, number>, trend: [] as { date: string; created: number; approved: number }[], items: [] as Wkd[] })
const versionOptions = computed(() => options.value.versions.filter(item => !filters.project_id || item.project_id === filters.project_id))
const machineOptions = computed(() => options.value.machines.filter(item => !filters.project_id || item.project_id === filters.project_id))
const subsystemOptions = computed(() => options.value.subsystems.filter(item => !filters.project_id || item.project_id === filters.project_id))
const statusNames: [WkdStatus, string, string][] = [['APPROVED','审核通过','#20ad78'],['REVIEW','软件经理审核','#315efb'],['DISABLE_CONFIRM','确认禁用','#7957d5'],['VERIFY','自验证','#f2ad4c'],['NEW_WKD','新建','#a5adba'],['DISABLED','禁用','#d0d5dd']]

const trendOption = computed<EChartsOption>(() => ({ grid: { left: 42, right: 18, top: 30, bottom: 32 }, tooltip: { trigger: 'axis' }, legend: { right: 10, top: 0, itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 10, color: '#7b879a' } }, xAxis: { type: 'category', data: stats.trend.map(item => item.date.slice(5).replace('-', '/')), axisLine: { lineStyle: { color: '#e7eaf0' } }, axisTick: { show: false }, axisLabel: { color: '#98a2b3', fontSize: 9 } }, yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f2f5' } }, axisLabel: { color: '#98a2b3', fontSize: 9 } }, series: [{ name: '新增', type: 'line', smooth: true, symbol: 'none', data: stats.trend.map(item => item.created), lineStyle: { width: 2, color: '#315efb' }, areaStyle: { color: 'rgba(49,94,251,.06)' } }, { name: '审核通过', type: 'line', smooth: true, symbol: 'none', data: stats.trend.map(item => item.approved), lineStyle: { width: 2, color: '#20ad78' } }] }))
const statusOption = computed<EChartsOption>(() => ({ tooltip: { trigger: 'item' }, legend: { bottom: 0, left: 'center', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 9, color: '#7b879a' } }, series: [{ type: 'pie', radius: ['48%','68%'], center: ['50%','43%'], label: { show: false }, data: statusNames.map(([status, name, color]) => ({ name, value: stats.status_counts[status], itemStyle: { color } })) }] }))

function filterParams() {
  return { project_id: filters.project_id, version_id: filters.version_id, machine_id: filters.machine_id, subsystem_id: filters.subsystem_id, start_date: filters.dates?.[0], end_date: filters.dates?.[1] }
}
function loadDemo() {
  const rows = wkdList.filter(item => {
    const date = item.createdAt.slice(0, 10)
    return (!filters.project_id || item.projectId === filters.project_id) && (!filters.version_id || item.versionId === filters.version_id) && (!filters.machine_id || item.machineIds?.includes(filters.machine_id)) && (!filters.subsystem_id || item.subsystemId === filters.subsystem_id) && (!filters.dates?.length || (date >= filters.dates[0] && date <= filters.dates[1]))
  })
  const end = filters.dates?.[1] ? dayjs(filters.dates[1]) : dayjs()
  const start = filters.dates?.[0] ? dayjs(filters.dates[0]) : end.subtract(13, 'day')
  const trend = []
  for (let day = start; day.isBefore(end) || day.isSame(end, 'day'); day = day.add(1, 'day')) {
    const key = day.format('YYYY-MM-DD')
    trend.push({ date: key, created: rows.filter(item => item.createdAt.slice(0,10) === key).length, approved: rows.filter(item => item.status === 'APPROVED' && item.updatedAt.slice(0,10) === key).length })
  }
  const approvedRows = rows.filter(item => item.status === 'APPROVED')
  Object.assign(stats, { total: rows.length, approved: approvedRows.length, approval_rate: rows.length ? Number((approvedRows.length / rows.length * 100).toFixed(1)) : 0, average_processing_days: approvedRows.length ? Number((approvedRows.reduce((sum,item) => sum + Math.max(0, dayjs(item.updatedAt).diff(dayjs(item.createdAt), 'day', true)), 0) / approvedRows.length).toFixed(1)) : 0, covered_subsystems: new Set(rows.map(item => item.subsystemId)).size, trend, items: rows })
  statusNames.forEach(([status]) => { stats.status_counts[status] = rows.filter(item => item.status === status).length })
}
async function load(showMessage = false) {
  loading.value = true
  try {
    if (store.demoMode) loadDemo()
    else {
      const result = await api.get<typeof stats>(`/statistics${queryString(filterParams())}`)
      Object.assign(stats, result, { items: result.items.map(item => normalizeWkd(item)) })
    }
    if (showMessage) ElMessage.success('统计结果已更新')
  } catch (error) { ElMessage.error(errorMessage(error, '统计数据加载失败')) }
  finally { loading.value = false }
}
function projectChanged() { filters.version_id=''; filters.machine_id=''; filters.subsystem_id=''; load() }
function reset() { Object.assign(filters, { project_id:'', version_id:'', machine_id:'', subsystem_id:'', dates:[] }); load() }
function csvCell(value: unknown) { return `"${String(value ?? '').replaceAll('"', '""')}"` }
async function exportCsv() {
  if (!can('stats.export')) return ElMessage.error('当前项目角色无统计导出权限')
  try {
    if (store.demoMode) {
      const csv = 'WKD编号,标题,项目,版本,机台,子系统,责任人,状态,创建时间\n' + stats.items.map(item => [displayNumber(item),item.title,item.project,item.version,item.machine,item.subsystem,item.owner,item.status,item.createdAt].map(csvCell).join(',')).join('\n')
      saveBlob('WMP统计明细.csv', new Blob(['\ufeff'+csv], { type: 'text/csv;charset=utf-8' }))
    } else saveBlob('wmp-statistics.csv', await api.download(`/statistics/export${queryString(filterParams())}`))
    ElMessage.success('统计明细已导出')
  } catch (error) { ElMessage.error(errorMessage(error, '导出失败')) }
}

onMounted(async () => {
  try {
    await ensureOptions()
    if (!store.demoMode) options.value = await api.get<BootstrapOptions>('/bootstrap/options')
    await load()
  } catch (error) { ElMessage.error(errorMessage(error, '统计选项加载失败')) }
})
watch(() => store.projectId, value => { filters.project_id = value; filters.version_id=''; filters.machine_id=''; filters.subsystem_id=''; load() })
</script>

<template>
  <div v-loading="loading">
    <PageHeader title="数据统计" description="按项目、版本、机台和时间维度分析 WKD 数据与流转趋势。"><el-button :disabled="!can('stats.export')" @click="exportCsv"><el-icon><Download /></el-icon>导出明细</el-button></PageHeader>
    <section class="surface-card stats-filter"><div class="stats-filter-grid"><div><label>项目</label><el-select v-model="filters.project_id" clearable placeholder="全部项目" @change="projectChanged"><el-option v-for="item in options.projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></div><div><label>版本</label><el-select v-model="filters.version_id" clearable filterable placeholder="全部版本"><el-option v-for="item in versionOptions" :key="item.id" :label="item.number || item.name" :value="item.id" /></el-select></div><div><label>机台</label><el-select v-model="filters.machine_id" clearable placeholder="全部机台"><el-option v-for="item in machineOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select></div><div><label>子系统</label><el-select v-model="filters.subsystem_id" clearable placeholder="全部子系统"><el-option v-for="item in subsystemOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select></div><div class="date-filter"><label>统计周期</label><el-date-picker v-model="filters.dates" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD" /></div><div class="stats-filter-actions"><el-button @click="reset">重置</el-button><el-button type="primary" @click="load(true)"><el-icon><Search /></el-icon>查询</el-button></div></div></section>
    <section class="metric-grid stats-metrics"><div class="metric-card"><div class="metric-card-top"><span>WKD 总量</span><span class="metric-icon"><el-icon><Files /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.total }}</strong><small>筛选范围</small></div><div class="metric-card-note">当前查询条件下全部记录</div></div><div class="metric-card"><div class="metric-card-top"><span>审核通过率</span><span class="metric-icon green"><el-icon><CircleCheck /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.approval_rate.toFixed(1) }}<em>%</em></strong><small>实时统计</small></div><div class="metric-card-note">{{ stats.approved }} 项当前审核通过</div></div><div class="metric-card"><div class="metric-card-top"><span>平均处理时长</span><span class="metric-icon orange"><el-icon><Timer /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.average_processing_days.toFixed(1) }}<em>天</em></strong><small>已审核通过</small></div><div class="metric-card-note">从创建到审核通过</div></div><div class="metric-card"><div class="metric-card-top"><span>覆盖子系统</span><span class="metric-icon violet"><el-icon><SetUp /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.covered_subsystems }}</strong><small>筛选范围内</small></div><div class="metric-card-note">按 WKD 所属子系统去重</div></div></section>
    <section class="chart-grid"><div class="surface-card"><div class="card-header"><div><h3>WKD 流转趋势</h3><p>每日新增与审核通过数量</p></div><span class="chart-period">{{ stats.trend.length }} 天</span></div><div class="chart-body"><AnalyticsChart :option="trendOption" /></div></div><div class="surface-card"><div class="card-header"><div><h3>工作流状态分布</h3><p>当前筛选范围内全部 WKD</p></div></div><div class="chart-body"><AnalyticsChart :option="statusOption" /></div></div></section>
    <section class="surface-card detail-table"><div class="card-header"><div><h3>数据明细</h3><p>共 {{ stats.total }} 条符合条件的记录</p></div></div><el-table :data="stats.items.slice(0,6)" class="data-table"><el-table-column label="WKD 编号" min-width="150"><template #default="{row}"><span class="table-link id-link">{{ displayNumber(row) }}</span></template></el-table-column><el-table-column prop="title" label="标题" min-width="230" /><el-table-column prop="machine" label="机台" min-width="100" /><el-table-column prop="subsystem" label="子系统" width="110" /><el-table-column prop="owner" label="责任人" width="90" /><el-table-column label="状态" width="120"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column><el-table-column prop="createdAt" label="创建时间" width="145" /></el-table><div class="detail-table-footer">仅预览前 6 条，完整数据请使用「导出明细」。</div></section>
  </div>
</template>

<style scoped>
.stats-filter { padding:17px 20px; margin-bottom:17px; }.stats-filter-grid { display:grid; grid-template-columns:1.25fr .85fr .85fr 1fr 1.8fr auto; gap:12px; align-items:end; }.stats-filter-grid>div { min-width:0; }.stats-filter-grid label { display:block; font-size:10px; color:#7a8494; margin-bottom:7px; }.stats-filter-grid :deep(.el-select),.stats-filter-grid :deep(.el-date-editor) { width:100%; }.stats-filter-actions { display:flex; gap:7px; }.stats-metrics { margin-bottom:17px; }.metric-card-value em { font-size:12px; font-style:normal; margin-left:3px; font-weight:500; }.chart-grid { display:grid; grid-template-columns:1.65fr 1fr; gap:16px; }.chart-body { height:285px; padding:8px 12px 8px 5px; }.chart-period { font-size:10px; color:#8a94a6; background:#f5f7fa; padding:5px 8px; border-radius:5px; }.detail-table { margin-top:18px; }.detail-table-footer { text-align:center; font-size:10px; color:#98a2b3; padding:13px; border-top:1px solid var(--line); }
@media(max-width:1200px){.stats-filter-grid{grid-template-columns:repeat(3,1fr)}.chart-grid{grid-template-columns:1fr}}
</style>
