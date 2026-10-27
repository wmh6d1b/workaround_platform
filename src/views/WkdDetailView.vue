<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, displayNumber, errorMessage, formatBytes, formatDateTime, normalizeWkd, openDownload, saveBlob } from '../api'
import { persistDemoWkds, wkdList } from '../data/mock'
import { hasRichContent, sanitizeRichText } from '../richtext'
import { can, ensureOptions, store } from '../store'
import { statePanels } from '../components/wkd/states'
import { clearWkdDraft, readWkdDraft, saveWkdDraft } from '../utils/wkdDrafts'
import type { AttachmentItem, ExecuteStage, OptionItem, WkdFieldChange, WkdHistoryItem, WkdStatus } from '../types'

type OperationType = 'UPLOAD_FILE' | 'LINUX_COMMAND' | 'SCRIPT'
type UploadOperationFile = { name: string; content: string }
type Operation = { id: string; type: OperationType; params: Record<string, any> }
type DetailForm = {
  id: string
  number: string
  title: string
  description: string
  issue_no: string | null
  requirement_no: string | null
  project_id: string
  project: string
  version_id: string
  version: string
  found_version_id: string | null
  planned_version_id: string | null
  subsystem_id: string
  owner_id: string
  owner: string
  current_handler_id: string | null
  current_handler: string | null
  machine_ids: string[]
  execution_type: 'AUTOMATED' | 'MANUAL'
  activity_scene: string
  measure_type: string
  remark: string | null
  stage: ExecuteStage | ''
  custom_stage_name: string | null
  status: WkdStatus
  lock_version: number
  operations: Operation[]
}

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const dragged = ref<number | null>(null)
const activePanels = ref<string[]>([])
const activeDetailTab = ref<'flow' | 'attachments' | 'history'>('flow')
const historyRows = ref<WkdHistoryItem[]>([])
const attachments = ref<AttachmentItem[]>([])
const reviewDialogOpen = ref(false)
const reviewAction = ref<'submit_review' | 'request_disable'>('submit_review')
const reviewersLoading = ref(false)
const reviewerOptions = ref<OptionItem[]>([])
const reviewerId = ref('')
const fileInput = ref<HTMLInputElement>()
let savedSnapshot: Record<string, unknown> = {}
const isNew = computed(() => route.name === 'wkd-new' || route.params.id === 'new')
const demoMode = computed(() => store.demoMode)
const notes = reactive<Record<WkdStatus, string>>({ NEW_WKD: '', VERIFY: '', REVIEW: '', APPROVED: '', DISABLE_CONFIRM: '', DISABLED: '' })

const statusMeta: Record<WkdStatus, { label: string; tone: string }> = {
  NEW_WKD: { label: '新建规避措施', tone: 'neutral' },
  VERIFY: { label: '自验证', tone: 'warning' },
  REVIEW: { label: '软件经理审核', tone: 'processing' },
  APPROVED: { label: '审核通过', tone: 'success' },
  DISABLE_CONFIRM: { label: '软件经理确认禁用', tone: 'warning' },
  DISABLED: { label: '禁用', tone: 'disabled' },
}
const stageLabels: Record<string, string> = { pre_upgrade: '升级前', post_upgrade: '升级后', post_start: '启动后', post_init: '初始化后', custom: '自定义' }
const operationMeta: Record<OperationType, { label: string; icon: string; tone: string }> = {
  UPLOAD_FILE: { label: '上传文件', icon: 'UploadFilled', tone: 'blue' },
  LINUX_COMMAND: { label: 'Linux 命令', icon: 'Monitor', tone: 'violet' },
  SCRIPT: { label: 'Python / Shell 脚本', icon: 'Document', tone: 'green' },
}
const actionLabels: Record<string, string> = {
  CREATE: '创建规避措施', SUBMIT_VERIFY: '提交自验证', SUBMIT_REVIEW: '提交软件经理审核',
  APPROVE: '审核通过', REJECT: '审核驳回', REQUEST_DISABLE: '发起禁用', CONFIRM_DISABLE: '确认禁用',
  REJECT_DISABLE: '拒绝禁用', DISABLE: '禁用规避措施',
}
const auditFieldLabels: Record<string, string> = {
  title: 'WKD 标题', description: '规避措施描述', issue_no: '问题单号', requirement_no: '需求单号',
  found_version: '问题发现版本', planned_version: '规划解决版本', subsystem: '所属子系统', machines: '关联机台',
  execution_type: '执行类型', activity_scene: '活动场景', measure_type: '类型', remark: '备注',
  stage: '执行阶段', custom_stage_name: '自定义阶段名称', operations: '原子操作编排',
}

function blankForm(): DetailForm {
  return {
    id: '', number: '保存后自动生成', title: '', description: '', issue_no: null, requirement_no: null,
    project_id: store.projectId, project: store.project, version_id: store.versionId, version: store.version,
    found_version_id: null, planned_version_id: null, subsystem_id: '', owner_id: store.session?.id || '', owner: store.session?.name || '',
    current_handler_id: store.session?.id || null, current_handler: store.session?.name || null, machine_ids: [],
    execution_type: 'AUTOMATED', activity_scene: '常规版本升级', measure_type: '事前规避措施', remark: null,
    stage: 'post_start', custom_stage_name: null, status: 'NEW_WKD', lock_version: 1, operations: [],
  }
}
const form = reactive<DetailForm>(blankForm())

const isCurrentHandler = computed(() => store.session?.isSuperuser || (demoMode.value && store.session?.role === '系统管理员') || form.current_handler_id === store.session?.id)
const canEdit = computed(() => (isNew.value ? can('wkd.create') : ['NEW_WKD', 'VERIFY'].includes(form.status) && can('wkd.edit')) && isCurrentHandler.value)
const canReviewCurrent = computed(() => can('wkd.review') && isCurrentHandler.value)
const canEditCurrentNote = computed(() => {
  if (form.status === 'DISABLED' || !can('wkd.note')) return false
  if (['NEW_WKD', 'VERIFY'].includes(form.status)) return canEdit.value
  if (['REVIEW', 'DISABLE_CONFIRM'].includes(form.status)) return canReviewCurrent.value
  return form.status === 'APPROVED' && can('wkd.disable')
})
const stepActive = computed(() => ({ NEW_WKD: 0, VERIFY: 1, REVIEW: 2, APPROVED: 3, DISABLE_CONFIRM: 4, DISABLED: 5 }[form.status]))
const reviewDialogCopy = computed(() => reviewAction.value === 'request_disable'
  ? { title: '选择软件经理确认禁用', intro: '提交后，所选软件经理将成为当前处理人，负责确认或拒绝禁用。', button: '提交禁用确认' }
  : { title: '选择软件经理审核', intro: '提交后，所选软件经理将成为当前处理人，负责审核通过或驳回。', button: '确认并提交审核' })
const versionOptions = computed(() => store.options.versions.filter(item => item.project_id === form.project_id))
const machineOptions = computed(() => store.options.machines.filter(item => item.project_id === form.project_id))
const subsystemOptions = computed(() => store.options.subsystems.filter(item => item.project_id === form.project_id))
const ownerName = computed(() => form.owner || store.options.users.find(item => item.id === form.owner_id)?.name || store.session?.name || '当前用户')
const currentHandlerName = computed(() => form.current_handler || store.options.users.find(item => item.id === form.current_handler_id)?.name || '暂无待处理人')
const stateVisits = computed(() => {
  if (isNew.value) return [{ key: 'new', status: 'NEW_WKD' as WkdStatus, occurrence: 1, entries: [] as WkdHistoryItem[], current: true }]
  const visits: { key: string; status: WkdStatus; occurrence: number; entries: WkdHistoryItem[]; current: boolean }[] = []
  const counts: Partial<Record<WkdStatus, number>> = {}
  const chronological = historyRows.value.map((item, index) => ({ item, index })).sort((a, b) => a.item.created_at.localeCompare(b.item.created_at) || a.index - b.index)
  for (const { item } of chronological) {
    const previous = visits.at(-1)
    const entersState = !previous || (!['SAVE', 'STATE_NOTE'].includes(item.action) && item.to_status !== previous.status)
    if (entersState) {
      if (previous && item.note) previous.entries.push(item)
      counts[item.to_status] = (counts[item.to_status] || 0) + 1
      visits.push({ key: item.id, status: item.to_status, occurrence: counts[item.to_status]!, entries: [], current: false })
      visits.at(-1)!.entries.push(previous ? { ...item, id: `${item.id}-arrival`, note: null } : item)
    } else {
      visits.at(-1)!.entries.push(item)
    }
  }
  return visits.map((visit, index) => ({ ...visit, current: index === visits.length - 1 && visit.status === form.status }))
})
const currentVisitKey = computed(() => stateVisits.value.find(visit => visit.current)?.key || stateVisits.value.at(-1)?.key || '')
watch(currentVisitKey, key => { activePanels.value = key ? [key] : [] }, { immediate: true })

