<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile, UploadUserFile } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { api, errorMessage, queryString, saveBlob } from '../../api'
import { can, ensureOptions, store } from '../../store'
import { isGlobalAdmin } from '../../permissions'
import type { OptionItem, UserOption } from '../../types'

interface Member { id: string; project_id: string; role_id: string; role: string; user: UserOption }
interface ImportRow {
  row_number: number
  employee_id: string
  username: string
  department?: string | null
  email?: string | null
  role_id?: string | null
  role_name?: string | null
  action: 'CREATE_USER_AND_MEMBER' | 'ADD_MEMBER' | 'EXISTING_MEMBER'
  status: 'READY' | 'ERROR'
  errors: string[]
}
interface ImportSummary { total: number; valid: number; errors: number; new_users: number; new_members: number; existing_members: number }

const ALL_PROJECTS = '__all_projects__'
const selectedProjectId = ref(store.projectId)
const projectSearch = ref('')
const search = ref('')
const loading = ref(false)
const saving = ref(false)
const dialogOpen = ref(false)
const editing = ref<Member | null>(null)
const members = ref<Member[]>([])
const users = ref<UserOption[]>([])
const form = reactive({ user_id: '', role_id: '' })
const allProjects = computed(() => selectedProjectId.value === ALL_PROJECTS)
const selectedProject = computed(() => store.options.projects.find(item => item.id === selectedProjectId.value))
const projects = computed(() => store.options.projects.filter(item => item.name.includes(projectSearch.value)))
const roles = computed(() => store.options.roles.filter(item => !['系统管理员', '初始化用户'].includes(item.name)))
const filtered = computed(() => members.value.filter(item => {
  const keyword = search.value.toLowerCase()
  return !keyword || [item.user.username, item.user.employee_id, item.user.department || ''].some(value => value.toLowerCase().includes(keyword))
}))
const availableUsers = computed(() => users.value.filter(user => !members.value.some(member => member.user.id === user.id)))
const canManage = computed(() => allProjects.value ? isGlobalAdmin() : can('project.member.manage'))
const canManageMember = (member: Member) => canManage.value && (isGlobalAdmin() || member.role !== '系统管理员')

const importDialogOpen = ref(false)
const importFileList = ref<UploadUserFile[]>([])
const importFile = ref<File | null>(null)
const importRoleId = ref('')
const importLoading = ref(false)
const importSaving = ref(false)
const importSummary = ref<ImportSummary | null>(null)
const importRows = ref<ImportRow[]>([])
const importReady = computed(() => !!importSummary.value && importSummary.value.total > 0 && importSummary.value.errors === 0)

function globalMember(item: UserOption): Member {
  return { id: `global-${item.id}`, project_id: ALL_PROJECTS, role_id: String(item.global_role_id || ''), role: String(item.global_role || ''), user: item }
}

async function loadMembers() {
  if (!selectedProjectId.value) { members.value = []; return }
  loading.value = true
  try {
    if (allProjects.value) {
      if (!isGlobalAdmin()) { members.value = []; return }
      if (store.demoMode) {
        users.value = store.options.users.filter(item => item.id !== 'demo-admin')
        members.value = users.value.filter(item => item.global_role_id).map(globalMember)
      } else {
        const rows = await api.get<UserOption[]>('/global-access/users')
        users.value = rows
        members.value = rows.filter(item => item.global_role_id).map(globalMember)
      }
    } else if (store.demoMode) {
      const admin: Member = { id: 'demo-member-admin', project_id: selectedProjectId.value, role_id: 'demo-role-system-admin', role: '系统管理员', user: { id: 'demo-admin', username: 'admin', employee_id: 'E1024', department: '系统管理', email: 'zhangming@wmp.local' } }
      const owner = store.options.users.find(item => item.id === 'demo-owner')
      members.value = [admin, ...(owner ? [{ id: 'demo-member-owner', project_id: selectedProjectId.value, role_id: 'demo-role-developer', role: '开发人员', user: owner }] : [])]
    } else members.value = await api.get<Member[]>(`/projects/${selectedProjectId.value}/members`)
  } catch (error) { ElMessage.error(errorMessage(error, '成员数据加载失败')) }
  finally { loading.value = false }
}

