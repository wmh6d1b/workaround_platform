export type WkdTableKey = 'workbench' | 'debug-build' | 'release-build'

export interface WkdColumnOption {
  key: string
  label: string
  required?: boolean
}

export const wkdColumnOptions: WkdColumnOption[] = [
  { key: 'id', label: 'WKD 编号', required: true },
  { key: 'title', label: 'WKD 标题', required: true },
  { key: 'version', label: '所属版本' },
  { key: 'machine', label: '机台' },
  { key: 'subsystem', label: '子系统' },
  { key: 'owner', label: '责任人' },
  { key: 'currentHandler', label: '当前处理人' },
  { key: 'executionType', label: '执行类型' },
  { key: 'activityScene', label: '活动场景' },
  { key: 'measureType', label: '措施类型' },
  { key: 'stage', label: '执行阶段' },
  { key: 'status', label: '工作流状态' },
  { key: 'issueNo', label: '问题单号' },
  { key: 'requirementNo', label: '需求单号' },
  { key: 'foundVersion', label: '问题发现版本' },
  { key: 'plannedVersion', label: '规划解决版本' },
  { key: 'createdAt', label: '创建时间' },
  { key: 'updatedAt', label: '更新时间' },
]

export const defaultWkdColumns: Record<WkdTableKey, string[]> = {
  workbench: ['id', 'title', 'machine', 'subsystem', 'owner', 'stage', 'status'],
  'debug-build': ['id', 'title', 'machine', 'subsystem', 'owner', 'stage', 'status', 'updatedAt'],
  'release-build': ['id', 'title', 'machine', 'subsystem', 'owner', 'stage', 'status'],
}

const validKeys = new Set(wkdColumnOptions.map(item => item.key))
const requiredKeys = wkdColumnOptions.filter(item => item.required).map(item => item.key)

export function sanitizeWkdColumns(value: unknown, tableKey: WkdTableKey) {
  const requested = Array.isArray(value) ? value.filter((key): key is string => typeof key === 'string' && validKeys.has(key)) : []
  const selected = new Set([...requiredKeys, ...requested])
  const ordered = wkdColumnOptions.map(item => item.key).filter(key => selected.has(key))
  return ordered.length ? ordered : [...defaultWkdColumns[tableKey]]
}

function storageKey(tableKey: WkdTableKey, userId: string) {
  return `wmp:table-columns:${userId}:${tableKey}`
}

export function loadWkdColumns(tableKey: WkdTableKey, userId: string) {
  try {
    const saved = localStorage.getItem(storageKey(tableKey, userId))
    return saved ? sanitizeWkdColumns(JSON.parse(saved), tableKey) : [...defaultWkdColumns[tableKey]]
  } catch {
    return [...defaultWkdColumns[tableKey]]
  }
}

export function saveWkdColumns(tableKey: WkdTableKey, userId: string, columns: string[]) {
  try {
    localStorage.setItem(storageKey(tableKey, userId), JSON.stringify(sanitizeWkdColumns(columns, tableKey)))
  } catch {
    // 浏览器禁用本地存储时仍保留当前会话内的字段配置。
  }
}
