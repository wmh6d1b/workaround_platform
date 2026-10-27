<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TreeInstance } from 'element-plus'
import { api, errorMessage, queryString } from '../../api'
import { store } from '../../store'
import { isGlobalAdmin } from '../../permissions'

interface Role { id: string; name: string; description: string; built_in: boolean; permissions: string[] }
interface Permission { code: string; module: string; description: string }
const roles = ref<Role[]>([])
const permissions = ref<Permission[]>([])
const selectedId = ref('')
const treeRef = ref<TreeInstance>()
const dialogOpen = ref(false)
const loading = ref(false)
const saving = ref(false)
const newRole = reactive({ name:'', description:'' })
const selectedRole = computed(() => roles.value.find(item => item.id === selectedId.value))
const canEdit = computed(isGlobalAdmin)
const moduleNames: Record<string,string> = { home:'首页', wkd:'WKD 全生命周期', build:'构建 / 发布', stats:'数据统计', business:'业务管理', project:'项目管理', files:'附件管理' }
const permissionTree = computed(() => {
  const groups = new Map<string, { id: string; label: string; children: { id: string; label: string }[] }>()
  permissions.value.forEach(item => {
    if (!groups.has(item.module)) groups.set(item.module, { id:`module:${item.module}`, label:moduleNames[item.module] || item.module, children:[] })
    groups.get(item.module)!.children.push({ id:item.code, label:item.description })
  })
  return [...groups.values()]
})
const fallbackPermissions: Permission[] = [
  ['home.view','home','查看首页'],['wkd.view','wkd','查看 WKD'],['wkd.create','wkd','新建 WKD'],['wkd.edit','wkd','编辑 WKD'],['wkd.submit','wkd','提交自验证或审核'],['wkd.review','wkd','软件经理审核'],['wkd.disable','wkd','禁用 WKD'],['wkd.note','wkd','填写状态说明'],['build.debug.view','build','查看调试构建'],['build.debug.build','build','执行调试构建'],['build.release.view','build','查看正式构建和制品'],['build.release.build','build','执行正式构建'],['build.release.download','build','下载构建制品'],['business.version.view','business','查看版本管理'],['business.version.edit','business','维护版本数据'],['business.machine.view','business','查看机台管理'],['business.machine.edit','business','维护机台数据'],['business.subsystem.view','business','查看子系统管理'],['business.subsystem.edit','business','维护子系统数据'],['project.member.view','project','查看项目成员'],['project.member.manage','project','管理项目成员及角色分配'],['project.role.view','project','查看项目角色权限'],['files.upload','files','上传附件'],['files.download','files','下载附件'],
].map(([code,module,description]) => ({code,module,description}))
const developerPermissions = ['home.view','wkd.view','wkd.create','wkd.edit','wkd.submit','wkd.disable','wkd.note','build.debug.view','build.debug.build','build.release.view','build.release.download','files.upload','files.download']
const managerPermissions = ['home.view','wkd.view','wkd.edit','wkd.review','wkd.disable','wkd.note','build.debug.view','build.debug.build','build.release.view','build.release.download','files.upload','files.download']

async function load() {
  loading.value = true
  try {
    if (store.demoMode) {
      permissions.value = fallbackPermissions
      roles.value = store.options.roles.map(item => ({ id:item.id, name:item.name, description:String(item.description || ''), built_in:Boolean(item.built_in), permissions:item.name === '开发人员' ? developerPermissions : item.name === '软件经理' ? managerPermissions : fallbackPermissions.map(permission => permission.code) }))
    } else [roles.value, permissions.value] = await Promise.all([api.get<Role[]>(`/roles${queryString({ project_id:store.projectId })}`), api.get<Permission[]>(`/permissions${queryString({ project_id:store.projectId })}`)])
    if (!selectedId.value || !roles.value.some(item => item.id === selectedId.value)) selectedId.value = roles.value[0]?.id || ''
    await nextTick()
    syncChecks()
  } catch (error) { ElMessage.error(errorMessage(error, '角色权限加载失败')) }
  finally { loading.value = false }
}
function syncChecks() { treeRef.value?.setCheckedKeys(selectedRole.value?.permissions || []) }
function selectRole(id: string) { selectedId.value = id; nextTick(syncChecks) }
async function savePermissions() {
  const role = selectedRole.value
  if (!role) return
  const checked = (treeRef.value?.getCheckedKeys(true) || []).map(String)
  saving.value = true
  try {
    if (store.demoMode) role.permissions = checked
    else await api.put(`/roles/${role.id}`, { name:role.name, description:role.description, permissions:checked })
    ElMessage.success(`${role.name} 的权限配置已保存`)
  } catch (error) { ElMessage.error(errorMessage(error, '权限保存失败')) }
  finally { saving.value = false }
}
async function addRole() {
  if (!newRole.name.trim()) return ElMessage.warning('请输入角色名称')
  saving.value = true
  try {
    let id = ''
    if (store.demoMode) {
      id = crypto.randomUUID()
      store.options.roles.push({ id, name:newRole.name.trim(), description:newRole.description, built_in:false })
    } else {
      const result = await api.post<{ id: string }>('/roles', { name:newRole.name.trim(), description:newRole.description, permissions:[] })
      id = result.id
    }
    dialogOpen.value = false
    selectedId.value = id
    newRole.name = ''; newRole.description = ''
    await load()
    ElMessage.success('自定义角色已创建，请配置权限')
  } catch (error) { ElMessage.error(errorMessage(error, '角色创建失败')) }
  finally { saving.value = false }
}
async function removeRole() {
  const role = selectedRole.value
  if (!role || role.built_in) return
  try { await ElMessageBox.confirm(`确定删除角色「${role.name}」吗？`, '删除角色', {type:'warning'}) } catch { return }
  try {
    if (store.demoMode) store.options.roles = store.options.roles.filter(item => item.id !== role.id)
    else await api.delete(`/roles/${role.id}`)
    selectedId.value = ''
    await load()
    ElMessage.success('角色已删除')
  } catch (error) { ElMessage.error(errorMessage(error, '角色删除失败')) }
}
onMounted(load)
</script>

