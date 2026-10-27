<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { api, errorMessage, queryString } from '../../api'
import { can, ensureOptions, store } from '../../store'
import { isGlobalAdmin } from '../../permissions'
import type { OptionItem } from '../../types'

interface Member { id: string; project_id: string; role_id: string; role: string; user: { id: string; name: string; username: string; employee_id: string; email?: string } }
interface GlobalUser extends OptionItem { global_role_id?: string | null; global_role?: string | null }
const ALL_PROJECTS = '__all_projects__'
const selectedProjectId = ref(store.projectId)
const projectSearch = ref('')
const search = ref('')
const loading = ref(false)
const saving = ref(false)
const dialogOpen = ref(false)
const editing = ref<Member | null>(null)
const members = ref<Member[]>([])
const users = ref<GlobalUser[]>([])
const form = reactive({ user_id: '', role_id: '' })
const allProjects = computed(() => selectedProjectId.value === ALL_PROJECTS)
const selectedProject = computed(() => store.options.projects.find(item => item.id === selectedProjectId.value))
const projects = computed(() => store.options.projects.filter(item => item.name.includes(projectSearch.value)))
const roles = computed(() => store.options.roles.filter(item => item.name !== '系统管理员'))
const filtered = computed(() => members.value.filter(item => !search.value || item.user.name.includes(search.value) || item.user.employee_id.toLowerCase().includes(search.value.toLowerCase()) || item.user.username.includes(search.value)))
const availableUsers = computed(() => users.value.filter(user => !members.value.some(member => member.user.id === user.id)))
const canManage = computed(() => allProjects.value ? isGlobalAdmin() : can('project.member.manage'))
const canManageMember = (member: Member) => canManage.value && (isGlobalAdmin() || member.role !== '系统管理员')

function globalMember(item: GlobalUser): Member {
  return { id: `global-${item.id}`, project_id: ALL_PROJECTS, role_id: String(item.global_role_id || ''), role: String(item.global_role || ''), user: { id: item.id, name: item.name, username: String(item.username), employee_id: String(item.employee_id), email: String(item.email || '') } }
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
        const rows = await api.get<GlobalUser[]>('/global-access/users')
        users.value = rows
        members.value = rows.filter(item => item.global_role_id).map(globalMember)
      }
    } else if (store.demoMode) {
      const admin: Member = { id: 'demo-member-admin', project_id: selectedProjectId.value, role_id: 'demo-role-system-admin', role: '系统管理员', user: { id: 'demo-admin', name: '张明', username: 'admin', employee_id: 'E1024', email: 'zhangming@wmp.local' } }
      const owner = store.options.users.find(item => item.id === 'demo-owner')
      members.value = [admin, ...(owner ? [{ id: 'demo-member-owner', project_id: selectedProjectId.value, role_id: 'demo-role-developer', role: '开发人员', user: { id: owner.id, name: owner.name, username: String(owner.username), employee_id: String(owner.employee_id), email: String(owner.email || '') } }] : [])]
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
      else members.value.push({ id: crypto.randomUUID(), project_id: selectedProjectId.value, role_id: role.id, role: role.name, user: { id: user.id, name: user.name, username: String(user.username), employee_id: String(user.employee_id), email: String(user.email || '') } })
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
  const message = allProjects.value ? `确定撤销 ${row.user.name} 的“所有项目”授权吗？` : `确定将 ${row.user.name} 从「${selectedProject.value?.name}」移除吗？`
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
  users.value = store.demoMode ? store.options.users : await api.get<GlobalUser[]>(`/users${queryString({ project_id: selectedProjectId.value })}`)
}
async function reload() { await Promise.all([loadUsers(), loadMembers()]) }
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
      <div class="member-toolbar"><div><h2>{{ allProjects ? '所有项目' : selectedProject?.name }}</h2><p>{{ allProjects ? '为平台用户分配全局角色，不创建具体项目成员关系' : '管理项目成员及其在当前项目中的角色' }}</p></div><el-button v-if="canManage" type="primary" @click="open()"><el-icon><Plus /></el-icon>{{ allProjects ? '添加全局授权' : '添加成员' }}</el-button></div>
      <div v-if="allProjects" class="global-scope-note"><el-icon><InfoFilled /></el-icon>全局授权由系统管理员维护，独立于各项目成员角色；撤销授权不会影响已加入的项目。</div>
      <div class="member-filter"><el-input v-model="search" placeholder="通过姓名、用户名或工号查询" :prefix-icon="Search" clearable style="width:300px" /><span>{{ filtered.length }} 名成员</span></div>
      <el-table v-loading="loading" :data="filtered" class="data-table" :empty-text="allProjects ? '暂无全局授权成员' : '暂无项目成员'">
        <el-table-column label="成员" min-width="170"><template #default="{ row }"><div class="member-name"><el-avatar :size="30">{{ row.user.name.slice(0, 1) }}</el-avatar><div><strong>{{ row.user.name }}</strong><small>@{{ row.user.username }}</small></div></div></template></el-table-column>
        <el-table-column prop="user.employee_id" label="工号" width="100"><template #default="{ row }"><span class="mono muted">{{ row.user.employee_id }}</span></template></el-table-column>
        <el-table-column prop="role" :label="allProjects ? '全局角色' : '项目角色'" width="140"><template #default="{ row }"><span class="role-chip" :class="{ global: allProjects }">{{ row.role }}</span></template></el-table-column>
        <el-table-column prop="user.email" label="邮箱" min-width="190"><template #default="{ row }"><span class="muted">{{ row.user.email || '—' }}</span></template></el-table-column>
        <el-table-column v-if="canManage" label="操作" width="130" align="right"><template #default="{ row }"><el-button v-if="canManageMember(row)" text type="primary" @click="open(row)">编辑</el-button><el-button v-if="canManageMember(row)" text class="remove-button" @click="remove(row)">{{ allProjects ? '撤销' : '移除' }}</el-button></template></el-table-column>
      </el-table>
    </div>
  </section>
  <el-dialog v-model="dialogOpen" :title="allProjects ? (editing ? '编辑全局授权' : '添加全局授权') : (editing ? '编辑项目成员' : '添加项目成员')" width="480px">
    <div class="member-dialog-project">授权范围：<strong>{{ allProjects ? '所有项目' : selectedProject?.name }}</strong></div>
    <el-form label-position="top" class="dialog-form"><el-form-item label="平台用户" required><el-select v-model="form.user_id" :disabled="!!editing" filterable style="width:100%" placeholder="搜索姓名、工号或用户名"><el-option v-for="item in editing ? users.filter(x => x.id === editing?.user.id) : availableUsers" :key="item.id" :label="`${item.name} · ${item.employee_id} · ${item.username}`" :value="item.id" /></el-select></el-form-item><el-form-item :label="allProjects ? '全局角色' : '项目角色'" required><el-select v-model="form.role_id" style="width:100%"><el-option v-for="role in roles" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item><p class="member-help">{{ allProjects ? '该角色作为用户的全局授权保存，不会自动加入任何具体项目。' : 'OAuth 仅负责身份认证，业务权限以此处的项目角色为准。' }}</p></el-form>
    <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">{{ editing ? '保存修改' : allProjects ? '添加授权' : '添加成员' }}</el-button></template>
  </el-dialog>