function open(row?: Member) {
  editing.value = row || null
  Object.assign(form, row ? { user_id: row.user.id, role_id: row.role_id } : { user_id: '', role_id: roles.value.find(item => !item.built_in)?.id || roles.value.find(item => item.name === '开发人员')?.id || roles.value[0]?.id || '' })
  dialogOpen.value = true
}

async function save() {
  if (!form.user_id || !form.role_id) return ElMessage.warning(`请选择平台用户和${allProjects.value ? '全局' : '项目'}角色`)
  saving.value = true
  try {
    if (allProjects.value) {
      if (store.demoMode) {
        const user = users.value.find(item => item.id === form.user_id)
        const role = roles.value.find(item => item.id === form.role_id)
        if (user) Object.assign(user, { global_role_id: form.role_id, global_role: role?.name })
      } else await api.put(`/users/${form.user_id}/global-role`, { role_id: form.role_id })
    } else if (store.demoMode) {
      const user = users.value.find(item => item.id === form.user_id)!
      const role = store.options.roles.find(item => item.id === form.role_id)!
      if (editing.value) Object.assign(editing.value, { role_id: role.id, role: role.name })
      else members.value.push({ id: crypto.randomUUID(), project_id: selectedProjectId.value, role_id: role.id, role: role.name, user })
    } else {
      if (editing.value) await api.put(`/projects/${selectedProjectId.value}/members/${editing.value.id}`, form)
      else await api.post(`/projects/${selectedProjectId.value}/members`, form)
    }
    dialogOpen.value = false
    ElMessage.success(allProjects.value ? '所有项目授权已保存' : editing.value ? '成员角色已更新' : '成员已添加到项目')
    await loadMembers()
  } catch (error) { ElMessage.error(errorMessage(error, '成员保存失败')) }
  finally { saving.value = false }
}

async function remove(row: Member) {
  const message = allProjects.value ? `确定撤销 ${row.user.username} 的“所有项目”授权吗？` : `确定将 ${row.user.username} 从「${selectedProject.value?.name}」移除吗？`
  try { await ElMessageBox.confirm(message, allProjects.value ? '撤销全局授权' : '移除成员', { type: 'warning', confirmButtonText: allProjects.value ? '撤销' : '移除', cancelButtonText: '取消' }) } catch { return }
  try {
    if (allProjects.value) {
      if (store.demoMode) {
        const user = users.value.find(item => item.id === row.user.id)
        if (user) Object.assign(user, { global_role_id: null, global_role: null })
      } else await api.put(`/users/${row.user.id}/global-role`, { role_id: null })
    } else if (store.demoMode) members.value = members.value.filter(item => item.id !== row.id)
    else await api.delete(`/projects/${selectedProjectId.value}/members/${row.id}`)
    ElMessage.success(allProjects.value ? '所有项目授权已撤销' : '成员已移除')
    await loadMembers()
  } catch (error) { ElMessage.error(errorMessage(error, '操作失败')) }
}

async function loadUsers() {
  if (allProjects.value) return
  users.value = store.demoMode ? store.options.users : await api.get<UserOption[]>(`/users${queryString({ project_id: selectedProjectId.value })}`)
}
async function reload() { await Promise.all([loadUsers(), loadMembers()]) }

function openImport() {
  if (store.demoMode) return ElMessage.info('批量初始化需要连接真实后端服务')
  importFileList.value = []
  importFile.value = null
  importSummary.value = null
  importRows.value = []
  importRoleId.value = roles.value.find(item => item.name === '开发人员')?.id || roles.value[0]?.id || ''
  importDialogOpen.value = true
}

function importFileChanged(file: UploadFile) {
  importFile.value = file.raw || null
  importSummary.value = null
  importRows.value = []
}

