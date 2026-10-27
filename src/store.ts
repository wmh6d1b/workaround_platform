import { computed, reactive } from 'vue'
import type { BootstrapOptions, Session } from './types'
import { api, queryString } from './api'
import { demoOptions } from './data/mock'

function readSession(): Session | null {
  try {
    const saved = localStorage.getItem('wmp-session')
    return saved ? JSON.parse(saved) as Session : null
  } catch {
    return null
  }
}

const saved = readSession()
const cloneDemoOptions = () => JSON.parse(JSON.stringify(demoOptions)) as BootstrapOptions

export const store = reactive({
  session: saved,
  demoMode: saved?.demo ?? (!saved ? false : !localStorage.getItem('wmp-token')),
  projectId: 'demo-project',
  versionId: 'demo-version',
  project: '晶圆检测设备',
  version: 'V3.2.0',
  options: cloneDemoOptions(),
  optionsLoading: false,
  optionsReady: false,
  sidebarCollapsed: false,
})

const DEMO_PERMISSIONS: Record<string, string[]> = {
  开发人员: ['home.view','wkd.view','wkd.create','wkd.edit','wkd.submit','wkd.disable','wkd.note','build.debug.view','build.debug.build','build.release.view','build.release.download','files.upload','files.download'],
  软件经理: ['home.view','wkd.view','wkd.edit','wkd.review','wkd.disable','wkd.note','build.debug.view','build.debug.build','build.release.view','build.release.download','files.upload','files.download'],
  项目管理员: ['*'],
  系统管理员: ['*'],
}

export function can(permission: string) {
  if (!store.session) return false
  const permissions = store.demoMode ? DEMO_PERMISSIONS[store.session.role] || [] : store.session.permissions || []
  return store.session.isSuperuser === true || permissions.includes('*') || permissions.includes(permission)
}

export const isAdmin = computed(() => can('build.release.build'))

function persistSession() {
  if (store.session) localStorage.setItem('wmp-session', JSON.stringify(store.session))
}

export function login(session: Session, token?: string) {
  store.session = session
  store.demoMode = session.demo === true
  store.optionsReady = false
  persistSession()
  if (token) localStorage.setItem('wmp-token', token)
  else localStorage.removeItem('wmp-token')
}

export async function refreshPermissions() {
  if (store.demoMode || !store.session || !localStorage.getItem('wmp-token')) return
  const result = await api.get<{ permissions: string[] }>(`/auth/permissions${queryString({ project_id: store.projectId })}`)
  store.session.permissions = result.permissions
  persistSession()
}

export async function ensureOptions(force = false) {
  if (store.optionsLoading) return
  if (!force && store.optionsReady) return
  store.optionsLoading = true
  try {
    if (store.demoMode) {
      store.options = cloneDemoOptions()
    } else {
      store.options = await api.get<BootstrapOptions>(`/bootstrap/options${queryString({ project_id: force ? store.projectId : undefined })}`)
    }
    const project = store.options.projects.find(item => item.id === store.projectId) || store.options.projects[0]
    if (project) {
      store.projectId = project.id
      store.project = project.name
    }
    const versions = store.options.versions.filter(item => item.project_id === store.projectId)
    const version = versions.find(item => item.id === store.versionId) || versions[0]
    store.versionId = version?.id || ''
    store.version = version?.number || version?.name || ''
    store.optionsReady = true
  } finally {
    store.optionsLoading = false
  }
}

export async function selectProject(projectId: string) {
  const project = store.options.projects.find(item => item.id === projectId)
  if (!project) return
  store.projectId = project.id
  store.project = project.name
  store.versionId = ''
  store.version = ''
  await ensureOptions(true)
  await refreshPermissions()
}

export function logout() {
  store.session = null
  store.demoMode = false
  store.optionsReady = false
  localStorage.removeItem('wmp-session')
  localStorage.removeItem('wmp-token')
}
