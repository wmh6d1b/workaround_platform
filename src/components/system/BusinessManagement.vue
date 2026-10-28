<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { api, errorMessage, formatDateTime, queryString } from '../../api'
import { ensureOptions, isInitializationProject, store } from '../../store'
import { canEditBusiness, canViewBusiness } from '../../permissions'
import type { OptionItem } from '../../types'

type Resource = 'projects' | 'versions' | 'machines' | 'subsystems'
const tab = ref<Resource>('projects')
const search = ref('')
const loading = ref(false)
const saving = ref(false)
const dialogOpen = ref(false)
const editing = ref<OptionItem | null>(null)
const datasets = reactive<Record<Resource, OptionItem[]>>({ projects: [], versions: [], machines: [], subsystems: [] })
const configs = { projects:{title:'项目管理',desc:'维护项目基础信息与负责人',name:'项目名称'}, versions:{title:'版本管理',desc:'管理项目下的软件版本与基线',name:'版本号'}, machines:{title:'机台管理',desc:'维护项目适用的设备机台',name:'机台名称'}, subsystems:{title:'子系统管理',desc:'管理子系统分类与责任归属',name:'子系统名称'} }
const statusOptions: Record<Resource, { value: string; label: string }[]> = {
  projects: [{value:'ENABLED',label:'启用'},{value:'DISABLED',label:'停用'}],
  versions: [{value:'DEVELOPING',label:'开发中'},{value:'RELEASED',label:'已发布'},{value:'ARCHIVED',label:'已归档'}],
  machines: [{value:'RUNNING',label:'运行中'},{value:'MAINTENANCE',label:'维护中'},{value:'STOPPED',label:'已停用'}],
  subsystems: [{value:'ENABLED',label:'启用'},{value:'DISABLED',label:'停用'}],
}
const statusLabels = Object.fromEntries(Object.values(statusOptions).flat().map(item => [item.value,item.label])) as Record<string,string>
const config = computed(() => configs[tab.value])
const canEditCurrent = computed(() => !(isInitializationProject.value && tab.value !== 'projects') && canEditBusiness(tab.value))
const visibleConfigs = computed(() => (Object.entries(configs) as [Resource, (typeof configs)[Resource]][]).filter(([resource]) => canViewBusiness(resource) && (!isInitializationProject.value || resource === 'projects')))
const rows = computed(() => datasets[tab.value].filter(item => Object.values(item).some(value => String(value ?? '').toLowerCase().includes(search.value.toLowerCase()))))
const form = reactive({ name:'', code:'', project_id:'', owner_id:'', status:'ENABLED', model:'', location:'', baseline_date:'' })
const displayName = (row: OptionItem) => String(row.number || row.name)
const projectName = (id?: string) => store.options.projects.find(item => item.id === id)?.name || '—'
const ownerName = (id?: string) => store.options.users.find(item => item.id === id)?.username || '—'