async function downloadTemplate() {
  try {
    const blob = await api.download(`/projects/${selectedProjectId.value}/members/import-template`)
    saveBlob('WMP用户批量初始化模板.xlsx', blob)
  } catch (error) { ElMessage.error(errorMessage(error, '模板下载失败')) }
}

async function previewImport() {
  if (!importRoleId.value) return ElMessage.warning('请选择默认项目角色')
  if (!importFile.value) return ElMessage.warning('请选择 Excel 或 CSV 文件')
  importLoading.value = true
  try {
    const body = new FormData()
    body.append('default_role_id', importRoleId.value)
    body.append('file', importFile.value)
    const result = await api.upload<{ summary: ImportSummary; rows: ImportRow[] }>(`/projects/${selectedProjectId.value}/members/bulk-preview`, body)
    importSummary.value = result.summary
    importRows.value = result.rows
    if (result.summary.errors) ElMessage.warning(`发现 ${result.summary.errors} 行错误，请修正后重新上传`)
  } catch (error) { ElMessage.error(errorMessage(error, '文件校验失败')) }
  finally { importLoading.value = false }
}

async function confirmImport() {
  if (!importReady.value) return
  importSaving.value = true
  try {
    const rows = importRows.value.map(row => ({ row_number: row.row_number, employee_id: row.employee_id, username: row.username, department: row.department, email: row.email, role_name: row.role_name }))
    const result = await api.post<{ message: string; summary: ImportSummary }>(`/projects/${selectedProjectId.value}/members/bulk-import`, { default_role_id: importRoleId.value, rows })
    importDialogOpen.value = false
    ElMessage.success(`初始化完成：新建用户 ${result.summary.new_users} 人，新增成员 ${result.summary.new_members} 人，已有成员 ${result.summary.existing_members} 人`)
    await reload()
  } catch (error) { ElMessage.error(errorMessage(error, '批量初始化失败')) }
  finally { importSaving.value = false }
}

function importAction(row: ImportRow) {
  if (row.status === 'ERROR') return '校验失败'
  return row.action === 'CREATE_USER_AND_MEMBER' ? '新建用户并加入' : row.action === 'ADD_MEMBER' ? '加入项目' : '已有成员，保留原角色'
}

function importRowClass({ row }: { row: ImportRow }) {
  return row.status === 'ERROR' ? 'import-error-row' : ''
}

onMounted(async () => {
  try {
    await ensureOptions()
    await reload()
  } catch (error) { ElMessage.error(errorMessage(error, '成员选项加载失败')) }
})
watch(selectedProjectId, () => { void reload().catch(error => ElMessage.error(errorMessage(error, '成员数据加载失败'))) })
watch(() => store.projectId, value => { if (!allProjects.value) selectedProjectId.value = value })
</script>

