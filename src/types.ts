export type WkdStatus = 'NEW_WKD' | 'VERIFY' | 'REVIEW' | 'APPROVED' | 'DISABLE_CONFIRM' | 'DISABLED'
export type ExecuteStage = 'pre_upgrade' | 'post_upgrade' | 'post_start' | 'post_init' | 'custom'
export type ExecutionType = 'AUTOMATED' | 'MANUAL'

export interface Wkd {
  id: string
  number?: string
  title: string
  machine: string
  machineIds?: string[]
  subsystem: string
  subsystemId?: string
  owner: string
  ownerId?: string
  stage: ExecuteStage | null
  customStageName?: string
  status: WkdStatus
  updatedAt: string
  createdAt: string
  project: string
  projectId?: string
  version: string
  versionId?: string
  description: string
  operation: string
  executionType?: ExecutionType
  activityScene?: string
  measureType?: string
  currentHandler?: string
  currentHandlerId?: string
  foundVersion?: string
  foundVersionId?: string
  plannedVersion?: string
  plannedVersionId?: string
  issueNo?: string
  requirementNo?: string
  operations?: { id?: string; position?: number; type: string; params: Record<string, any> }[]
  packageData?: Record<string, any>
}

export interface Session {
  id?: string
  username: string
  employeeId: string
  department?: string | null
  role: '开发人员' | '软件经理' | '项目管理员' | '系统管理员' | '项目成员'
  isSuperuser?: boolean
  permissions?: string[]
  demo?: boolean
}

export interface UserOption {
  id: string
  username: string
  employee_id: string
  department?: string | null
  email?: string | null
  global_role_id?: string | null
  global_role?: string | null
  role?: string
  [key: string]: unknown
}

export interface OptionItem {
  id: string
  name: string
  code?: string | null
  project_id?: string | null
  number?: string | null
  baseline_date?: string | null
  model?: string | null
  location?: string | null
  owner_id?: string | null
  status?: string | null
  created_at?: string | null
  updated_at?: string | null
  username?: string | null
  employee_id?: string | null
  email?: string | null
  description?: string | null
  built_in?: boolean
  [key: string]: unknown
}

export interface BootstrapOptions {
  projects: OptionItem[]
  versions: OptionItem[]
  machines: OptionItem[]
  subsystems: OptionItem[]
  users: UserOption[]
  roles: OptionItem[]
}

export interface WkdFieldChange {
  field: string
  label: string
  before: unknown
  after: unknown
}

export interface WkdHistoryItem {
  id: string
  action: string
  from_status: WkdStatus | null
  to_status: WkdStatus
  note: string | null
  changes?: WkdFieldChange[]
  operator: string
  created_at: string
}

export interface AttachmentItem {
  id: string
  filename: string
  size: number
  content_type?: string | null
  sha256?: string | null
  status?: 'UPLOADING' | 'READY'
  multipart?: boolean
  upload_session_id?: string | null
  created_at?: string
  url?: string
  progress?: number
  busy?: boolean
  error?: string
}

export interface ArtifactItem {
  id: string
  number: string
  filename: string
  project_id: string
  machine_id: string
  type: 'DEBUG' | 'RELEASE'
  size: number
  sha256: string
  builder_id: string
  created_at: string
  items: { wkd_id: string; position: number; snapshot?: unknown }[]
  demoContent?: string
  demoBlob?: Blob
}
