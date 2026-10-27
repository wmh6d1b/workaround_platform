import type { Wkd } from './types'

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

export class ApiError extends Error {
  constructor(public status: number, message: string, public payload?: unknown) {
    super(message)
  }
}

function detailMessage(payload: any, status: number) {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => item.msg || item.message || '参数校验失败').join('；')
  return payload?.message || `请求失败（${status}）`
}

async function parseError(response: Response) {
  const payload = await response.json().catch(() => null)
  return new ApiError(response.status, detailMessage(payload, response.status), payload)
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('wmp-token')
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/login')) window.dispatchEvent(new Event('wmp:unauthorized'))
    throw await parseError(response)
  }
  return response.status === 204 ? undefined as T : response.json()
}

export function queryString(values: Record<string, string | number | string[] | null | undefined>) {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach(item => { if (item) params.append(key, item) })
    else if (value !== '' && value !== null && value !== undefined) params.set(key, String(value))
  })
  const text = params.toString()
  return text ? `?${text}` : ''
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  async download(path: string) {
    const token = localStorage.getItem('wmp-token')
    const response = await fetch(`${API_BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : undefined })
    if (!response.ok) throw await parseError(response)
    return response.blob()
  },
}

export function formatDateTime(value?: string | null) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

export function formatBytes(size: number) {
  if (!Number.isFinite(size) || size < 0) return '—'
  if (size < 1024) return `${size} B`
  const units = ['KB', 'MB', 'GB']
  let value = size / 1024
  let unit = units[0]
  for (let index = 1; value >= 1024 && index < units.length; index++) {
    value /= 1024
    unit = units[index]
  }
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${unit}`
}

export function normalizeWkd(item: any): Wkd {
  const machines = Array.isArray(item.machines) ? item.machines : []
  const firstOperation = item.operations?.[0]?.type
  const operation = item.execution_type === 'MANUAL' ? '人工操作' : firstOperation === 'LINUX_COMMAND' ? 'Linux 命令' : firstOperation === 'SCRIPT' ? '脚本' : firstOperation === 'UPLOAD_FILE' ? '上传文件' : '未编排'
  return {
    id: item.id,
    number: item.number,
    title: item.title,
    description: item.description || '',
    machine: machines.map((machine: any) => machine.name).join('、') || item.machine || '—',
    machineIds: item.machine_ids || machines.map((machine: any) => machine.id),
    subsystem: item.subsystem || '—',
    subsystemId: item.subsystem_id,
    owner: item.owner || '—',
    ownerId: item.owner_id,
    stage: item.stage || null,
    customStageName: item.custom_stage_name,
    status: item.status,
    project: item.project || '',
    projectId: item.project_id,
    version: item.version || '',
    versionId: item.version_id,
    createdAt: formatDateTime(item.created_at || item.createdAt),
    updatedAt: formatDateTime(item.updated_at || item.updatedAt),
    operation,
    executionType: item.execution_type || item.executionType,
    operations: item.operations || [],
    packageData: item,
  }
}

export function displayNumber(item: Pick<Wkd, 'id' | 'number'>) {
  return item.number || item.id
}

export function saveBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function openDownload(url: string) {
  const link = document.createElement('a')
  link.href = url
  link.target = '_blank'
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

export function errorMessage(error: unknown, fallback = '操作失败') {
  return error instanceof Error ? error.message : fallback
}