<template>
  <section class="surface-card member-card">
    <aside class="project-panel">
      <div class="project-panel-title"><span>授权范围</span><el-icon><MoreFilled /></el-icon></div>
      <el-input v-model="projectSearch" placeholder="搜索项目" :prefix-icon="Search" class="project-search" />
      <button v-if="isGlobalAdmin()" :class="{ active: allProjects }" class="all-projects-button" @click="selectedProjectId = ALL_PROJECTS"><span class="project-avatar"><el-icon><OfficeBuilding /></el-icon></span><span><strong>所有项目</strong><small>全局角色授权</small></span><el-icon><ArrowRight /></el-icon></button>
      <div class="project-divider">项目列表</div>
      <button v-for="project in projects" :key="project.id" :class="{ active: selectedProjectId === project.id }" @click="selectedProjectId = project.id"><span class="project-avatar">{{ project.name.slice(0, 1) }}</span><span><strong>{{ project.name }}</strong><small>{{ selectedProjectId === project.id ? `${members.length} 名成员` : project.code }}</small></span><el-icon><ArrowRight /></el-icon></button>
    </aside>
    <div class="member-content">
      <div class="member-toolbar">
        <div><h2>{{ allProjects ? '所有项目' : selectedProject?.name }}</h2><p>{{ allProjects ? '为平台用户分配全局角色，不创建具体项目成员关系' : '管理项目成员及其在当前项目中的角色' }}</p></div>
        <div v-if="canManage" class="member-actions"><el-button v-if="!allProjects" @click="openImport"><el-icon><Upload /></el-icon>批量初始化</el-button><el-button type="primary" @click="open()"><el-icon><Plus /></el-icon>{{ allProjects ? '添加全局授权' : '添加成员' }}</el-button></div>
      </div>
      <div v-if="allProjects" class="global-scope-note"><el-icon><InfoFilled /></el-icon>全局授权由系统管理员维护，独立于各项目成员角色；撤销授权不会影响已加入的项目。</div>
      <div class="member-filter"><el-input v-model="search" placeholder="通过用户名、工号或部门查询" :prefix-icon="Search" clearable style="width:300px" /><span>{{ filtered.length }} 名成员</span></div>
      <el-table v-loading="loading" :data="filtered" class="data-table" :empty-text="allProjects ? '暂无全局授权成员' : '暂无项目成员'">
        <el-table-column label="成员" min-width="160"><template #default="{ row }"><div class="member-name"><el-avatar :size="30">{{ row.user.username.slice(0, 1) }}</el-avatar><div><strong>{{ row.user.username }}</strong><small>{{ row.user.department || '未填写部门' }}</small></div></div></template></el-table-column>
        <el-table-column prop="user.employee_id" label="工号" width="105"><template #default="{ row }"><span class="mono muted">{{ row.user.employee_id }}</span></template></el-table-column>
        <el-table-column prop="role" :label="allProjects ? '全局角色' : '项目角色'" width="140"><template #default="{ row }"><span class="role-chip" :class="{ global: allProjects }">{{ row.role }}</span></template></el-table-column>
        <el-table-column prop="user.email" label="邮箱" min-width="190"><template #default="{ row }"><span class="muted">{{ row.user.email || '—' }}</span></template></el-table-column>
        <el-table-column v-if="canManage" label="操作" width="130" align="right"><template #default="{ row }"><el-button v-if="canManageMember(row)" text type="primary" @click="open(row)">编辑</el-button><el-button v-if="canManageMember(row)" text class="remove-button" @click="remove(row)">{{ allProjects ? '撤销' : '移除' }}</el-button></template></el-table-column>
      </el-table>
    </div>
  </section>

  <el-dialog v-model="dialogOpen" :title="allProjects ? (editing ? '编辑全局授权' : '添加全局授权') : (editing ? '编辑项目成员' : '添加项目成员')" width="480px">
    <div class="member-dialog-project">授权范围：<strong>{{ allProjects ? '所有项目' : selectedProject?.name }}</strong></div>
    <el-form label-position="top" class="dialog-form"><el-form-item label="平台用户" required><el-select v-model="form.user_id" :disabled="!!editing" filterable style="width:100%" placeholder="搜索用户名、工号或部门"><el-option v-for="item in editing ? users.filter(x => x.id === editing?.user.id) : availableUsers" :key="item.id" :label="`${item.username} · ${item.employee_id} · ${item.department || '未填写部门'}`" :value="item.id" /></el-select></el-form-item><el-form-item :label="allProjects ? '全局角色' : '项目角色'" required><el-select v-model="form.role_id" style="width:100%"><el-option v-for="role in roles" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item><p class="member-help">{{ allProjects ? '该角色作为用户的全局授权保存，不会自动加入任何具体项目。' : '企业用户首次 OAuth 登录后自动注册，也可通过批量初始化预先建档；业务权限以此处的项目角色为准。' }}</p></el-form>
    <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">{{ editing ? '保存修改' : allProjects ? '添加授权' : '添加成员' }}</el-button></template>
  </el-dialog>

  <el-dialog v-model="importDialogOpen" title="批量初始化项目用户" width="1080px" :close-on-click-modal="false" class="import-dialog">
    <div class="import-project">目标项目：<strong>{{ selectedProject?.name }}</strong><span>工号是唯一匹配标识，已有成员保留原角色</span></div>
    <el-steps :active="importSummary ? 1 : 0" align-center finish-status="success" simple><el-step title="上传并校验" /><el-step title="预览并确认" /></el-steps>
    <div v-if="!importSummary" v-loading="importLoading" class="import-upload-step">
      <div class="import-options"><el-form label-position="top"><el-form-item label="默认项目角色" required><el-select v-model="importRoleId" style="width:280px"><el-option v-for="role in roles" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item></el-form><el-button text type="primary" @click="downloadTemplate"><el-icon><Download /></el-icon>下载 Excel 模板</el-button></div>
      <el-upload v-model:file-list="importFileList" drag :auto-upload="false" :limit="1" accept=".xlsx,.csv" :on-change="importFileChanged" :on-remove="() => { importFile = null }" class="import-uploader"><el-icon class="el-icon--upload"><UploadFilled /></el-icon><div class="el-upload__text">将 Excel／CSV 文件拖到此处，或 <em>点击选择</em></div><template #tip><div class="el-upload__tip">模板列：工号、用户名、所属部门、项目角色、邮箱；单次最多 5000 行，文件不超过 10 MB。</div></template></el-upload>
    </div>
    <div v-else class="import-preview-step">
      <div class="import-summary"><div><span>总行数</span><strong>{{ importSummary.total }}</strong></div><div><span>新建用户</span><strong>{{ importSummary.new_users }}</strong></div><div><span>新增成员</span><strong>{{ importSummary.new_members }}</strong></div><div><span>已有成员</span><strong>{{ importSummary.existing_members }}</strong></div><div :class="{ error: importSummary.errors }"><span>错误行</span><strong>{{ importSummary.errors }}</strong></div></div>
      <el-alert v-if="importSummary.errors" type="error" :closable="false" show-icon title="存在错误时不能确认导入，请根据逐行原因修改文件并重新上传。" />
      <el-alert v-else type="success" :closable="false" show-icon title="全部行校验通过。确认后将一次性写入，重复执行不会生成重复用户或成员。" />
      <el-table :data="importRows" max-height="430" class="data-table import-table" :row-class-name="importRowClass">
        <el-table-column prop="row_number" label="行号" width="65" /><el-table-column prop="employee_id" label="工号" width="100" /><el-table-column prop="username" label="用户名" min-width="130" /><el-table-column prop="department" label="所属部门" min-width="130"><template #default="{ row }">{{ row.department || '—' }}</template></el-table-column><el-table-column prop="role_name" label="项目角色" width="110" /><el-table-column label="处理结果" min-width="180"><template #default="{ row }"><span :class="row.status === 'ERROR' ? 'import-result-error' : 'import-result-ready'">{{ importAction(row) }}</span><div v-if="row.errors.length" class="import-errors">{{ row.errors.join('；') }}</div></template></el-table-column>
      </el-table>
    </div>
    <template #footer><el-button @click="importDialogOpen = false">取消</el-button><el-button v-if="importSummary" @click="importSummary = null; importRows = []">重新选择文件</el-button><el-button v-if="!importSummary" type="primary" :loading="importLoading" @click="previewImport">校验并预览</el-button><el-button v-else type="primary" :disabled="!importReady" :loading="importSaving" @click="confirmImport">确认初始化 {{ importSummary.valid }} 行</el-button></template>
  </el-dialog>