async function load() {
  loading.value = true
  try {
    if (store.demoMode) {
      const source = store.options[tab.value]
      datasets[tab.value] = tab.value === 'projects' ? source : source.filter(item => item.project_id === store.projectId)
    } else datasets[tab.value] = await api.get<OptionItem[]>(`/business/${tab.value}${queryString({ project_id: tab.value === 'projects' ? undefined : store.projectId })}`)
  } catch (error) { ElMessage.error(errorMessage(error, '业务数据加载失败')) }
  finally { loading.value = false }
}
function open(row?: OptionItem) {
  if (!canEditCurrent.value) return ElMessage.warning(tab.value === 'projects' ? '仅系统管理员可维护项目' : '当前项目角色没有维护权限')
  editing.value = row || null
  Object.assign(form, row ? { name: displayName(row), code: row.code || '', project_id: row.project_id || store.projectId, owner_id: row.owner_id || '', status: row.status || statusOptions[tab.value][0].value, model: row.model || '', location: row.location || '', baseline_date: row.baseline_date || '' } : { name:'', code:'', project_id:store.projectId, owner_id:'', status:statusOptions[tab.value][0].value, model:'', location:'', baseline_date:'' })
  dialogOpen.value = true
}
async function save() {
  if (!form.name.trim()) return ElMessage.warning(`请输入${config.value.name}`)
  if (['projects','subsystems'].includes(tab.value) && !form.code.trim()) return ElMessage.warning('请输入唯一标识')
  if (tab.value !== 'projects' && !form.project_id) return ElMessage.warning('请选择所属项目')
  saving.value = true
  const payload = { name: form.name.trim(), number: tab.value === 'versions' ? form.name.trim() : null, code: form.code.trim() || null, project_id: tab.value === 'projects' ? null : form.project_id, owner_id: form.owner_id || null, status: form.status, model: form.model || null, location: form.location || null, baseline_date: form.baseline_date || null }
  try {
    if (store.demoMode) {
      if (editing.value) Object.assign(editing.value, payload, { name: form.name.trim(), updated_at: new Date().toISOString() })
      else store.options[tab.value].unshift({ ...payload, id: `demo-${tab.value}-${Date.now()}`, name: form.name.trim(), created_at: new Date().toISOString() })
    } else {
      if (editing.value) await api.put(`/business/${tab.value}/${editing.value.id}`, payload)
      else await api.post(`/business/${tab.value}`, payload)
    }
    dialogOpen.value = false
    ElMessage.success(editing.value ? '修改已保存' : '新增成功')
    await ensureOptions(true)
    await load()
  } catch (error) { ElMessage.error(errorMessage(error, '保存失败')) }
  finally { saving.value = false }
}
async function remove(row: OptionItem) {
  try { await ElMessageBox.confirm(`确定删除「${displayName(row)}」吗？已被业务数据引用的对象将由后端拒绝删除。`, '确认删除', {type:'warning',confirmButtonText:'删除',cancelButtonText:'取消'}) } catch { return }
  try {
    if (store.demoMode) store.options[tab.value] = store.options[tab.value].filter(item => item.id !== row.id)
    else await api.delete(`/business/${tab.value}/${row.id}`)
    ElMessage.success('删除成功')
    await load()
  } catch (error) { ElMessage.error(errorMessage(error, '删除失败')) }
}
function changeTab() { search.value=''; load() }
onMounted(async () => { try { await ensureOptions(); await load() } catch (error) { ElMessage.error(errorMessage(error, '基础选项加载失败')) } })
watch(tab, changeTab)
watch(() => store.projectId, () => {
  if (isInitializationProject.value) tab.value = 'projects'
  else if (tab.value !== 'projects') load()
})
</script>

