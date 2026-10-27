import type { TableFilterOption } from '../components/TableHeaderFilter.vue'
import type { Wkd, WkdStatus } from '../types'

export type WkdFilterKey = 'machine' | 'subsystem' | 'owner' | 'stage' | 'status'
export type WkdFilters = Record<WkdFilterKey, string[]>
export type WkdFilterOptions = Record<WkdFilterKey, TableFilterOption[]>

export const statusLabels: Record<WkdStatus, string> = {
  NEW_WKD: '新建规避措施', VERIFY: '自验证', REVIEW: '软件经理审核', APPROVED: '审核通过',
  DISABLE_CONFIRM: '软件经理确认禁用', DISABLED: '禁用',
}
export const stageLabels: Record<string, string> = {
  pre_upgrade: '升级前', post_upgrade: '升级后', post_start: '启动后', post_init: '初始化后', custom: '自定义', MANUAL: '人工操作',
}
export const stageFilterOptions: TableFilterOption[] = ['pre_upgrade', 'post_upgrade', 'post_start', 'post_init', 'custom', 'MANUAL'].map(value => ({ value, label: stageLabels[value] }))
export const statusFilterOptions: TableFilterOption[] = Object.entries(statusLabels).map(([value, label]) => ({ value, label }))

export function emptyWkdFilters(): WkdFilters {
  return { machine: [], subsystem: [], owner: [], stage: [], status: [] }
}
export function wkdStageKey(row: Wkd) {
  return row.executionType === 'MANUAL' ? 'MANUAL' : row.stage || ''
}
export function wkdStageLabel(row: Wkd) {
  return row.executionType === 'MANUAL' ? '人工操作' : row.customStageName || stageLabels[row.stage || ''] || '未选择'
}
export function hasWkdFilters(filters: WkdFilters) {
  return Object.values(filters).some(values => values.length)
}
function matches(values: string[], candidates: Array<string | null | undefined>) {
  return !values.length || candidates.some(candidate => candidate && values.includes(candidate))
}
export function filterWkdRows(rows: Wkd[], search: string, filters: WkdFilters) {
  const query = search.trim().toLowerCase()
  return rows.filter(row => {
    const matchesSearch = !query || row.id.toLowerCase().includes(query) || !!row.number?.toLowerCase().includes(query) || row.title.toLowerCase().includes(query)
    return matchesSearch
      && matches(filters.machine, [...(row.machineIds || []), row.machine])
      && matches(filters.subsystem, [row.subsystemId, row.subsystem])
      && matches(filters.owner, [row.ownerId, row.owner])
      && matches(filters.stage, [wkdStageKey(row)])
      && matches(filters.status, [row.status])
  })
}

function uniqueOptions(entries: Array<{ value?: string; label?: string }>) {
  return [...new Map(entries.filter(item => item.value).map(item => [item.value!, { value: item.value!, label: item.label || item.value! }])).values()]
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
}
export function optionsFromWkdRows(rows: Wkd[]): WkdFilterOptions {
  const presentStages = new Set<string>(rows.map(wkdStageKey))
  const presentStatuses = new Set<WkdStatus>(rows.map(row => row.status))
  return {
    machine: uniqueOptions(rows.flatMap(row => (row.machineIds?.length ? row.machineIds : [row.machine]).map(value => ({ value, label: row.machineIds?.length ? value : row.machine })))),
    subsystem: uniqueOptions(rows.map(row => ({ value: row.subsystemId || row.subsystem, label: row.subsystem }))),
    owner: uniqueOptions(rows.map(row => ({ value: row.ownerId || row.owner, label: row.owner }))),
    stage: stageFilterOptions.filter(option => presentStages.has(option.value)),
    status: statusFilterOptions.filter(option => presentStatuses.has(option.value as WkdStatus)),
  }
}
