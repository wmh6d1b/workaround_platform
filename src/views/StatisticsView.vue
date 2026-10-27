<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import dayjs from 'dayjs'
import type { EChartsOption } from 'echarts'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import StatusTag from '../components/StatusTag.vue'
import { wkdList } from '../data/mock'
import { store } from '../store'
import { api, displayNumber, errorMessage, normalizeWkd, queryString, saveBlob } from '../api'
import type { BootstrapOptions, ExecuteStage, ExecutionType, Wkd, WkdStatus } from '../types'

interface CountItem { name: string; value: number }
interface StatisticsResult {
  scope: 'project' | 'global'
  total: number
  approved: number
  pending: number
  approval_rate: number
  average_processing_days: number
  covered_subsystems: number
  status_counts: Record<WkdStatus, number>
  project_counts: CountItem[]
  execution_counts: CountItem[]
  trend_granularity: 'day' | 'week' | 'month'
  trend: { date: string; created: number; approved: number }[]
  items: Wkd[]
}

const emptyStats = (): StatisticsResult => ({
  scope: 'project', total: 0, approved: 0, pending: 0, approval_rate: 0, average_processing_days: 0,
  covered_subsystems: 0,
  status_counts: { NEW_WKD: 0, VERIFY: 0, REVIEW: 0, APPROVED: 0, DISABLE_CONFIRM: 0, DISABLED: 0 },
  project_counts: [], execution_counts: [], trend_granularity: 'day', trend: [], items: [],
})
const createFilters = () => ({
  project_ids: [] as string[], version_ids: [] as string[], machine_ids: [] as string[], subsystem_ids: [] as string[],
  found_version_ids: [] as string[], planned_version_ids: [] as string[], statuses: [] as WkdStatus[],
  execution_types: [] as ExecutionType[], activity_scenes: [] as string[], measure_types: [] as string[],
  owner_ids: [] as string[], handler_ids: [] as string[], stages: [] as ExecuteStage[],
  keyword: '', date_field: 'created' as 'created' | 'updated',
  dates: [dayjs().subtract(29, 'day').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')] as string[],
})

const scope = ref<'project' | 'global'>('project')
const filters = reactive(createFilters())
const options = ref<BootstrapOptions>(store.options)
const stats = reactive<StatisticsResult>(emptyStats())
const loading = ref(false)
const exporting = ref(false)
const advancedOpen = ref(false)
const page = ref(1)
const pageSize = 8
const stageNames: [ExecuteStage, string][] = [['pre_upgrade', '升级前'], ['post_upgrade', '升级后'], ['post_start', '启动后'], ['post_init', '初始化后'], ['custom', '自定义']]
const statusNames: [WkdStatus, string, string][] = [['APPROVED', '审核通过', '#20ad78'], ['REVIEW', '软件经理审核', '#315efb'], ['DISABLE_CONFIRM', '确认禁用', '#7957d5'], ['VERIFY', '自验证', '#f2ad4c'], ['NEW_WKD', '新建规避措施', '#98a2b3'], ['DISABLED', '禁用', '#d0d5dd']]
const executionNames = [['AUTOMATED', '自动化执行'], ['MANUAL', '人工操作']]
const sceneOptions = ['首版本部署', 'ES集成活动', '常规版本升级']
const measureOptions = ['事前规避措施', '事后恢复措施']
const selectedProjects = computed(() => filters.project_ids)
const selectedProjectId = computed({ get: () => filters.project_ids[0] || '', set: value => { filters.project_ids = value ? [value] : []; projectsChanged() } })
const inSelectedProjects = (item: { project_id?: string | null }) => !selectedProjects.value.length || selectedProjects.value.includes(item.project_id || '')
const versionOptions = computed(() => options.value.versions.filter(inSelectedProjects))
const machineOptions = computed(() => options.value.machines.filter(inSelectedProjects))
const subsystemOptions = computed(() => options.value.subsystems.filter(inSelectedProjects))
const activeFilterCount = computed(() => Object.entries(filters).reduce((count, [key, value]) => {
  if (key === 'dates' || key === 'date_field' || (key === 'project_ids' && scope.value === 'project')) return count
  return count + (Array.isArray(value) ? value.length : value ? 1 : 0)
}, 0))
const granularityNames = { day: '按日', week: '按周', month: '按月' }
const pagedItems = computed(() => stats.items.slice((page.value - 1) * pageSize, page.value * pageSize))
const scopeDescription = computed(() => scope.value === 'global' ? '跨项目汇总与对比，所有已登录用户均可查询和导出。' : `当前项目：${options.value.projects.find(item => item.id === selectedProjectId.value)?.name || '未选择'}，统计结果限定在所选项目内。`)

const trendOption = computed<EChartsOption>(() => ({
  grid: { left: 42, right: 18, top: 38, bottom: 34 }, tooltip: { trigger: 'axis' },
  legend: { right: 12, top: 4, itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 11, color: '#667085' } },
  xAxis: { type: 'category', data: stats.trend.map(item => item.date.slice(5).replace('-', '/')), axisLine: { lineStyle: { color: '#e7eaf0' } }, axisTick: { show: false }, axisLabel: { color: '#98a2b3', fontSize: 10 } },
  yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f2f5' } }, axisLabel: { color: '#98a2b3', fontSize: 10 } },
  series: [
    { name: '新增', type: 'line', smooth: true, symbol: 'none', data: stats.trend.map(item => item.created), lineStyle: { width: 2, color: '#315efb' }, areaStyle: { color: 'rgba(49,94,251,.06)' } },
    { name: '审核通过', type: 'line', smooth: true, symbol: 'none', data: stats.trend.map(item => item.approved), lineStyle: { width: 2, color: '#20ad78' } },
  ],
}))
const statusOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'item' }, legend: { bottom: 0, left: 'center', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 10, color: '#667085' } },
  series: [{ type: 'pie', radius: ['48%', '68%'], center: ['50%', '43%'], label: { show: false }, data: statusNames.map(([status, name, color]) => ({ name, value: stats.status_counts[status], itemStyle: { color } })) }],
}))
const compareOption = computed<EChartsOption>(() => {
  const data = scope.value === 'global' ? stats.project_counts : stats.execution_counts.map(item => ({ ...item, name: executionNames.find(([value]) => value === item.name)?.[1] || item.name }))
  return {
    grid: { left: 90, right: 30, top: 20, bottom: 28 }, tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f2f5' } }, axisLabel: { color: '#98a2b3' } },
    yAxis: { type: 'category', data: data.map(item => item.name), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#667085', width: 78, overflow: 'truncate' } },
    series: [{ type: 'bar', barMaxWidth: 20, data: data.map(item => item.value), itemStyle: { color: '#6689f7', borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: '#667085' } }],
  }
})

function filterParams() {
  return {
    scope: scope.value, project_ids: filters.project_ids,
    version_ids: filters.version_ids, machine_ids: filters.machine_ids, subsystem_ids: filters.subsystem_ids,
    found_version_ids: filters.found_version_ids, planned_version_ids: filters.planned_version_ids,
    statuses: filters.statuses, execution_types: filters.execution_types, activity_scenes: filters.activity_scenes,
    measure_types: filters.measure_types, owner_ids: filters.owner_ids, handler_ids: filters.handler_ids,
    stages: filters.stages, keyword: filters.keyword.trim(), date_field: filters.date_field,
    start_date: filters.dates?.[0], end_date: filters.dates?.[1],
  }
}
function includes<T>(selected: T[], value: T | undefined) { return !selected.length || (value !== undefined && selected.includes(value)) }
function demoRows() {
  const params = filterParams()
  return wkdList.filter(item => {
    const date = (params.date_field === 'created' ? item.createdAt : item.updatedAt).slice(0, 10)
    const keyword = params.keyword.toLowerCase()
    return includes(params.project_ids, item.projectId) && includes(params.version_ids, item.versionId) &&
      (!params.machine_ids.length || params.machine_ids.some(id => item.machineIds?.includes(id))) &&
      includes(params.subsystem_ids, item.subsystemId) && includes(params.found_version_ids, item.foundVersionId) &&
      includes(params.planned_version_ids, item.plannedVersionId) && includes(params.statuses, item.status) &&
      includes(params.execution_types, item.executionType) && includes(params.activity_scenes, item.activityScene) &&
      includes(params.measure_types, item.measureType) && includes(params.owner_ids, item.ownerId) &&
      includes(params.handler_ids, item.currentHandlerId) && includes(params.stages, item.stage || undefined) &&
      (!keyword || [item.number, item.title, item.issueNo, item.requirementNo].some(value => value?.toLowerCase().includes(keyword))) &&
      (!params.start_date || date >= params.start_date) && (!params.end_date || date <= params.end_date)
  })
}
function loadDemo() {
  const rows = demoRows()
  const start = dayjs(filters.dates[0])
  const end = dayjs(filters.dates[1])
  const days = end.diff(start, 'day') + 1
  const granularity = days <= 31 ? 'day' : days <= 93 ? 'week' : 'month'
  const keys = new Map<string, { date: string; created: number; approved: number }>()
  const bucket = (value: string) => {
    const date = dayjs(value)
    return granularity === 'month' ? date.startOf('month').format('YYYY-MM-DD') : granularity === 'week' ? date.startOf('week').add(1, 'day').format('YYYY-MM-DD') : date.format('YYYY-MM-DD')
  }
  rows.forEach(item => {
    const createdKey = bucket(item.createdAt)
    const approvedKey = bucket(item.updatedAt)
    if (!keys.has(createdKey)) keys.set(createdKey, { date: createdKey, created: 0, approved: 0 })
    keys.get(createdKey)!.created++
    if (item.status === 'APPROVED') {
      if (!keys.has(approvedKey)) keys.set(approvedKey, { date: approvedKey, created: 0, approved: 0 })
      keys.get(approvedKey)!.approved++
    }
  })
  const approvedRows = rows.filter(item => item.status === 'APPROVED')
  const result = emptyStats()
  Object.assign(result, {
    scope: scope.value, total: rows.length, approved: approvedRows.length,
    pending: rows.filter(item => ['VERIFY', 'REVIEW', 'DISABLE_CONFIRM'].includes(item.status)).length,
    approval_rate: rows.length ? Number((approvedRows.length / rows.length * 100).toFixed(1)) : 0,
    average_processing_days: approvedRows.length ? Number((approvedRows.reduce((sum, item) => sum + Math.max(0, dayjs(item.updatedAt).diff(dayjs(item.createdAt), 'day', true)), 0) / approvedRows.length).toFixed(1)) : 0,
    covered_subsystems: new Set(rows.map(item => item.subsystemId)).size,
    trend_granularity: granularity, trend: [...keys.values()].sort((a, b) => a.date.localeCompare(b.date)), items: rows,
    project_counts: [...rows.reduce((map, item) => map.set(item.project, (map.get(item.project) || 0) + 1), new Map<string, number>())].map(([name, value]) => ({ name, value })),
    execution_counts: [...rows.reduce((map, item) => map.set(item.executionType || 'AUTOMATED', (map.get(item.executionType || 'AUTOMATED') || 0) + 1), new Map<string, number>())].map(([name, value]) => ({ name, value })),
  })
  statusNames.forEach(([status]) => { result.status_counts[status] = rows.filter(item => item.status === status).length })
  Object.assign(stats, result)
}
async function load(showMessage = false) {
  if (scope.value === 'project' && filters.project_ids.length !== 1) return ElMessage.warning('项目统计请选择一个项目')
  loading.value = true
  try {
    if (store.demoMode) loadDemo()
    else {
      const result = await api.get<StatisticsResult>(`/statistics${queryString(filterParams())}`)
      Object.assign(stats, result, { items: result.items.map(item => normalizeWkd(item)) })
    }
    page.value = 1
    if (showMessage) ElMessage.success('统计结果已更新')
  } catch (error) { ElMessage.error(errorMessage(error, '统计数据加载失败')) }
  finally { loading.value = false }
}
function resetCascade() {
  filters.version_ids = []
  filters.found_version_ids = []
  filters.planned_version_ids = []
  filters.machine_ids = []
  filters.subsystem_ids = []
}
function projectsChanged() {
  const valid = (ids: string[], source: { id: string; project_id?: string | null }[]) => ids.filter(id => source.some(item => item.id === id && inSelectedProjects(item)))
  filters.version_ids = valid(filters.version_ids, options.value.versions)
  filters.found_version_ids = valid(filters.found_version_ids, options.value.versions)
  filters.planned_version_ids = valid(filters.planned_version_ids, options.value.versions)
  filters.machine_ids = valid(filters.machine_ids, options.value.machines)
  filters.subsystem_ids = valid(filters.subsystem_ids, options.value.subsystems)
}
function defaultProjectId() {
  return options.value.projects.some(item => item.id === store.projectId) ? store.projectId : options.value.projects[0]?.id || ''
}
function changeScope(value: 'project' | 'global') {
  scope.value = value
  filters.project_ids = value === 'project' && defaultProjectId() ? [defaultProjectId()] : []
  resetCascade()
  load()
}
function reset() {
  const currentScope = scope.value
  Object.assign(filters, createFilters())
  scope.value = currentScope
  filters.project_ids = currentScope === 'project' && defaultProjectId() ? [defaultProjectId()] : []
  load()
}
function csvCell(value: unknown) { return `"${String(value ?? '').replaceAll('"', '""')}"` }
async function exportCsv() {
  exporting.value = true
  try {
    if (store.demoMode) {
      const rows = demoRows()
      const csv = 'WKD编号,标题,项目,所属版本,问题发现版本,规划解决版本,机台,子系统,责任人,当前处理人,执行类型,活动场景,措施类型,执行阶段,自定义阶段,状态,创建时间,更新时间\n' + rows.map(item => [displayNumber(item), item.title, item.project, item.version, item.foundVersion, item.plannedVersion, item.machine, item.subsystem, item.owner, item.currentHandler, executionNames.find(([value]) => value === item.executionType)?.[1], item.activityScene, item.measureType, stageNames.find(([value]) => value === item.stage)?.[1], item.customStageName, statusNames.find(([value]) => value === item.status)?.[1], item.createdAt, item.updatedAt].map(csvCell).join(',')).join('\n')
      saveBlob('WMP统计明细.csv', new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' }))
    } else saveBlob('wmp-statistics.csv', await api.download(`/statistics/export${queryString(filterParams())}`))
    ElMessage.success(`已导出 ${stats.total} 条统计明细`)
  } catch (error) { ElMessage.error(errorMessage(error, '导出失败')) }
  finally { exporting.value = false }
}

onMounted(async () => {
  try {
    if (!store.demoMode) options.value = await api.get<BootstrapOptions>('/statistics/options')
    filters.project_ids = defaultProjectId() ? [defaultProjectId()] : []
    await load()
  } catch (error) { ElMessage.error(errorMessage(error, '统计选项加载失败')) }
})
watch(() => store.projectId, value => { if (scope.value === 'project') { filters.project_ids = value ? [value] : []; resetCascade(); load() } })
</script>

<template>
  <div class="statistics-page" v-loading="loading">
    <PageHeader title="数据统计" :description="scopeDescription">
      <el-button :loading="exporting" @click="exportCsv"><el-icon><Download /></el-icon>导出明细</el-button>
    </PageHeader>

    <section class="surface-card stats-filter">
      <div class="filter-topline">
        <el-radio-group :model-value="scope" @change="changeScope($event as 'project' | 'global')">
          <el-radio-button value="project">项目统计</el-radio-button><el-radio-button value="global">全局统计</el-radio-button>
        </el-radio-group>
        <span class="filter-count">{{ activeFilterCount ? `已设置 ${activeFilterCount} 个筛选条件` : '默认统计最近 30 天' }}</span>
      </div>
      <div class="filter-grid primary-filters">
        <div class="filter-field project-filter"><label>项目</label><el-select v-if="scope === 'global'" v-model="filters.project_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部项目" @change="projectsChanged"><el-option v-for="item in options.projects" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-select v-else v-model="selectedProjectId" filterable clearable placeholder="选择项目"><el-option v-for="item in options.projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></div>
        <div class="filter-field keyword-filter"><label>关键字</label><el-input v-model="filters.keyword" clearable placeholder="编号 / 标题 / 问题单 / 需求单" @keyup.enter="load(true)"><template #prefix><el-icon><Search /></el-icon></template></el-input></div>
        <div class="filter-field"><label>所属版本</label><el-select v-model="filters.version_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部版本"><el-option v-for="item in versionOptions" :key="item.id" :label="item.number || item.name" :value="item.id" /></el-select></div>
        <div class="filter-field"><label>机台</label><el-select v-model="filters.machine_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部机台"><el-option v-for="item in machineOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select></div>
        <div class="filter-field"><label>状态</label><el-select v-model="filters.statuses" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部状态"><el-option v-for="item in statusNames" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select></div>
        <div class="filter-field date-filter"><label>时间范围</label><div class="date-combo"><el-select v-model="filters.date_field" class="date-field"><el-option label="创建时间" value="created" /><el-option label="更新时间" value="updated" /></el-select><el-date-picker v-model="filters.dates" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" :clearable="false" /></div></div>
        <div class="filter-actions"><el-button @click="reset">重置</el-button><el-button type="primary" @click="load(true)"><el-icon><Search /></el-icon>查询</el-button></div>
      </div>
      <button class="advanced-toggle" type="button" @click="advancedOpen = !advancedOpen"><el-icon><Filter /></el-icon>高级筛选<span>版本、子系统、人员、执行属性</span><el-icon class="toggle-arrow" :class="{ open: advancedOpen }"><ArrowDown /></el-icon></button>
      <el-collapse-transition><div v-show="advancedOpen" class="filter-grid advanced-filters">
        <div class="filter-field"><label>问题发现版本</label><el-select v-model="filters.found_version_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部版本"><el-option v-for="item in versionOptions" :key="item.id" :label="item.number || item.name" :value="item.id" /></el-select></div>
        <div class="filter-field"><label>规划解决版本</label><el-select v-model="filters.planned_version_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部版本"><el-option v-for="item in versionOptions" :key="item.id" :label="item.number || item.name" :value="item.id" /></el-select></div>
        <div class="filter-field"><label>子系统</label><el-select v-model="filters.subsystem_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部子系统"><el-option v-for="item in subsystemOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select></div>
        <div class="filter-field"><label>责任人</label><el-select v-model="filters.owner_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部责任人"><el-option v-for="item in options.users" :key="item.id" :label="item.name" :value="item.id" /></el-select></div>
        <div class="filter-field"><label>当前处理人</label><el-select v-model="filters.handler_ids" multiple filterable collapse-tags collapse-tags-tooltip clearable placeholder="全部处理人"><el-option v-for="item in options.users" :key="item.id" :label="item.name" :value="item.id" /></el-select></div>
        <div class="filter-field"><label>执行类型</label><el-select v-model="filters.execution_types" multiple collapse-tags collapse-tags-tooltip clearable placeholder="全部类型"><el-option v-for="item in executionNames" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select></div>
        <div class="filter-field"><label>活动场景</label><el-select v-model="filters.activity_scenes" multiple collapse-tags collapse-tags-tooltip clearable placeholder="全部场景"><el-option v-for="item in sceneOptions" :key="item" :label="item" :value="item" /></el-select></div>
        <div class="filter-field"><label>措施类型</label><el-select v-model="filters.measure_types" multiple collapse-tags collapse-tags-tooltip clearable placeholder="全部类型"><el-option v-for="item in measureOptions" :key="item" :label="item" :value="item" /></el-select></div>
        <div class="filter-field"><label>执行阶段</label><el-select v-model="filters.stages" multiple collapse-tags collapse-tags-tooltip clearable placeholder="全部阶段"><el-option v-for="item in stageNames" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select></div>
      </div></el-collapse-transition>
    </section>

    <section class="metric-grid stats-metrics">
      <div class="metric-card"><div class="metric-card-top"><span>WKD 总量</span><span class="metric-icon"><el-icon><Files /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.total }}</strong><small>条记录</small></div><div class="metric-card-note">符合当前全部筛选条件</div></div>
      <div class="metric-card"><div class="metric-card-top"><span>审核通过率</span><span class="metric-icon green"><el-icon><CircleCheck /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.approval_rate.toFixed(1) }}<em>%</em></strong><small>{{ stats.approved }} 条通过</small></div><div class="metric-card-note">审核通过数量 / 筛选总量</div></div>
      <div class="metric-card"><div class="metric-card-top"><span>待处理</span><span class="metric-icon orange"><el-icon><Clock /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.pending }}</strong><small>条记录</small></div><div class="metric-card-note">自验证、审核与确认禁用</div></div>
      <div class="metric-card"><div class="metric-card-top"><span>平均处理时长</span><span class="metric-icon violet"><el-icon><Timer /></el-icon></span></div><div class="metric-card-value"><strong>{{ stats.average_processing_days.toFixed(1) }}<em>天</em></strong><small>已完成审核</small></div><div class="metric-card-note">从创建到首次审核通过</div></div>
    </section>

    <section class="chart-grid"><div class="surface-card"><div class="card-header"><div><h3>WKD 流转趋势</h3><p>新增与审核通过数量</p></div><span class="chart-period">{{ granularityNames[stats.trend_granularity] }}</span></div><div class="chart-body"><AnalyticsChart :option="trendOption" /></div></div><div class="surface-card"><div class="card-header"><div><h3>工作流状态分布</h3><p>各状态记录占比</p></div></div><div class="chart-body"><AnalyticsChart :option="statusOption" /></div></div></section>
    <section class="surface-card compare-card"><div class="card-header"><div><h3>{{ scope === 'global' ? '项目数据对比' : '执行类型分布' }}</h3><p>{{ scope === 'global' ? '所选范围内各项目 WKD 数量' : '自动化执行与人工操作数量' }}</p></div></div><div class="compare-body"><AnalyticsChart :option="compareOption" /></div></section>

    <section class="surface-card detail-table"><div class="card-header"><div><h3>数据明细</h3><p>共 {{ stats.total }} 条记录，与图表及导出使用相同筛选条件</p></div></div><el-table :data="pagedItems" class="data-table" empty-text="当前条件下暂无数据"><el-table-column v-if="scope === 'global'" prop="project" label="项目" min-width="130" show-overflow-tooltip /><el-table-column label="WKD 编号" min-width="150"><template #default="{ row }"><span class="table-link id-link">{{ displayNumber(row) }}</span></template></el-table-column><el-table-column prop="title" label="标题" min-width="230" show-overflow-tooltip /><el-table-column prop="version" label="所属版本" min-width="105" /><el-table-column prop="machine" label="机台" min-width="110" show-overflow-tooltip /><el-table-column prop="subsystem" label="子系统" min-width="110" /><el-table-column prop="owner" label="责任人" width="90" /><el-table-column label="当前处理人" width="105"><template #default="{ row }">{{ row.currentHandler || '—' }}</template></el-table-column><el-table-column label="状态" width="125"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column><el-table-column prop="createdAt" label="创建时间" width="150" /></el-table><div class="table-pagination"><el-pagination v-model:current-page="page" :page-size="pageSize" :total="stats.items.length" layout="prev, pager, next" background hide-on-single-page /></div></section>
  </div>