</template>

<style scoped>
.member-card { display:grid; grid-template-columns:235px minmax(0,1fr); min-height:490px; }
.project-panel { border-right:1px solid var(--line); padding:17px 12px; }
.project-panel-title { display:flex; justify-content:space-between; color:#7a8494; font-size:11px; padding:0 8px 13px; }
.project-search { margin-bottom:13px; }
.project-panel>button { width:100%; display:flex; align-items:center; gap:10px; border:0; background:transparent; border-radius:8px; padding:11px 9px; text-align:left; margin:4px 0; cursor:pointer; }
.project-panel>button.active { background:#edf0ff; }
.project-panel>button.all-projects-button { border:1px solid #e1e7f5; background:#f8faff; margin-bottom:12px; }
.project-panel>button.all-projects-button.active { border-color:#cbd7ff; background:#edf0ff; }
.project-avatar { width:30px; height:30px; display:grid; place-items:center; flex-shrink:0; border-radius:7px; background:#f0f2f5; color:#7a8494; font-size:11px; }
.active .project-avatar { background:#dbe3ff; color:#315efb; }
.project-panel button>span:nth-child(2) { flex:1; display:flex; flex-direction:column; gap:4px; }
.project-panel button strong { font-size:11px; font-weight:500; }
.project-panel button small { font-size:9px; color:#98a2b3; }
.project-panel button>.el-icon { color:#b5bdc9; font-size:10px; }
.project-divider { padding:4px 9px 7px; color:#a0a8b7; font-size:9px; }
.member-content { min-width:0; }
.member-toolbar { padding:20px; display:flex; justify-content:space-between; align-items:center; gap:20px; }
.member-toolbar h2 { font-size:15px; margin:0; }
.member-toolbar p { color:#98a2b3; font-size:10px; margin:5px 0 0; }
.member-actions { display:flex; gap:8px; flex-shrink:0; }
.global-scope-note { display:flex; align-items:center; gap:7px; margin:0 20px 15px; padding:10px 12px; border-radius:7px; background:#f5f7ff; color:#667085; font-size:10px; }
.global-scope-note .el-icon { color:#315efb; }
.member-filter { display:flex; align-items:center; justify-content:space-between; padding:0 20px 17px; }
.member-filter>span { color:#98a2b3; font-size:10px; }
.member-name { display:flex; align-items:center; gap:10px; }
.member-name>div { display:flex; flex-direction:column; gap:3px; }
.member-name strong { font-size:12px; }
.member-name small { color:#98a2b3; font-size:10px; }
.role-chip { display:inline-flex; padding:4px 9px; border-radius:6px; background:#edf0ff; color:#315efb; font-size:10px; }
.role-chip.global { background:#f3efff; color:#7957d5; }
.remove-button { color:#d54848; }
.member-dialog-project { margin-bottom:18px; padding:11px 13px; border-radius:7px; background:#f6f8fb; color:#667085; font-size:12px; }
.member-help { color:#98a2b3; font-size:11px; line-height:1.7; margin:0; }
.import-project { display:flex; align-items:center; gap:8px; margin-bottom:18px; color:#667085; font-size:12px; }
.import-project span { margin-left:auto; color:#98a2b3; font-size:11px; }
.import-upload-step { padding:26px 10px 8px; }
.import-options { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:12px; }
.import-uploader { width:100%; }
.import-uploader :deep(.el-upload), .import-uploader :deep(.el-upload-dragger) { width:100%; }
.import-uploader :deep(.el-upload-dragger) { padding:45px 20px; }
.import-preview-step { margin-top:20px; }
.import-summary { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:15px; }
.import-summary>div { padding:13px 15px; border:1px solid #e6eaf0; border-radius:8px; background:#f8fafc; display:flex; flex-direction:column; gap:5px; }
.import-summary span { color:#7a8494; font-size:11px; }
.import-summary strong { font-size:22px; color:#27364b; }
.import-summary .error strong { color:#d54848; }
.import-table { margin-top:15px; }
.import-result-ready { color:#168a63; }
.import-result-error { color:#d54848; }
.import-errors { color:#d54848; font-size:10px; line-height:1.5; margin-top:4px; }
:deep(.import-error-row) { background:#fff8f7; }
@media(max-width:1000px){.member-card{grid-template-columns:200px minmax(0,1fr)}.import-summary{grid-template-columns:repeat(3,1fr)}}
</style>
