import { can, store } from './store'

export type BusinessResource = 'projects' | 'versions' | 'machines' | 'subsystems'

const businessPermissions: Record<Exclude<BusinessResource, 'projects'>, string> = {
  versions: 'business.version',
  machines: 'business.machine',
  subsystems: 'business.subsystem',
}

export function isGlobalAdmin() {
  return store.session?.isSuperuser === true || (store.demoMode && store.session?.role === '系统管理员')
}

export function hasBusinessAccess() {
  return Object.values(businessPermissions).some(permission => can(`${permission}.view`))
}

export function canViewBusiness(resource: BusinessResource) {
  return resource === 'projects' ? hasBusinessAccess() : can(`${businessPermissions[resource]}.view`)
}

export function canEditBusiness(resource: BusinessResource) {
  return resource === 'projects' ? isGlobalAdmin() : can(`${businessPermissions[resource]}.edit`)
}

export function hasSystemAccess() {
  return hasBusinessAccess() || can('project.member.view') || can('project.role.view')
}

export function firstSystemPath() {
  if (hasBusinessAccess()) return '/system/business'
  return can('project.member.view') ? '/system/members' : '/system/roles'
}

export function firstSystemPermission() {
  if (hasBusinessAccess()) return Object.values(businessPermissions).map(permission => `${permission}.view`).find(can) || ''
  if (can('project.member.view')) return 'project.member.view'
  return 'project.role.view'
}