function applyDetail(data: any) {
  Object.assign(form, blankForm(), data)
  form.stage = data.stage || ''
  form.machine_ids = [...(data.machine_ids || [])]
  form.operations = (data.operations || []).map((item: any) => ({ id: item.id || crypto.randomUUID(), type: item.type, params: { ...item.params, ...(item.type === 'UPLOAD_FILE' ? { files: (item.params.files || []).map((file: UploadOperationFile) => ({ name: file.name, content: file.content || '' })) } : {}) } }))
}

function applyDemo(id: string) {
  const source = wkdList.find(item => item.id === id)
  if (!source) throw new Error('Demo 中不存在这条 WKD，请返回工作台重新选择')
  applyDetail({
    id: source.id, number: displayNumber(source), title: source.title, description: source.description,
    issue_no: `BUG-${source.id.slice(-6)}`, requirement_no: null,
    project_id: source.projectId || store.projectId, project: source.project, version_id: source.versionId || store.versionId, version: source.version,
    found_version_id: 'demo-version-31', planned_version_id: source.versionId || store.versionId,
    subsystem_id: source.subsystemId || store.options.subsystems[0]?.id, owner_id: source.ownerId || store.options.users[0]?.id, owner: source.owner,
    current_handler_id: ['NEW_WKD', 'VERIFY'].includes(source.status) ? source.ownerId || store.options.users[0]?.id : ['REVIEW', 'DISABLE_CONFIRM'].includes(source.status) ? 'demo-owner-lin' : null,
    current_handler: ['NEW_WKD', 'VERIFY'].includes(source.status) ? source.owner : ['REVIEW', 'DISABLE_CONFIRM'].includes(source.status) ? '林舟' : null,
    machine_ids: source.machineIds || [], execution_type: source.executionType || 'AUTOMATED', activity_scene: '常规版本升级',
    measure_type: '事前规避措施', remark: null, stage: source.stage || '', custom_stage_name: source.stage === 'custom' ? 'after_service_check' : null,
    status: source.status, lock_version: 1,
    operations: source.operations?.length ? source.operations : source.executionType === 'MANUAL' ? [] : [
      { id: 'demo-op-1', type: 'UPLOAD_FILE', params: { target_path: '/opt/wmp/patches', overwrite: '覆盖', permission: '0644', files: [{ name: 'config.yaml', content: 'enabled: true\n' }] } },
      { id: 'demo-op-2', type: 'LINUX_COMMAND', params: { command: 'systemctl reload wmp-agent', workdir: '/opt/wmp', timeout: '30', exit_code: '0' } },
    ],
  })
  historyRows.value = [{ id: `demo-history-${id}`, action: 'CREATE', from_status: null, to_status: 'NEW_WKD', note: null, operator: source.owner, created_at: source.createdAt }]
  const visits: { status: WkdStatus; action: string }[] = source.status === 'DISABLED'
    ? [{ status: 'DISABLED', action: 'DISABLE' }]
    : source.status === 'NEW_WKD' ? [] : [
        { status: 'VERIFY', action: 'SUBMIT_VERIFY' },
        ...(['REVIEW', 'APPROVED', 'DISABLE_CONFIRM'].includes(source.status) ? [{ status: 'REVIEW' as WkdStatus, action: 'SUBMIT_REVIEW' }] : []),
        ...(['APPROVED', 'DISABLE_CONFIRM'].includes(source.status) ? [{ status: 'APPROVED' as WkdStatus, action: 'APPROVE' }] : []),
        ...(source.status === 'DISABLE_CONFIRM' ? [{ status: 'DISABLE_CONFIRM' as WkdStatus, action: 'REQUEST_DISABLE' }] : []),
      ]
  visits.forEach((visit, index) => historyRows.value.push({ id: `demo-history-${id}-${index}`, action: visit.action, from_status: index ? visits[index - 1].status : 'NEW_WKD', to_status: visit.status, note: visit.status === 'DISABLED' ? 'Demo 禁用原因' : null, operator: source.owner, created_at: source.updatedAt }))
}

async function loadDetail() {
  if (isNew.value) {
    Object.assign(form, blankForm())
    form.owner_id = store.session?.id || store.options.users.find(item => item.name === store.session?.name)?.id || store.options.users[0]?.id || ''
    form.current_handler_id = form.owner_id
    form.current_handler = form.owner
    historyRows.value = []
    attachments.value = []
    return
  }
  loading.value = true
  try {
    if (demoMode.value) applyDemo(String(route.params.id))
    else {
      const [detail, history, files] = await Promise.all([
        api.get<Record<string, unknown>>(`/wkds/${route.params.id}`),
        api.get<WkdHistoryItem[]>(`/wkds/${route.params.id}/history`),
        api.get<AttachmentItem[]>(`/files/attachments?wkd_id=${encodeURIComponent(String(route.params.id))}`),
      ])
      applyDetail(detail)
      historyRows.value = history
      attachments.value = files
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, 'WKD 加载失败'))
  } finally {
    loading.value = false
  }
}

function draftUserId() { return store.session?.id || store.session?.name || 'anonymous' }
function draftWkdId() { return isNew.value ? 'new' : form.id }
function clearLocalDraft(status = form.status, visitKey = currentVisitKey.value) {
  clearWkdDraft(draftUserId(), draftWkdId(), status, visitKey)
}
function restoreLocalDraft() {
  const draft = readWkdDraft(draftUserId(), draftWkdId(), form.status, currentVisitKey.value, form.lock_version)
  if (!draft) return
  Object.assign(form, JSON.parse(JSON.stringify(draft.form)))
  notes[form.status] = sanitizeRichText(draft.note)
  ElMessage.info('已恢复保存在当前浏览器的本地草稿')
}

onMounted(async () => {
  try { await ensureOptions() } catch (error) { ElMessage.error(errorMessage(error, '基础选项加载失败')) }
  await loadDetail()
  if (!isNew.value) savedSnapshot = auditSnapshot()
  restoreLocalDraft()
})

watch(() => [store.projectId, store.versionId] as const, ([projectId, versionId]) => {
  if (!isNew.value) return
  const project = store.options.projects.find(item => item.id === projectId)
  const version = store.options.versions.find(item => item.id === versionId)
  form.project_id = projectId
  form.project = project?.name || store.project
  form.version_id = versionId
  form.version = version?.number || version?.name || store.version
  form.found_version_id = null
  form.planned_version_id = null
  form.subsystem_id = ''
  form.machine_ids = []
})

function addOperation(type: OperationType) {
  if (!canEdit.value || form.execution_type === 'MANUAL') return
  if (!form.stage) return ElMessage.warning('请先选择执行阶段')
  const defaults: Record<OperationType, Record<string, any>> = {
    UPLOAD_FILE: { target_path: '', overwrite: '覆盖', permission: '0644', files: [{ name: '', content: '' }] },
    LINUX_COMMAND: { command: '', workdir: '/opt/wmp', timeout: '30', exit_code: '0' },
    SCRIPT: { script_type: 'Python', script: '', arguments: '', timeout: '60' },
  }
  form.operations.push({ id: crypto.randomUUID(), type, params: JSON.parse(JSON.stringify(defaults[type])) })
}
function addUploadFile(operation: Operation) {
  operation.params.files ||= []
  operation.params.files.push({ name: '', content: '' })
}
function removeUploadFile(operation: Operation, index: number | string) {
  operation.params.files.splice(Number(index), 1)
}

function dropOperation(index: number) {
  if (dragged.value === null || dragged.value === index || !canEdit.value) return
  const [item] = form.operations.splice(dragged.value, 1)
  form.operations.splice(index, 0, item)
  dragged.value = null
}

async function executionTypeChanged(value: string) {
  if (value === 'MANUAL' && (form.operations.length || form.stage)) {
    try {
      await ElMessageBox.confirm('切换为人工操作后，已选择的执行阶段和已编排的原子操作将被清空，且无法恢复。是否继续？', '确认切换执行类型', { type: 'warning', confirmButtonText: '清空并切换', cancelButtonText: '取消' })
      form.operations = []
      form.stage = ''
      form.custom_stage_name = null
    } catch { form.execution_type = 'AUTOMATED' }
  }
}