</template>

<style scoped>
.member-card { display:grid; grid-template-columns:235px minmax(0,1fr); min-height:490px; }.project-panel { border-right:1px solid var(--line); padding:17px 12px; }.project-panel-title { display:flex; justify-content:space-between; color:#7a8494; font-size:11px; padding:0 8px 13px; }.project-search { margin-bottom:13px; }.project-panel>button { width:100%; display:flex; align-items:center; gap:10px; border:0; background:transparent; border-radius:8px; padding:11px 9px; text-align:left; margin:4px 0; cursor:pointer; }.project-panel>button.active { background:#edf0ff; }.project-panel>button.all-projects-button { border:1px solid #e1e7f5; background:#f8faff; margin-bottom:12px; }.project-panel>button.all-projects-button.active { border-color:#cbd7ff; background:#edf0ff; }.project-avatar { width:30px; height:30px; display:grid; place-items:center; flex-shrink:0; border-radius:7px; background:#f0f2f5; color:#7a8494; font-size:11px; }.active .project-avatar { background:#dbe3ff; color:#315efb; }.project-panel button>span:nth-child(2) { flex:1; display:flex; flex-direction:column; gap:4px; }.project-panel button strong { font-size:11px; font-weight:500; }.project-panel button small { font-size:9px; color:#98a2b3; }.project-panel button>.el-icon { color:#b5bdc9; font-size:10px; }.project-divider { padding:4px 9px 7px; color:#a0a8b7; font-size:9px; }.member-content { min-width:0; }.member-toolbar { padding:20px; display:flex; justify-content:space-between; align-items:center; }.member-toolbar h2 { font-size:15px; margin:0; }.member-toolbar p { color:#98a2b3; font-size:10px; margin:5px 0 0; }.global-scope-note { display:flex; align-items:center; gap:7px; margin:0 20px 15px; padding:10px 12px; border-radius:7px; background:#f5f7ff; color:#667085; font-size:10px; }.global-scope-note .el-icon { color:#315efb; }.member-filter { display:flex; align-items:center; justify-content:space-between; padding:0 20px 17px; }.member-filter>span { color:#98a2b3; font-size:10px; }.member-name { display:flex; align-items:center; gap:9px; }.member-name .el-avatar { background:#eef2ff; color:#315efb; font-size:10px; }.member-name>div { display:flex; flex-direction:column; gap:3px; }.member-name strong { font-size:11px; font-weight:500; }.member-name small { color:#98a2b3; font-size:9px; }.role-chip { background:#f3f4f6; border-radius:5px; padding:4px 7px; font-size:10px; color:#596579; }.role-chip.global { background:#f3efff; color:#6941c6; }.remove-button { color:#98a2b3; }.remove-button:hover { color:#d92d20; }.member-dialog-project { background:#f6f8fc; border-radius:7px; padding:11px 13px; margin-bottom:17px; color:#667085; font-size:11px; }.member-help { color:#98a2b3; font-size:10px; line-height:1.6; }
</style>