<template>
  <section class="surface-card business-card">
    <div class="business-layout"><nav class="business-nav"><span>业务配置</span><button v-for="([key,item]) in visibleConfigs" :key="key" :class="{active:tab===key}" @click="tab=key"><el-icon><component :is="key==='projects'?'OfficeBuilding':key==='versions'?'CollectionTag':key==='machines'?'Monitor':'SetUp'" /></el-icon>{{ item.title }}<small>{{ datasets[key].length }}</small></button></nav><div class="business-content"><div class="business-toolbar"><div><h2>{{ config.title }}</h2><p>{{ config.desc }}</p></div><el-button type="primary" v-if="canEditCurrent" @click="open()"><el-icon><Plus /></el-icon>新增</el-button></div><div class="business-search"><el-input v-model="search" :placeholder="`搜索${config.name}或其他信息`" :prefix-icon="Search" clearable style="width:280px" /><span>共 {{ rows.length }} 条记录</span></div>
      <el-table v-loading="loading" :data="rows" class="data-table"><el-table-column label="编号" width="115"><template #default="{row}"><span class="mono muted">{{ row.code || row.id.slice(0,8) }}</span></template></el-table-column><el-table-column :label="config.name" min-width="140"><template #default="{row}"><strong class="business-name">{{ displayName(row) }}</strong></template></el-table-column><el-table-column v-if="tab!=='projects'" label="所属项目" min-width="135"><template #default="{row}">{{ projectName(row.project_id) }}</template></el-table-column><el-table-column v-if="tab==='versions'" prop="baseline_date" label="基线日期" width="115" /><el-table-column v-if="tab==='machines'" prop="model" label="设备系列" width="110" /><el-table-column v-if="tab==='machines'" prop="location" label="部署位置" min-width="120" /><el-table-column label="负责人" width="90"><template #default="{row}">{{ ownerName(row.owner_id) }}</template></el-table-column><el-table-column label="状态" width="90"><template #default="{row}"><span class="business-status" :class="{archived:['ARCHIVED','MAINTENANCE','DISABLED','STOPPED'].includes(String(row.status))}"><i />{{ statusLabels[String(row.status)] || row.status }}</span></template></el-table-column><el-table-column label="更新时间" width="145"><template #default="{row}"><span class="muted">{{ formatDateTime(String(row.updated_at || row.created_at || '')) }}</span></template></el-table-column><el-table-column v-if="canEditCurrent" label="操作" width="110" align="right"><template #default="{row}"><el-button text type="primary" v-if="canEditCurrent" @click="open(row)">编辑</el-button><el-button text class="delete-button" v-if="canEditCurrent" @click="remove(row)">删除</el-button></template></el-table-column></el-table></div></div>
  </section>
  <el-dialog v-model="dialogOpen" :title="`${editing?'编辑':'新增'}${config.title.slice(0,-2)}`" width="520px"><el-form label-position="top" class="dialog-form"><el-form-item :label="config.name" required><el-input v-model="form.name" :placeholder="`请输入${config.name}`" /></el-form-item><el-form-item v-if="tab!=='projects'" label="所属项目" required><el-select v-model="form.project_id" style="width:100%"><el-option v-for="item in store.options.projects.filter(project => project.code !== 'WMP-USER-INIT')" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item v-if="['projects','subsystems'].includes(tab)" label="唯一标识" required><el-input v-model="form.code" placeholder="大写字母、数字或连字符" /></el-form-item><el-form-item v-if="tab==='versions'" label="基线日期"><el-date-picker v-model="form.baseline_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><template v-if="tab==='machines'"><el-form-item label="设备系列"><el-input v-model="form.model" /></el-form-item><el-form-item label="部署位置"><el-input v-model="form.location" /></el-form-item></template><el-form-item label="负责人"><el-select v-model="form.owner_id" clearable filterable style="width:100%"><el-option v-for="item in store.options.users" :key="item.id" :label="item.username" :value="item.id" /></el-select></el-form-item><el-form-item label="状态"><el-radio-group v-model="form.status"><el-radio v-for="item in statusOptions[tab]" :key="item.value" :value="item.value">{{ item.label }}</el-radio></el-radio-group></el-form-item></el-form><template #footer><el-button @click="dialogOpen=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
</template>

<style scoped>
.business-layout { display:grid; grid-template-columns:185px minmax(0,1fr); min-height:490px; }.business-nav { border-right:1px solid var(--line); padding:19px 12px; }.business-nav>span { display:block; color:#a0a8b7; font-size:9px; letter-spacing:1px; padding:0 11px 12px; }.business-nav button { width:100%; height:41px; border:0; background:transparent; border-radius:7px; color:#667085; display:flex; align-items:center; gap:9px; padding:0 11px; font-size:11px; margin:3px 0; cursor:pointer; }.business-nav button.active { background:#edf0ff; color:#315efb; font-weight:600; }.business-nav button small { margin-left:auto; font-size:9px; background:#f0f2f5; padding:2px 6px; border-radius:4px; }.business-nav button.active small { background:#dce4ff; }.business-content { min-width:0; }.business-toolbar { min-height:82px; padding:19px 20px; display:flex; align-items:center; justify-content:space-between; }.business-toolbar h2 { margin:0; font-size:15px; }.business-toolbar p { margin:5px 0 0; color:#98a2b3; font-size:10px; }.business-search { padding:0 20px 16px; display:flex; align-items:center; justify-content:space-between; }.business-search>span { font-size:10px; color:#98a2b3; }.business-name { font-weight:500; font-size:11px; }.business-status { display:inline-flex; align-items:center; gap:5px; color:#16865b; font-size:10px; }.business-status i { width:5px; height:5px; background:currentColor; border-radius:50%; }.business-status.archived { color:#8b95a5; }.delete-button { color:#98a2b3; }.delete-button:hover { color:#d92d20; }
</style>