<template>
  <section v-loading="loading" class="role-layout"><div class="surface-card role-list"><div class="card-header"><div><h3>角色列表</h3><p>{{ roles.length }} 个角色模板</p></div><el-button v-if="canEdit" text type="primary" @click="dialogOpen=true"><el-icon><Plus /></el-icon></el-button></div><button v-for="(role,index) in roles" :key="role.id" :class="{active:selectedId===role.id}" @click="selectRole(role.id)"><span class="role-icon" :class="['blue','green','orange','violet'][index%4]"><el-icon><UserFilled /></el-icon></span><span class="role-copy"><strong>{{ role.name }}<small v-if="role.built_in">预设</small></strong><span>{{ role.description }}</span><small>{{ role.permissions.length }} 个权限点</small></span><el-icon><ArrowRight /></el-icon></button></div>
    <div class="surface-card permission-panel"><div class="permission-header"><div><span class="permission-kicker">PERMISSION CONFIGURATION</span><h2>{{ selectedRole?.name || '请选择角色' }}</h2><p>权限精确到核心模块下的每个操作按钮</p></div><div><el-button v-if="canEdit && selectedRole && !selectedRole.built_in" class="danger-button" @click="removeRole">删除角色</el-button><el-button v-if="canEdit" type="primary" :disabled="!selectedRole" :loading="saving" @click="savePermissions"><el-icon><Check /></el-icon>保存权限</el-button></div></div><div class="permission-note"><el-icon><InfoFilled /></el-icon>{{ canEdit ? '全局角色模板仅由系统管理员维护，修改会影响所有使用该角色的项目。' : '当前为只读视图；你可以在成员管理中为当前项目分配角色，不能修改全局权限。' }}</div><el-tree ref="treeRef" :data="permissionTree" :show-checkbox="canEdit" node-key="id" default-expand-all class="permission-tree"><template #default="{data}"><span :class="{'permission-parent':data.children}">{{ data.label }}</span></template></el-tree><div class="permission-footer"><span><el-icon><Lock /></el-icon>{{ canEdit ? '保存后，用户下次获取项目权限时生效' : '项目管理员仅可查看角色权限，全局配置由系统管理员维护' }}</span></div></div>
  </section>
  <el-dialog v-model="dialogOpen" title="新增自定义角色" width="480px"><el-form label-position="top" class="dialog-form"><el-form-item label="角色名称" required><el-input v-model="newRole.name" placeholder="如：质量工程师" /></el-form-item><el-form-item label="角色描述"><el-input v-model="newRole.description" type="textarea" :rows="3" placeholder="说明该角色的职责和权限范围" /></el-form-item></el-form><template #footer><el-button @click="dialogOpen=false">取消</el-button><el-button type="primary" :loading="saving" @click="addRole">创建角色</el-button></template></el-dialog>
</template>

<style scoped>
.role-layout { display:grid; grid-template-columns:330px minmax(0,1fr); gap:17px; }.role-list { padding-bottom:10px; }.role-list>button { width:calc(100% - 24px); margin:5px 12px; border:1px solid transparent; background:transparent; border-radius:9px; display:flex; align-items:flex-start; gap:11px; text-align:left; padding:14px 11px; cursor:pointer; }.role-list>button.active { border-color:#d8e0ff; background:#f5f7ff; }.role-icon { width:33px; height:33px; border-radius:8px; display:grid; place-items:center; flex-shrink:0; background:#edf0ff; color:#315efb; }.role-icon.green { color:#16865b; background:#ecf8f2; }.role-icon.orange { color:#b66a09; background:#fff6e5; }.role-icon.violet { color:#7957d5; background:#f3efff; }.role-copy { display:flex; flex-direction:column; flex:1; gap:5px; }.role-copy strong { font-size:12px; font-weight:600; }.role-copy strong small { font-size:8px; font-weight:400; color:#8a94a6; background:#eceff4; border-radius:3px; padding:2px 4px; margin-left:6px; }.role-copy>span { color:#8a94a6; font-size:9px; line-height:1.5; }.role-copy>small { font-size:9px; color:#a0a8b7; }.role-list>button>.el-icon { color:#c1c8d2; margin-top:9px; }.permission-header { display:flex; align-items:center; justify-content:space-between; padding:22px 24px; border-bottom:1px solid var(--line); }.permission-kicker { color:#315efb; font-size:8px; letter-spacing:1.2px; }.permission-header h2 { margin:5px 0; font-size:18px; }.permission-header p { margin:0; color:#98a2b3; font-size:10px; }.danger-button { color:#d92d20; }.permission-note { margin:17px 24px 5px; padding:10px 12px; background:#f6f8fc; border-radius:7px; color:#7a8494; font-size:10px; display:flex; gap:7px; align-items:center; }.permission-note .el-icon { color:#315efb; }.permission-tree { padding:13px 24px 20px; --el-tree-node-content-height:36px; }.permission-tree :deep(.el-tree-node__content) { border-radius:5px; }.permission-parent { font-weight:600; color:#344054; }.permission-footer { display:flex; justify-content:space-between; align-items:center; border-top:1px solid var(--line); padding:14px 24px; color:#98a2b3; font-size:9px; }.permission-footer>span { display:flex; align-items:center; gap:6px; }
</style>