</template>

<style scoped>
.statistics-page { padding-bottom: 24px; }.stats-filter { padding: 18px 20px 0; margin-bottom: 18px; }.filter-topline { display: flex; align-items: center; justify-content: space-between; margin-bottom: 17px; }.scope-label { display: inline-flex; align-items: center; gap: 7px; color: #344054; font-size: 13px; font-weight: 600; }.filter-count { color: #98a2b3; font-size: 11px; }.filter-grid { display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 13px 16px; align-items: end; }.primary-filters { grid-template-columns: repeat(4, minmax(145px, 1fr)); }.filter-field { min-width: 0; }.filter-field label { display: block; margin-bottom: 7px; color: #667085; font-size: 11px; }.filter-field :deep(.el-select), .filter-field :deep(.el-date-editor), .filter-field :deep(.el-input) { width: 100%; }.keyword-filter { grid-column: span 1; }.date-filter { grid-column: span 2; }.date-combo { display: grid; grid-template-columns: 102px minmax(240px, 1fr); }.date-combo :deep(.el-select .el-select__wrapper) { border-radius: 6px 0 0 6px; }.date-combo :deep(.el-date-editor) { border-radius: 0 6px 6px 0; margin-left: -1px; }.filter-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }.advanced-toggle { width: 100%; display: flex; align-items: center; gap: 7px; margin-top: 16px; padding: 12px 0; border: 0; border-top: 1px solid #f0f2f5; background: transparent; color: #667085; font-size: 11px; cursor: pointer; text-align: left; }.advanced-toggle:hover { color: #315efb; }.advanced-toggle span { color: #a0a8b7; margin-left: 3px; }.toggle-arrow { margin-left: auto; transition: transform .2s; }.toggle-arrow.open { transform: rotate(180deg); }.advanced-filters { grid-template-columns: repeat(3, minmax(160px, 1fr)); padding: 16px 0 20px; border-top: 1px dashed #e7eaf0; }.stats-metrics { margin-bottom: 18px; }.metric-card-value em { margin-left: 3px; font-size: 12px; font-style: normal; font-weight: 500; }.chart-grid { display: grid; grid-template-columns: 1.6fr 1fr; gap: 16px; }.chart-body { height: 278px; padding: 8px 12px 8px 5px; }.chart-period { padding: 5px 8px; border-radius: 5px; background: #f5f7fa; color: #7b879a; font-size: 10px; }.compare-card { margin-top: 16px; }.compare-body { height: 210px; padding: 0 20px 8px; }.detail-table { margin-top: 18px; overflow: hidden; }.table-pagination { display: flex; justify-content: flex-end; padding: 15px 18px; border-top: 1px solid var(--line); }
@media (max-width: 1280px) { .filter-grid, .primary-filters { grid-template-columns: repeat(3, minmax(150px, 1fr)); }.advanced-filters { grid-template-columns: repeat(3, minmax(150px, 1fr)); }.chart-grid { grid-template-columns: 1fr; } }
@media (max-width: 860px) { .filter-grid, .primary-filters, .advanced-filters { grid-template-columns: repeat(2, minmax(140px, 1fr)); }.date-filter { grid-column: span 2; }.filter-actions { justify-content: flex-start; } }
</style>