function validateForm() {
  if (!form.title.trim() || !form.description.trim()) return '请填写 WKD 标题和规避措施描述'
  if (!form.project_id || !form.version_id || !form.subsystem_id) return '请确认顶部上下文中的所属项目和所属版本，并选择子系统'
  if (!form.machine_ids.length) return '请至少关联一个机台'
  if (!form.owner_id) return '请选择责任人'
  if (!form.issue_no?.trim() && !form.requirement_no?.trim()) return '问题单号和需求单号不能同时为空'
  if (form.issue_no?.trim() && !form.found_version_id) return '填写问题单号时，问题发现版本必填'
  if (!form.activity_scene || !form.measure_type) return '请选择活动场景和类型'
  if (form.execution_type === 'AUTOMATED') {
    if (!form.stage) return '自动化执行必须选择执行阶段'
    if (form.stage === 'custom' && !form.custom_stage_name?.trim()) return '请填写自定义阶段名称'
    if (!form.operations.length) return '自动化执行至少需要编排一个原子操作'
    for (const [index, operation] of form.operations.entries()) {
      if (operation.type === 'UPLOAD_FILE') {
        if (!operation.params.target_path?.trim()?.startsWith('/') || operation.params.target_path.includes('..')) return `第 ${index + 1} 个操作需要安全的绝对目标路径`
        const files = operation.params.files as UploadOperationFile[] | undefined
        if (!files?.length) return `第 ${index + 1} 个上传操作至少需要一个文件`
        if (files.some(file => !file.name.trim() || file.name.includes('/') || file.name.includes('\\'))) return `第 ${index + 1} 个上传操作存在空文件名或非法文件名`
        if (new Set(files.map(file => file.name.trim())).size !== files.length) return `第 ${index + 1} 个上传操作内文件名不能重复`
      }
      if (operation.type === 'LINUX_COMMAND' && !operation.params.command?.trim()) return `第 ${index + 1} 个操作缺少 Linux 命令`
      if (operation.type === 'SCRIPT' && !operation.params.script?.trim()) return `第 ${index + 1} 个操作缺少脚本内容`
    }
  }
  return ''
}

function payload() {
  return {
    title: form.title.trim(), description: form.description.trim(), issue_no: form.issue_no?.trim() || null,
    requirement_no: form.requirement_no?.trim() || null, project_id: form.project_id, version_id: form.version_id,
    found_version_id: form.found_version_id || null, planned_version_id: form.planned_version_id || null,
    subsystem_id: form.subsystem_id, machine_ids: form.machine_ids, owner_id: form.owner_id,
    execution_type: form.execution_type, activity_scene: form.activity_scene, measure_type: form.measure_type,
    remark: form.remark?.trim() || null, stage: form.execution_type === 'AUTOMATED' ? form.stage : null,
    custom_stage_name: form.execution_type === 'AUTOMATED' && form.stage === 'custom' ? form.custom_stage_name?.trim() : null,
    operations: form.execution_type === 'AUTOMATED' ? form.operations.map(item => ({ type: item.type, params: item.params })) : [],
    lock_version: isNew.value ? null : form.lock_version,
  }
}

function auditSnapshot(): Record<string, unknown> {
  const versionName = (id: string | null) => {
    const item = store.options.versions.find(option => option.id === id)
    return item ? item.number || item.name : null
  }
  return {
    title: form.title.trim(), description: form.description.trim(), issue_no: form.issue_no?.trim() || null,
    requirement_no: form.requirement_no?.trim() || null, found_version: versionName(form.found_version_id),
    planned_version: versionName(form.planned_version_id),
    subsystem: store.options.subsystems.find(item => item.id === form.subsystem_id)?.name || null,
    machines: machineOptions.value.filter(item => form.machine_ids.includes(item.id)).map(item => item.name).sort(),
    execution_type: form.execution_type === 'AUTOMATED' ? '自动化执行' : '人工操作',
    activity_scene: form.activity_scene, measure_type: form.measure_type, remark: form.remark?.trim() || null,
    stage: form.execution_type === 'AUTOMATED' ? stageLabels[form.stage] || null : null,
    custom_stage_name: form.execution_type === 'AUTOMATED' && form.stage === 'custom' ? form.custom_stage_name?.trim() || null : null,
    operations: form.execution_type === 'AUTOMATED' ? form.operations.map((operation, index) => {
      const params = Object.entries(operation.params).sort(([left], [right]) => left.localeCompare(right)).map(([key, value]) => `${key}=${value}`).join('，')
      return `${String(index + 1).padStart(2, '0')} ${operationMeta[operation.type].label} · ${params}`
    }) : [],
  }
}

function diffAuditSnapshots(before: Record<string, unknown>, after: Record<string, unknown>): WkdFieldChange[] {
  return Object.entries(auditFieldLabels)
    .filter(([field]) => JSON.stringify(before[field]) !== JSON.stringify(after[field]))
    .map(([field, label]) => ({ field, label, before: before[field], after: after[field] }))
}

function formatChangeValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '空'
  if (Array.isArray(value)) return value.length ? value.join('、') : '空'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function flowEntries(entries: WkdHistoryItem[]) {
  return entries.filter(item => !!item.note)
}

function upsertDemoWkd() {
  const now = new Date()
  const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  if (isNew.value) {
    const id = `WKD${date}${String(wkdList.length + 1).padStart(4, '0')}`
    form.id = id
    form.number = id
    form.status = 'NEW_WKD'
    wkdList.unshift(normalizeWkd({ ...payload(), id, number: id, status: form.status, created_at: now.toISOString(), updated_at: now.toISOString(), project: form.project, version: store.options.versions.find(item => item.id === form.version_id)?.name, subsystem: store.options.subsystems.find(item => item.id === form.subsystem_id)?.name, owner: store.options.users.find(item => item.id === form.owner_id)?.name, machines: machineOptions.value.filter(item => form.machine_ids.includes(item.id)) }))
    historyRows.value.unshift({ id: crypto.randomUUID(), action: 'CREATE', from_status: null, to_status: 'NEW_WKD', note: hasRichContent(notes.NEW_WKD) ? sanitizeRichText(notes.NEW_WKD) : null, operator: store.session?.name || '当前用户', created_at: now.toISOString() })
  } else {
    const item = wkdList.find(row => row.id === form.id)
    if (item) Object.assign(item, normalizeWkd({ ...payload(), id: form.id, number: form.number, status: form.status, created_at: item.createdAt, updated_at: now.toISOString(), project: form.project, version: store.options.versions.find(item => item.id === form.version_id)?.name, subsystem: store.options.subsystems.find(item => item.id === form.subsystem_id)?.name, owner: store.options.users.find(item => item.id === form.owner_id)?.name, machines: machineOptions.value.filter(item => form.machine_ids.includes(item.id)) }))
  }
  form.version = store.options.versions.find(item => item.id === form.version_id)?.name || ''
  persistDemoWkds()
}

async function persist(): Promise<string | null> {
  const creating = isNew.value
  if (creating) {
    const validation = validateForm()
    if (validation) { ElMessage.warning(validation); return null }
  }
  saving.value = true
  const currentPayload = payload()
  const currentSnapshot = auditSnapshot()
  try {
    if (creating) {
      if (demoMode.value) upsertDemoWkd()
      else applyDetail(await api.post<Record<string, unknown>>('/wkds', { ...currentPayload, note: hasRichContent(notes.NEW_WKD) ? sanitizeRichText(notes.NEW_WKD) : null }))
      savedSnapshot = currentSnapshot
      clearLocalDraft('NEW_WKD', 'new')
      await router.replace(`/wkd/${form.id}`)
      ElMessage.success('WKD 已创建，可继续上传附件')
    } else {
      saveWkdDraft(draftUserId(), draftWkdId(), {
        status: form.status, visitKey: currentVisitKey.value, lockVersion: form.lock_version,
        form: JSON.parse(JSON.stringify(form)), note: sanitizeRichText(notes[form.status]), savedAt: new Date().toISOString(),
      })
      ElMessage.success('草稿已保存在当前浏览器，未提交后端')
    }
    return form.id
  } catch (error) {
    ElMessage.error(errorMessage(error, creating ? '创建失败' : '本地草稿保存失败'))
    return null
  } finally { saving.value = false }
}

async function save() { await persist() }

