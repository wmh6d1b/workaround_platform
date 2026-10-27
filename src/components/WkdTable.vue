<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { TableInstance } from 'element-plus'
import type { Wkd } from '../types'
import type { WkdFilterKey, WkdFilterOptions, WkdFilters } from '../utils/wkdFilters'
import { emptyWkdFilters, wkdStageLabel } from '../utils/wkdFilters'
import { displayNumber } from '../api'
import StatusTag from './StatusTag.vue'
import TableHeaderFilter from './TableHeaderFilter.vue'

const props = withDefaults(defineProps<{
  rows: Wkd[]
  selectable?: boolean
  preselect?: boolean
  columns?: string[]
  showIndex?: boolean
  loading?: boolean
  filterable?: WkdFilterKey[]
  filters?: WkdFilters
  filterOptions?: WkdFilterOptions
}>(), {
  selectable: false, preselect: false, columns: () => ['id', 'title', 'machine', 'subsystem', 'owner', 'stage', 'status'],
  showIndex: true, loading: false, filterable: () => [], filters: emptyWkdFilters, filterOptions: undefined,
})
const emit = defineEmits<{
  selection: [rows: Wkd[]]
  filterChange: [payload: { key: WkdFilterKey; values: string[] }]
}>()
const router = useRouter()
const tableRef = ref<TableInstance>()
const has = computed(() => (key: string) => props.columns.includes(key))
const canFilter = (key: WkdFilterKey) => props.filterable.includes(key)
const filterValues = (key: WkdFilterKey) => props.filters[key] || []
const filterOptions = (key: WkdFilterKey) => props.filterOptions?.[key] || []
const canSelect = (row: Wkd) => !['NEW_WKD', 'DISABLED'].includes(row.status)
const open = (row: Wkd) => router.push(`/wkd/${row.id}`)

watch(() => props.rows, async rows => {
  await nextTick()
  tableRef.value?.clearSelection()
  if (props.selectable && props.preselect) rows.filter(canSelect).forEach(row => tableRef.value?.toggleRowSelection(row, true))
}, { immediate: true })
</script>

<template>
  <el-table ref="tableRef" v-loading="loading" :data="rows" class="data-table wkd-table" @selection-change="emit('selection', $event)" row-key="id">
    <el-table-column v-if="selectable" type="selection" width="44" :selectable="canSelect" align="center" />
    <el-table-column v-if="showIndex" type="index" label="序号" width="58" align="center" />
    <el-table-column v-if="has('id')" label="WKD 编号" min-width="150">
      <template #default="{ row }"><button class="table-link id-link" @click="open(row)">{{ displayNumber(row) }}</button></template>
    </el-table-column>
    <el-table-column v-if="has('title')" prop="title" label="WKD 标题" min-width="235" show-overflow-tooltip>
      <template #default="{ row }"><button class="table-link title-cell" @click="open(row)"><span>{{ row.title }}</span><small>{{ row.operation }}</small></button></template>
    </el-table-column>
    <el-table-column v-if="has('machine')" prop="machine" label="机台" min-width="112" show-overflow-tooltip>
      <template v-if="canFilter('machine')" #header><TableHeaderFilter label="机台" :values="filterValues('machine')" :options="filterOptions('machine')" @apply="emit('filterChange', { key: 'machine', values: $event })" /></template>
    </el-table-column>
    <el-table-column v-if="has('subsystem')" prop="subsystem" label="子系统" min-width="112">
      <template v-if="canFilter('subsystem')" #header><TableHeaderFilter label="子系统" :values="filterValues('subsystem')" :options="filterOptions('subsystem')" @apply="emit('filterChange', { key: 'subsystem', values: $event })" /></template>
    </el-table-column>
    <el-table-column v-if="has('owner')" prop="owner" label="责任人" width="100">
      <template v-if="canFilter('owner')" #header><TableHeaderFilter label="责任人" :values="filterValues('owner')" :options="filterOptions('owner')" @apply="emit('filterChange', { key: 'owner', values: $event })" /></template>
    </el-table-column>
    <el-table-column v-if="has('stage')" label="执行阶段" width="112">
      <template v-if="canFilter('stage')" #header><TableHeaderFilter label="执行阶段" :values="filterValues('stage')" :options="filterOptions('stage')" @apply="emit('filterChange', { key: 'stage', values: $event })" /></template>
      <template #default="{ row }"><span class="text-secondary">{{ wkdStageLabel(row) }}</span></template>
    </el-table-column>
    <el-table-column v-if="has('status')" prop="status" label="工作流状态" width="140">
      <template v-if="canFilter('status')" #header><TableHeaderFilter label="工作流状态" :values="filterValues('status')" :options="filterOptions('status')" @apply="emit('filterChange', { key: 'status', values: $event })" /></template>
      <template #default="{ row }"><StatusTag :status="row.status" /></template>
    </el-table-column>
    <el-table-column v-if="has('updatedAt')" prop="updatedAt" label="更新时间" width="145"><template #default="{ row }"><span class="muted">{{ row.updatedAt }}</span></template></el-table-column>
    <template #empty><div class="empty-table"><el-icon :size="28"><Document /></el-icon><p>没有找到符合条件的 WKD</p></div></template>
  </el-table>
</template>