async function openReviewDialog(action: 'submit_review' | 'request_disable') {
  reviewAction.value = action
  reviewerId.value = ''
  reviewDialogOpen.value = true
  reviewersLoading.value = true
  try {
    reviewerOptions.value = demoMode.value
      ? store.options.users.filter(item => item.role === '软件经理')
      : await api.get<OptionItem[]>(`/wkds/reviewers?project_id=${encodeURIComponent(form.project_id)}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '软件经理列表加载失败'))
  } finally { reviewersLoading.value = false }
}

async function confirmReviewAssignment() {
  if (!reviewerId.value) return ElMessage.warning('请选择软件经理')
  await transition(reviewAction.value, reviewerId.value)
  if (['REVIEW', 'DISABLE_CONFIRM'].includes(form.status)) reviewDialogOpen.value = false
}

async function transition(action: string, managerId?: string) {
  const creating = isNew.value
  const previousStatus = form.status
  const previousVisitKey = currentVisitKey.value
  const previousHandlerId = form.current_handler_id
  const previousHandlerName = currentHandlerName.value
  const note = sanitizeRichText(notes[previousStatus])
  if (['submit_review', 'request_disable'].includes(action) && !managerId) return ElMessage.warning('请先选择软件经理')
  if (note.length > 10_000_000) return ElMessage.warning('状态说明内容过大，请减少图片或文字')
  if (['approve', 'reject', 'disable', 'request_disable', 'confirm_disable', 'reject_disable'].includes(action) && !hasRichContent(note)) {
    return ElMessage.warning(['disable', 'request_disable'].includes(action) ? '请填写禁用原因' : '请填写审核或确认意见')
  }
  if (['disable', 'confirm_disable'].includes(action)) {
    try { await ElMessageBox.confirm('禁用后不可恢复，WKD 将转为最终只读状态。是否继续？', '确认禁用', { type: 'warning', confirmButtonText: '确认禁用', cancelButtonText: '取消' }) } catch { return }
  }
  if (['submit_verify', 'submit_review'].includes(action)) {
    const validation = validateForm()
    if (validation) return ElMessage.warning(validation)
    if (creating && !await persist()) return
  }
  const currentSnapshot = auditSnapshot()
  const changes: WkdFieldChange[] = !creating && ['submit_verify', 'submit_review'].includes(action) ? diffAuditSnapshots(savedSnapshot, currentSnapshot) : []
  const next = { submit_verify: 'VERIFY', submit_review: 'REVIEW', approve: 'APPROVED', reject: 'VERIFY', request_disable: 'DISABLE_CONFIRM', confirm_disable: 'DISABLED', reject_disable: 'APPROVED', disable: 'DISABLED' } as Record<string, WkdStatus>
  saving.value = true
  try {
    if (!demoMode.value) applyDetail(await api.post(`/wkds/${form.id}/transitions/${action}`, {
      note: hasRichContent(note) ? note : null, lock_version: form.lock_version, manager_id: managerId || null,
      data: ['submit_verify', 'submit_review'].includes(action) ? payload() : null,
    }))
    else {
      if (['submit_verify', 'submit_review'].includes(action)) upsertDemoWkd()
      const manager = reviewerOptions.value.find(item => item.id === managerId)
      const managerAction = ['submit_review', 'request_disable'].includes(action)
      const nextHandlerId = managerAction ? managerId || null : ['submit_verify', 'reject'].includes(action) ? form.owner_id : null
      const nextHandlerName = managerAction ? manager?.name || null : ['submit_verify', 'reject'].includes(action) ? form.owner : null
      form.current_handler_id = nextHandlerId
      form.current_handler = nextHandlerName
      form.status = next[action]
      form.lock_version += 1
      const item = wkdList.find(row => row.id === form.id)
      if (item) item.status = form.status
      persistDemoWkds()
    }
    if (previousHandlerId !== form.current_handler_id) changes.push({ field: 'current_handler', label: '当前处理人', before: previousHandlerName === '暂无待处理人' ? null : previousHandlerName, after: form.current_handler })
    historyRows.value.unshift({ id: crypto.randomUUID(), action: action.toUpperCase(), from_status: previousStatus, to_status: next[action], note: hasRichContent(note) ? note : null, changes, operator: store.session?.name || '当前用户', created_at: new Date().toISOString() })
    savedSnapshot = currentSnapshot
    clearLocalDraft(previousStatus, previousVisitKey)
    notes[previousStatus] = ''
    ElMessage.success(`已流转至「${statusMeta[next[action]].label}」`)
  } catch (error) { ElMessage.error(errorMessage(error, '状态流转失败')) }
  finally { saving.value = false }
}

function chooseFiles() {
  if (isNew.value) return ElMessage.warning('请先保存并创建 WKD，再上传附件')
  fileInput.value?.click()
}

async function uploadFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  const oversized = files.find(file => file.size > 500 * 1024 * 1024)
  if (oversized) return ElMessage.error(`附件「${oversized.name}」超过单文件 500 MB 限制`)
  uploading.value = true
  let completed = 0
  for (const file of files) {
    try {
      if (demoMode.value) {
        attachments.value.push({ id: crypto.randomUUID(), filename: file.name, size: file.size, content_type: file.type, created_at: new Date().toISOString(), url: URL.createObjectURL(file) })
      } else {
        const upload = await api.post<{ object_key: string; upload_url: string }>('/files/upload-url', { filename: file.name, size: file.size, content_type: file.type || null, wkd_id: form.id, category: 'WKD' })
        const response = await fetch(upload.upload_url, { method: 'PUT', headers: file.type ? { 'Content-Type': file.type } : undefined, body: file })
        if (!response.ok) throw new Error(`文件上传失败（${response.status}）`)
        const item = await api.post<AttachmentItem>('/files/complete', { object_key: upload.object_key, filename: file.name, size: file.size, content_type: file.type || null, sha256: null, wkd_id: form.id, category: 'WKD' })
        attachments.value.push(item)
      }
      completed += 1
    } catch (error) { ElMessage.error(`${file.name}：${errorMessage(error, '上传失败')}`) }
  }
  uploading.value = false
  if (completed) ElMessage.success(`已上传 ${completed} 个附件`)
}

async function downloadAttachment(item: AttachmentItem) {
  try {
    if (demoMode.value) {
      if (item.url) openDownload(item.url)
      else saveBlob(item.filename, new Blob(['WMP Demo attachment'], { type: 'text/plain' }))
    } else {
      const result = await api.get<{ url: string }>(`/files/attachments/${item.id}/download`)
      openDownload(result.url)
    }
  } catch (error) { ElMessage.error(errorMessage(error, '附件下载失败')) }
}
</script>

<template>
  <div v-loading="loading" class="detail-page">
    <div class="detail-topline">
      <button class="back-button" title="返回" @click="router.back()"><el-icon><ArrowLeft /></el-icon></button>
      <div class="detail-identity">
        <div><h1>{{ isNew ? '新建规避措施' : form.title }}</h1><span class="detail-status" :class="statusMeta[form.status].tone"><i />{{ statusMeta[form.status].label }}</span><span v-if="demoMode" class="demo-badge">DEMO</span></div>
        <p><span class="mono">{{ isNew ? '编号按日自动生成' : form.number }}</span><span>·</span>{{ form.project || '未选择项目' }}<template v-if="form.version"> / {{ form.version }}</template></p>
      </div>
      <div class="detail-actions">
        <el-button v-if="canEdit" :loading="saving" @click="save"><el-icon><Check /></el-icon>{{ isNew ? '保存并创建' : '保存' }}</el-button>
        <el-button v-if="form.status==='NEW_WKD' && can('wkd.submit') && isCurrentHandler" type="primary" :loading="saving" @click="transition('submit_verify')">提交自验证<el-icon><Right /></el-icon></el-button>
        <template v-if="form.status==='REVIEW' && canReviewCurrent"><el-button :loading="saving" @click="transition('reject')">审核驳回</el-button><el-button type="primary" :loading="saving" @click="transition('approve')"><el-icon><Check /></el-icon>审核通过</el-button></template>
        <template v-if="form.status==='DISABLE_CONFIRM' && canReviewCurrent"><el-button :loading="saving" @click="transition('reject_disable')">拒绝禁用</el-button><el-button type="danger" :loading="saving" @click="transition('confirm_disable')"><el-icon><CircleClose /></el-icon>确认禁用</el-button></template>
        <el-button v-if="!isNew && ['NEW_WKD','VERIFY'].includes(form.status) && can('wkd.disable') && isCurrentHandler" type="danger" plain :loading="saving" @click="transition('disable')"><el-icon><CircleClose /></el-icon>禁用</el-button>
      </div>
    </div>

    <section class="surface-card lifecycle-card">
      <div class="lifecycle-title"><span>WKD 生命周期</span><small>状态提交后不可随意回退，所有操作均保留审计记录</small></div>
      <el-steps :active="stepActive" align-center finish-status="success" process-status="process"><el-step title="新建规避措施" description="NEW_WKD" /><el-step title="自验证" description="VERIFY" /><el-step title="软件经理审核" description="REVIEW" /><el-step title="审核通过" description="APPROVED" /><el-step title="确认禁用" description="DISABLE_CONFIRM" /><el-step title="禁用" description="DISABLED" /></el-steps>
      <div v-if="form.status==='DISABLE_CONFIRM'" class="disabled-banner"><el-icon><CircleClose /></el-icon>等待软件经理确认禁用，业务字段保持只读</div>
      <div v-if="form.status==='DISABLED'" class="disabled-banner"><el-icon><CircleClose /></el-icon>该 WKD 已禁用，当前为最终只读状态</div>
    </section>

    <div class="detail-workspace">
      <div class="left-column">
        <section class="surface-card operation-section" :class="{disabled: form.execution_type==='MANUAL'}">
          <div class="card-header"><div><h3>原子操作编排</h3><p>拖拽卡片调整执行顺序，所有关联机台共用此配置</p></div><div class="stage-select"><span>执行阶段</span><el-select v-model="form.stage" :disabled="!canEdit || form.execution_type==='MANUAL'" placeholder="请选择阶段" style="width:150px"><el-option v-for="(label,key) in stageLabels" :key="key" :label="label" :value="key" /></el-select></div></div>
          <div v-if="form.stage==='custom'" class="custom-stage"><span>自定义阶段名称</span><el-input v-model="form.custom_stage_name" :disabled="!canEdit" placeholder="当前版本内唯一，将作为脚本阶段参数" /></div>
          <div v-if="form.execution_type==='MANUAL'" class="manual-empty"><el-icon><User /></el-icon><strong>人工操作</strong><p>当前执行类型无需选择阶段或编排原子操作</p></div>
          <div v-else class="operation-layout">
            <div class="operation-canvas" :class="{readonly:!canEdit}">
              <div v-if="!form.operations.length" class="operation-empty"><el-icon><Plus /></el-icon><p>从右侧添加第一个原子操作</p></div>
              <div v-for="(op,index) in form.operations" :key="op.id" class="operation-card" :draggable="canEdit" @dragstart="dragged=index" @dragend="dragged=null" @dragover.prevent @drop="dropOperation(index)">
                <div class="operation-card-head"><span v-if="canEdit" class="drag-handle"><el-icon><Rank /></el-icon></span><span class="operation-number">{{ String(index+1).padStart(2,'0') }}</span><span class="operation-type-icon" :class="operationMeta[op.type].tone"><el-icon><component :is="operationMeta[op.type].icon" /></el-icon></span><strong>{{ operationMeta[op.type].label }}</strong><el-button v-if="canEdit" text title="删除操作" class="operation-delete" @click="form.operations.splice(index,1)"><el-icon><Delete /></el-icon></el-button></div>
                <div class="operation-params">
                  <template v-if="op.type==='UPLOAD_FILE'"><label class="wide">目标目录<el-input v-model="op.params.target_path" :disabled="!canEdit" placeholder="/root/temp" /></label><label>覆盖策略<el-select v-model="op.params.overwrite" :disabled="!canEdit"><el-option label="覆盖" value="覆盖" /><el-option label="跳过已存在文件" value="跳过" /></el-select></label><label>文件权限<el-input v-model="op.params.permission" :disabled="!canEdit" placeholder="0644" /></label><div class="upload-operation-files wide"><div class="upload-files-heading"><div><strong>文件列表</strong><span>同一操作内的文件会上传到上述目录</span></div><el-button v-if="canEdit" size="small" @click="addUploadFile(op)"><el-icon><Plus /></el-icon>添加文件</el-button></div><div v-for="(file,fileIndex) in op.params.files" :key="fileIndex" class="upload-file-editor"><div class="upload-file-name"><el-input v-model="file.name" :disabled="!canEdit" placeholder="文件名，例如 hello.py" /><el-button v-if="canEdit" text type="danger" title="移除文件" :disabled="op.params.files.length===1" @click="removeUploadFile(op,fileIndex)"><el-icon><Delete /></el-icon></el-button></div><el-input v-model="file.content" type="textarea" :rows="3" :disabled="!canEdit" placeholder="输入文件内容，例如 print(&quot;hello&quot;)" /></div></div></template>
                  <template v-else-if="op.type==='LINUX_COMMAND'"><label class="wide">执行命令<el-input v-model="op.params.command" :disabled="!canEdit" placeholder="输入 Linux 命令" /></label><label>工作目录<el-input v-model="op.params.workdir" :disabled="!canEdit" /></label><label>超时（秒）<el-input v-model="op.params.timeout" :disabled="!canEdit" /></label><label>期望退出码<el-input v-model="op.params.exit_code" :disabled="!canEdit" /></label></template>
                  <template v-else><label>脚本类型<el-select v-model="op.params.script_type" :disabled="!canEdit"><el-option label="Python" value="Python" /><el-option label="Shell" value="Shell" /></el-select></label><label>执行参数<el-input v-model="op.params.arguments" :disabled="!canEdit" /></label><label class="wide">脚本内容<el-input v-model="op.params.script" type="textarea" :rows="3" :disabled="!canEdit" /></label><label>超时（秒）<el-input v-model="op.params.timeout" :disabled="!canEdit" /></label></template>
                </div>
              </div>
            </div>
            <aside class="operation-palette"><span class="palette-title">原子操作</span><p>添加至当前阶段末尾</p><div v-for="(meta,type) in operationMeta" :key="type" class="palette-item"><div><span class="operation-type-icon" :class="meta.tone"><el-icon><component :is="meta.icon" /></el-icon></span><strong>{{ meta.label }}</strong></div><el-button size="small" :disabled="!canEdit || !form.stage" @click="addOperation(type)"><el-icon><Plus /></el-icon>添加到当前阶段</el-button></div></aside>
          </div>
        </section>

        <section class="surface-card state-panel detail-tabs-card">
          <div class="detail-tab-bar" role="tablist" aria-label="WKD 详细信息">
            <button type="button" role="tab" :aria-selected="activeDetailTab==='flow'" :class="{active:activeDetailTab==='flow'}" @click="activeDetailTab='flow'"><el-icon><Document /></el-icon>详细流程</button>
            <button type="button" role="tab" :aria-selected="activeDetailTab==='attachments'" :class="{active:activeDetailTab==='attachments'}" @click="activeDetailTab='attachments'"><el-icon><Paperclip /></el-icon>附件<span v-if="attachments.length" class="tab-count">{{ attachments.length }}</span></button>
            <button type="button" role="tab" :aria-selected="activeDetailTab==='history'" :class="{active:activeDetailTab==='history'}" @click="activeDetailTab='history'"><el-icon><Clock /></el-icon>历史记录<span v-if="historyRows.length" class="tab-count">{{ historyRows.length }}</span></button>
          </div>

          <div v-show="activeDetailTab==='flow'" class="detail-tab-panel" role="tabpanel">
            <div class="tab-section-heading"><div><h3>状态说明与流转</h3><p>每次进入状态都会新增独立面板，仅展示说明与流转意见</p></div></div>
            <el-collapse v-model="activePanels">
              <el-collapse-item v-for="visit in stateVisits" :key="visit.key" :name="visit.key" :class="{ 'current-visit': visit.current }">
                <template #title><span class="collapse-state-dot" :class="statusMeta[visit.status].tone" /><span>{{ statusMeta[visit.status].label }}</span><small>第 {{ visit.occurrence }} 次 · {{ visit.status }}</small><em v-if="visit.current">当前</em></template>
                <div v-if="flowEntries(visit.entries).length" class="history-list"><div v-for="item in flowEntries(visit.entries)" :key="item.id" class="history-row"><div><strong>{{ actionLabels[item.action] || item.action }}</strong><span>{{ item.operator }} · {{ formatDateTime(item.created_at) }}</span></div><div v-if="item.note" class="rich-text" v-html="sanitizeRichText(item.note)" /></div></div>
                <component :is="statePanels[form.status]" v-if="visit.current" v-model="notes[form.status]" :disabled="!canEditCurrentNote" />
              </el-collapse-item>
            </el-collapse>
          </div>

          <div v-show="activeDetailTab==='attachments'" class="detail-tab-panel" role="tabpanel">
            <div class="attachment-section"><div class="attachment-heading"><div><h3>附件</h3><p>支持多文件，不限类型，单个文件不超过 500 MB</p></div><el-button size="small" :disabled="isNew || !can('files.upload')" :loading="uploading" @click="chooseFiles"><el-icon><Paperclip /></el-icon>添加附件</el-button><input ref="fileInput" type="file" multiple hidden @change="uploadFiles" /></div><div v-if="attachments.length" class="attachment-list"><div v-for="item in attachments" :key="item.id"><span><el-icon><Document /></el-icon></span><div><strong>{{ item.filename }}</strong><small>{{ formatBytes(item.size) }}<template v-if="item.created_at"> · {{ formatDateTime(item.created_at) }}</template></small></div><el-button v-if="can('files.download')" text type="primary" title="下载附件" @click="downloadAttachment(item)"><el-icon><Download /></el-icon></el-button></div></div><div v-else class="attachment-empty"><el-icon><Paperclip /></el-icon><span>{{ isNew ? '首次保存后可上传附件' : '暂无附件，点击右上角“添加附件”上传' }}</span></div></div>
          </div>

          <div v-show="activeDetailTab==='history'" class="detail-tab-panel" role="tabpanel">
            <div class="tab-section-heading"><div><h3>全部历史记录</h3><p>状态流转、状态说明和属性字段变化均按时间保留</p></div></div>
            <el-timeline v-if="historyRows.length" class="full-history"><el-timeline-item v-for="item in historyRows" :key="item.id" :timestamp="formatDateTime(item.created_at)" placement="top"><div class="history-record-card"><div class="history-record-title"><strong>{{ actionLabels[item.action] || item.action }}</strong><span>{{ item.operator }} · {{ statusMeta[item.to_status]?.label || item.to_status }}</span></div><div v-if="item.note" class="rich-text" v-html="sanitizeRichText(item.note)" /><div v-if="item.changes?.length" class="history-changes"><div class="change-header"><span>字段</span><span>变更前</span><span>变更后</span></div><div v-for="change in item.changes" :key="change.field" class="change-row"><strong>{{ change.label }}</strong><span :title="formatChangeValue(change.before)">{{ formatChangeValue(change.before) }}</span><span :title="formatChangeValue(change.after)">{{ formatChangeValue(change.after) }}</span></div></div></div></el-timeline-item></el-timeline><el-empty v-else description="暂无历史记录" />
          </div>
        </section>
        <section v-if="form.status==='VERIFY' && can('wkd.submit') && isCurrentHandler" class="surface-card review-assignment-bar">
          <div class="review-assignment-icon"><el-icon><User /></el-icon></div>
          <div><strong>指派软件经理审核</strong><p>完整数据和自验证说明将随本次流转一次提交</p></div>
          <el-button type="primary" :loading="saving" @click="openReviewDialog('submit_review')">选择软件经理并提交<el-icon><Right /></el-icon></el-button>
        </section>
        <section v-if="form.status==='APPROVED' && can('wkd.disable')" class="surface-card review-assignment-bar">
          <div class="review-assignment-icon"><el-icon><CircleClose /></el-icon></div>
          <div><strong>发起软件经理确认禁用</strong><p>填写禁用申请说明并选择软件经理，审核通过前不会直接禁用</p></div>
          <el-button type="danger" plain :loading="saving" @click="openReviewDialog('request_disable')">选择软件经理并发起<el-icon><Right /></el-icon></el-button>
        </section>
      </div>

      <aside class="surface-card property-panel">
        <div class="card-header"><div><h3>字段属性</h3><p>{{ canEdit?'当前状态允许编辑':'当前状态字段只读' }}</p></div><el-icon><Lock v-if="!canEdit" /><Edit v-else /></el-icon></div>
        <el-form label-position="top" class="property-form">
          <div class="form-section-title">基本信息</div>
          <el-form-item label="WKD 标题" required><el-input v-model="form.title" :disabled="!canEdit" maxlength="200" placeholder="简要说明需要规避的问题" /></el-form-item>
          <el-form-item label="规避措施描述" required><el-input v-model="form.description" type="textarea" :rows="3" :disabled="!canEdit" placeholder="说明问题现象、触发条件和规避方式" /></el-form-item>
          <div class="property-grid"><el-form-item label="问题单号"><el-input v-model="form.issue_no" :disabled="!canEdit" /></el-form-item><el-form-item label="需求单号"><el-input v-model="form.requirement_no" :disabled="!canEdit" placeholder="两项至少填一项" /></el-form-item><el-form-item label="问题发现版本" :required="!!form.issue_no"><el-select v-model="form.found_version_id" :disabled="!canEdit" filterable clearable placeholder="输入版本号辅助选择"><el-option v-for="item in versionOptions" :key="item.id" :label="item.number || item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="规划解决版本"><el-select v-model="form.planned_version_id" :disabled="!canEdit" filterable clearable placeholder="请选择版本"><el-option v-for="item in versionOptions" :key="item.id" :label="item.number || item.name" :value="item.id" /></el-select></el-form-item></div>

          <div class="form-section-title">业务归属<small>项目与所属版本由顶部上下文自动带入</small></div>
          <div class="property-grid"><el-form-item label="所属项目" required><el-input :model-value="form.project" disabled><template #suffix><el-icon><Lock /></el-icon></template></el-input></el-form-item><el-form-item label="所属版本" required><el-input :model-value="form.version" disabled><template #suffix><el-icon><Lock /></el-icon></template></el-input></el-form-item></div>
          <el-form-item label="关联机台" required><el-select v-model="form.machine_ids" multiple :disabled="!canEdit" placeholder="可关联多个机台"><el-option v-for="item in machineOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
          <div class="property-grid"><el-form-item label="所属子系统" required><el-select v-model="form.subsystem_id" :disabled="!canEdit" filterable placeholder="请选择子系统"><el-option v-for="item in subsystemOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="责任人"><div class="owner-fixed"><span>{{ ownerName.slice(0,1) }}</span><strong>{{ ownerName }}</strong><small><el-icon><Lock /></el-icon>创建人固定</small></div></el-form-item></div>
          <el-form-item label="当前处理人"><div class="current-handler-fixed" :class="{empty:!form.current_handler_id}"><span><el-icon><User /></el-icon></span><strong>{{ currentHandlerName }}</strong><small><el-icon><Lock /></el-icon>随状态流转更新</small></div></el-form-item>

          <div class="form-section-title">执行属性</div>
          <el-form-item label="执行类型" required><el-select v-model="form.execution_type" :disabled="!canEdit" @change="executionTypeChanged"><el-option label="自动化执行" value="AUTOMATED" /><el-option label="人工操作" value="MANUAL" /></el-select></el-form-item>
          <div class="property-grid"><el-form-item label="活动场景" required><el-select v-model="form.activity_scene" :disabled="!canEdit"><el-option v-for="item in ['首版本部署','ES集成活动','常规版本升级']" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="类型" required><el-select v-model="form.measure_type" :disabled="!canEdit"><el-option label="事前规避措施" value="事前规避措施" /><el-option label="事后恢复措施" value="事后恢复措施" /></el-select></el-form-item></div>
          <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" :disabled="!canEdit" placeholder="非必填" /></el-form-item>

        </el-form>
      </aside>
    </div>

    <el-dialog v-model="reviewDialogOpen" :title="reviewDialogCopy.title" width="460px" :close-on-click-modal="false">
      <div class="review-dialog-intro"><el-icon><User /></el-icon><p>{{ reviewDialogCopy.intro }}</p></div>
      <el-form label-position="top" v-loading="reviewersLoading"><el-form-item label="软件经理" required><el-select v-model="reviewerId" filterable placeholder="请选择软件经理" style="width:100%"><el-option v-for="item in reviewerOptions" :key="item.id" :label="item.name" :value="item.id"><div class="reviewer-option"><strong>{{ item.name }}</strong><span>{{ item.employee_id || item.email }}</span></div></el-option></el-select></el-form-item></el-form>
      <template #footer><el-button @click="reviewDialogOpen=false">取消</el-button><el-button type="primary" :disabled="!reviewerId" :loading="saving" @click="confirmReviewAssignment">{{ reviewDialogCopy.button }}</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.detail-topline { display:flex; align-items:flex-start; gap:13px; margin:4px 0 20px; }
.back-button { width:34px; height:34px; border:1px solid var(--line); background:#fff; border-radius:8px; color:#667085; flex-shrink:0; cursor:pointer; }
.detail-identity { flex:1; min-width:0; }
.detail-identity>div { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.detail-identity h1 { font-size:20px; margin:0; letter-spacing:-.3px; }
.detail-identity p { display:flex; gap:8px; color:#98a2b3; font-size:10px; margin:6px 0 0; }
.detail-actions { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
.detail-actions .el-button+.el-button { margin-left:0; }
.detail-status { display:inline-flex; align-items:center; gap:5px; font-size:10px; border-radius:5px; padding:4px 8px; white-space:nowrap; }
.detail-status i { width:5px; height:5px; border-radius:50%; background:currentColor; }
.detail-status.neutral { background:#f2f4f7; color:#667085; }.detail-status.warning { background:#fff5e5; color:#b66a09; }.detail-status.processing { background:#edf0ff; color:#315efb; }.detail-status.success { background:#ecf8f2; color:#16865b; }.detail-status.disabled { background:#f2f4f7; color:#8b95a5; }
.demo-badge { font-size:8px; letter-spacing:1px; background:#fff4e5; color:#b66a09; padding:3px 5px; border-radius:4px; }
.lifecycle-card { padding:18px 28px 20px; margin-bottom:17px; }
.lifecycle-title { display:flex; align-items:center; justify-content:space-between; margin-bottom:18px; }.lifecycle-title>span { font-size:12px; font-weight:600; }.lifecycle-title small { color:#a0a8b7; font-size:9px; }
.lifecycle-card :deep(.el-step__title) { font-size:11px; }.lifecycle-card :deep(.el-step__description) { font-size:8px; }.lifecycle-card :deep(.el-step__head.is-process) { color:#315efb; border-color:#315efb; }.lifecycle-card :deep(.el-step__title.is-process) { color:#315efb; }
.disabled-banner { display:flex; align-items:center; justify-content:center; gap:6px; background:#f5f6f8; color:#7a8494; font-size:10px; border-radius:6px; padding:8px; margin-top:12px; }
.detail-workspace { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(350px,.85fr); gap:17px; align-items:start; }
.left-column { display:flex; flex-direction:column; gap:17px; min-width:0; }
.card-header { display:flex; justify-content:space-between; align-items:center; gap:12px; }.card-header h3 { font-size:13px; margin:0; }.card-header p { color:#98a2b3; font-size:9px; margin:5px 0 0; }.card-header>.el-icon { color:#98a2b3; }
.operation-section,.state-panel { padding:19px 20px; }.operation-section.disabled { background:#fafbfc; }
.stage-select { display:flex; align-items:center; gap:9px; }.stage-select>span,.custom-stage>span { font-size:10px; color:#7a8494; white-space:nowrap; }
.custom-stage { display:flex; align-items:center; gap:10px; background:#f6f8ff; border-radius:7px; padding:11px 12px; margin-top:15px; }.custom-stage .el-input { max-width:360px; }
.operation-layout { display:grid; grid-template-columns:minmax(0,1fr) 190px; gap:15px; margin-top:17px; }
.operation-canvas { min-width:0; display:flex; flex-direction:column; gap:10px; }.operation-empty { min-height:155px; border:1px dashed #dce2ec; border-radius:8px; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#a0a8b7; font-size:10px; }.operation-empty .el-icon { font-size:22px; margin-bottom:6px; }
.operation-card { border:1px solid #e3e8f0; border-radius:9px; background:#fff; overflow:hidden; }.operation-card[draggable=true] { cursor:grab; }.operation-card[draggable=true]:active { cursor:grabbing; }.operation-card-head { display:flex; align-items:center; gap:8px; padding:10px 12px; background:#fafbfc; border-bottom:1px solid #edf0f4; }.operation-card-head strong { font-size:11px; font-weight:600; }.drag-handle { color:#b0b8c5; display:flex; }.operation-number { color:#98a2b3; font-size:9px; font-variant-numeric:tabular-nums; }.operation-delete { margin-left:auto; color:#a0a8b7; }
.operation-type-icon { width:25px; height:25px; display:inline-grid; place-items:center; border-radius:6px; flex-shrink:0; }.operation-type-icon.blue { color:#315efb; background:#edf0ff; }.operation-type-icon.violet { color:#7957d5; background:#f3efff; }.operation-type-icon.green { color:#16865b; background:#ecf8f2; }
.operation-params { display:grid; grid-template-columns:1fr 1fr; gap:10px 12px; padding:12px; }.operation-params label { display:flex; flex-direction:column; gap:5px; color:#7a8494; font-size:9px; min-width:0; }.operation-params .wide { grid-column:1/-1; }
.upload-operation-files { border-top:1px dashed #e3e8f0; padding-top:11px; }.upload-files-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:9px; }.upload-files-heading>div { display:flex; flex-direction:column; gap:3px; }.upload-files-heading strong { color:#475467; font-size:10px; }.upload-files-heading span { color:#98a2b3; font-size:8px; }.upload-file-editor { padding:9px; margin-top:8px; border:1px solid #e8ecf2; border-radius:7px; background:#fafbfc; }.upload-file-name { display:flex; align-items:center; gap:5px; margin-bottom:7px; }.upload-file-name .el-button { flex-shrink:0; }.upload-file-editor :deep(textarea) { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:10px; line-height:1.6; }
.operation-palette { border-left:1px solid #edf0f4; padding-left:15px; }.palette-title { font-size:11px; font-weight:600; }.operation-palette>p { color:#a0a8b7; font-size:9px; margin:4px 0 13px; }.palette-item { padding:10px 0 13px; border-bottom:1px solid #f0f2f5; }.palette-item:last-child { border-bottom:0; }.palette-item>div { display:flex; gap:8px; align-items:center; margin-bottom:9px; }.palette-item strong { font-size:10px; font-weight:500; }.palette-item .el-button { width:100%; font-size:9px; }
.manual-empty { min-height:210px; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#98a2b3; }.manual-empty>.el-icon { font-size:28px; margin-bottom:10px; }.manual-empty strong { color:#667085; font-size:13px; }.manual-empty p { font-size:10px; }
.detail-tabs-card { padding-top:0; overflow:hidden; }
.detail-tab-bar { display:flex; align-items:center; gap:4px; margin:0 -20px 18px; padding:8px 12px 0; background:#f7f8fa; border-bottom:1px solid var(--line); }
.detail-tab-bar button { position:relative; display:flex; align-items:center; justify-content:center; gap:6px; min-height:40px; padding:0 15px; border:0; background:transparent; color:#7a8494; font-size:11px; font-weight:500; cursor:pointer; transition:color .18s,background .18s; border-radius:7px 7px 0 0; }
.detail-tab-bar button:hover { color:#344054; background:#f0f2f5; }
.detail-tab-bar button.active { color:#315efb; background:#fff; font-weight:600; }
.detail-tab-bar button.active::after { content:''; position:absolute; left:14px; right:14px; bottom:-1px; height:2px; border-radius:2px; background:#315efb; }
.detail-tab-bar .el-icon { font-size:14px; }.tab-count { min-width:17px; height:17px; display:inline-grid; place-items:center; padding:0 4px; border-radius:9px; background:#e9edf3; color:#667085; font-size:8px; }.detail-tab-bar button.active .tab-count { background:#edf0ff; color:#315efb; }
.detail-tab-panel { min-height:160px; }.tab-section-heading { margin-bottom:15px; }.tab-section-heading h3,.attachment-heading h3 { margin:0; color:#344054; font-size:13px; }.tab-section-heading p,.attachment-heading p { margin:5px 0 0; color:#98a2b3; font-size:9px; font-weight:400; }
.state-panel { padding-bottom:18px; }.state-panel>.card-header { margin-bottom:15px; }.state-panel :deep(.el-collapse) { border:0; }.state-panel :deep(.el-collapse-item) { margin-bottom:10px; }.state-panel :deep(.el-collapse-item:last-child) { margin-bottom:0; }.state-panel :deep(.el-collapse-item__header) { height:42px; line-height:1; padding:0 13px; background:#eceff3; border:1px solid #dfe4ea; border-radius:7px; color:#475467; font-size:11px; font-weight:600; cursor:pointer; transition:background .18s,border-color .18s; }.state-panel :deep(.el-collapse-item__header:hover) { background:#e4e8ee; border-color:#cfd6df; }.state-panel :deep(.el-collapse-item__header.is-active) { background:#e7ebf0; }.state-panel :deep(.current-visit .el-collapse-item__header) { border-color:#bdc9dc; }.state-panel :deep(.el-collapse-item__wrap) { border:0; background:transparent; }.state-panel :deep(.el-collapse-item__content) { padding:12px 3px 4px; }.state-panel :deep(.el-collapse-item__title) { display:flex; align-items:center; min-width:0; }.state-panel :deep(.el-collapse-item__title) small { color:#8a94a3; font-size:8px; font-weight:400; margin-left:9px; }.state-panel :deep(.el-collapse-item__title) em { font-size:8px; font-style:normal; font-weight:500; color:#315efb; background:#f5f7ff; border-radius:4px; padding:3px 5px; margin-left:8px; }.collapse-state-dot { width:7px; height:7px; border-radius:50%; margin-right:8px; background:#98a2b3; flex-shrink:0; }.collapse-state-dot.warning { background:#f2ad4c; }.collapse-state-dot.processing { background:#315efb; }.collapse-state-dot.success { background:#20ad78; }.collapse-state-dot.disabled { background:#7a8494; }
.state-note-editor { border-top:1px dashed #e0e5ec; padding-top:13px; margin-top:4px; }.state-note-editor>label { display:block; font-size:10px; color:#667085; margin-bottom:7px; }.editor-toolbar { display:flex; align-items:center; gap:4px; border:1px solid #dfe4eb; border-bottom:0; border-radius:7px 7px 0 0; background:#f8f9fb; padding:6px 8px; }.editor-toolbar button { width:27px; height:25px; border:0; border-radius:4px; background:transparent; color:#475467; cursor:pointer; }.editor-toolbar button:hover { background:#e9edf3; }.editor-toolbar>span { flex:1; }.editor-toolbar>label { display:flex; align-items:center; gap:5px; color:#667085; font-size:9px; cursor:pointer; }.editor-toolbar input { width:24px; height:22px; padding:1px; border:0; background:transparent; cursor:pointer; }.rich-editor { min-height:120px; max-height:420px; overflow:auto; border:1px solid #dfe4eb; border-radius:0 0 7px 7px; padding:11px 12px; outline:none; color:#344054; background:#fff; font-size:11px; line-height:1.75; white-space:pre-wrap; }.rich-editor:focus { border-color:#9db3ec; box-shadow:0 0 0 2px #eef2ff; }.rich-editor:empty:before { content:attr(data-placeholder); color:#a0a8b7; pointer-events:none; }.editor-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:9px; }.editor-footer>span { color:#a0a8b7; font-size:9px; }.history-list { display:flex; flex-direction:column; gap:8px; padding-bottom:10px; }.history-row { background:#f8f9fb; border:1px solid #f0f2f5; border-radius:7px; padding:10px 12px; }.history-row>div:first-child { display:flex; justify-content:space-between; gap:12px; }.history-row strong { font-size:10px; }.history-row span { color:#98a2b3; font-size:9px; }.rich-text { color:#667085; font-size:10px; line-height:1.7; margin:8px 0 0; overflow-wrap:anywhere; }.rich-text p { margin:0 0 5px; }.rich-text p:last-child { margin-bottom:0; }.rich-text img,.rich-editor img { display:block; max-width:100%; height:auto; border-radius:6px; margin:8px 0; }
.property-panel { position:sticky; top:0; padding:19px 20px; }.property-panel>.card-header { margin-bottom:14px; }.property-form :deep(.el-form-item) { margin-bottom:13px; }.property-form :deep(.el-form-item__label) { font-size:10px; color:#667085; padding-bottom:5px; line-height:1.4; }.property-form :deep(.el-select) { width:100%; }.property-grid { display:grid; grid-template-columns:1fr 1fr; gap:0 12px; }.form-section-title { display:flex; align-items:center; justify-content:space-between; gap:8px; color:#344054; font-size:10px; font-weight:600; border-top:1px solid #edf0f4; padding-top:14px; margin:4px 0 13px; }.form-section-title>small { color:#98a2b3; font-size:7px; font-weight:400; }.form-section-title:first-child { border-top:0; padding-top:0; margin-top:0; }
.owner-fixed { display:flex; align-items:center; min-height:32px; gap:7px; border:1px solid #e4e7ec; border-radius:6px; background:#f7f8fa; padding:5px 8px; }.owner-fixed>span { display:grid; place-items:center; width:21px; height:21px; border-radius:50%; background:#e7ebf3; color:#667085; font-size:9px; }.owner-fixed>strong { color:#475467; font-size:10px; font-weight:500; }.owner-fixed>small { display:flex; align-items:center; gap:2px; margin-left:auto; color:#98a2b3; font-size:7px; white-space:nowrap; }
.current-handler-fixed { display:flex; align-items:center; min-height:38px; gap:8px; border:1px solid #dbe4f7; border-radius:7px; background:#f5f7ff; padding:6px 9px; }.current-handler-fixed>span { display:grid; place-items:center; width:24px; height:24px; border-radius:50%; background:#e3eaff; color:#315efb; }.current-handler-fixed>strong { color:#344054; font-size:10px; font-weight:600; }.current-handler-fixed>small { display:flex; align-items:center; gap:3px; margin-left:auto; color:#8a98b5; font-size:7px; }.current-handler-fixed.empty { border-color:#e4e7ec; background:#f7f8fa; }.current-handler-fixed.empty>span { background:#e9edf2; color:#98a2b3; }.current-handler-fixed.empty>strong { color:#98a2b3; font-weight:400; }
.review-assignment-bar { display:flex; align-items:center; gap:11px; padding:16px 18px; border-color:#dbe4f7; background:linear-gradient(135deg,#fff 0%,#f6f8ff 100%); }.review-assignment-icon { width:34px; height:34px; display:grid; place-items:center; flex-shrink:0; border-radius:9px; background:#e8eeff; color:#315efb; font-size:17px; }.review-assignment-bar>div:nth-child(2) { flex:1; min-width:0; }.review-assignment-bar strong { color:#344054; font-size:11px; }.review-assignment-bar p { margin:4px 0 0; color:#8a94a6; font-size:9px; }.review-assignment-bar>.el-button { flex-shrink:0; }
.review-dialog-intro { display:flex; align-items:flex-start; gap:10px; padding:12px; margin-bottom:17px; border-radius:8px; background:#f5f7ff; color:#315efb; }.review-dialog-intro .el-icon { margin-top:2px; flex-shrink:0; }.review-dialog-intro p { margin:0; color:#667085; font-size:12px; line-height:1.7; }.reviewer-option { display:flex; align-items:center; justify-content:space-between; gap:20px; }.reviewer-option span { color:#98a2b3; font-size:11px; }
.attachment-section { min-height:150px; }.attachment-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }.attachment-empty { min-height:120px; border:1px dashed #e1e6ee; border-radius:8px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:#a0a8b7; font-size:10px; }.attachment-empty .el-icon { font-size:22px; }.attachment-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }.attachment-list>div { display:flex; align-items:center; gap:9px; background:#f8f9fb; border:1px solid #edf0f4; border-radius:8px; padding:11px; }.attachment-list>div>span { width:30px; height:30px; display:grid; place-items:center; border-radius:7px; background:#edf0ff; color:#315efb; flex-shrink:0; }.attachment-list>div>div { flex:1; min-width:0; display:flex; flex-direction:column; gap:4px; }.attachment-list strong { font-size:10px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.attachment-list small { color:#98a2b3; font-size:8px; }
.full-history { padding:2px 0 0 3px; }.full-history :deep(.el-timeline-item__timestamp) { color:#98a2b3; font-size:9px; }.full-history :deep(.el-timeline-item__node) { background:#a9b8d4; }.full-history :deep(.el-timeline-item__tail) { border-color:#e3e8f0; }.history-record-card { background:#f8f9fb; border:1px solid #edf0f4; border-radius:8px; padding:12px 14px; }.history-record-title { display:flex; align-items:center; justify-content:space-between; gap:12px; }.history-record-title strong { color:#344054; font-size:11px; }.history-record-title span { color:#8a94a6; font-size:9px; }.history-changes { margin-top:11px; border:1px solid #e4e9f0; border-radius:7px; overflow:hidden; background:#fff; }.change-header,.change-row { display:grid; grid-template-columns:minmax(90px,.65fr) minmax(0,1fr) minmax(0,1fr); gap:0; }.change-header { background:#f0f3f7; color:#7a8494; font-size:8px; font-weight:600; }.change-header span,.change-row>span,.change-row>strong { min-width:0; padding:8px 10px; border-right:1px solid #edf0f4; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.change-header span:last-child,.change-row>*:last-child { border-right:0; }.change-row { border-top:1px solid #edf0f4; color:#667085; font-size:9px; }.change-row>strong { color:#475467; font-weight:500; }.change-row>span:last-child { color:#315efb; background:#fafbff; }
@media (max-width:1200px) { .detail-workspace { grid-template-columns:1fr; }.property-panel { position:static; }.detail-topline { flex-wrap:wrap; }.detail-actions { width:100%; justify-content:flex-start; padding-left:47px; } }
@media (max-width:760px) { .operation-layout { grid-template-columns:1fr; }.operation-palette { border-left:0; border-top:1px solid #edf0f4; padding:15px 0 0; }.property-grid,.attachment-list { grid-template-columns:1fr; }.lifecycle-card { padding:15px 12px; }.lifecycle-title small { display:none; }.stage-select { align-items:flex-end; flex-direction:column; }.detail-actions { padding-left:0; }.detail-tab-bar { margin-left:-14px; margin-right:-14px; padding-left:7px; padding-right:7px; }.detail-tab-bar button { flex:1; padding:0 6px; font-size:10px; }.change-header,.change-row { grid-template-columns:minmax(72px,.7fr) minmax(0,1fr) minmax(0,1fr); }.change-header span,.change-row>span,.change-row>strong { padding:7px 6px; }.review-assignment-bar { flex-wrap:wrap; }.review-assignment-bar>.el-button { width:100%; margin-left:0; } }
</style>
