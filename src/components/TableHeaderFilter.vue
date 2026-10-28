<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

export interface TableFilterOption {
  label: string
  value: string
}

const props = defineProps<{
  label: string
  values: string[]
  options: TableFilterOption[]
}>()
const emit = defineEmits<{ apply: [values: string[]] }>()
const open = ref(false)
const draft = ref<string[]>([])
const search = ref('')
const filteredOptions = computed(() => {
  const query = search.value.trim().toLowerCase()
  return query ? props.options.filter(option => `${option.label} ${option.value}`.toLowerCase().includes(query)) : props.options
})
const visibleValues = computed(() => filteredOptions.value.map(option => option.value))
const allVisibleSelected = computed(() => visibleValues.value.length > 0 && visibleValues.value.every(value => draft.value.includes(value)))
const someVisibleSelected = computed(() => !allVisibleSelected.value && visibleValues.value.some(value => draft.value.includes(value)))

function opened() {
  draft.value = [...props.values]
  search.value = ''
}
function toggleAll(checked: string | number | boolean) {
  const visible = new Set(visibleValues.value)
  draft.value = checked
    ? [...new Set([...draft.value, ...visibleValues.value])]
    : draft.value.filter(value => !visible.has(value))
}
function apply() {
  emit('apply', [...draft.value])
  open.value = false
}
function clear() {
  draft.value = []
  emit('apply', [])
  open.value = false
}
</script>

<template>
  <div class="table-header-filter">
    <span>{{ label }}</span>
    <el-popover v-model:visible="open" placement="bottom-start" :width="268" trigger="click" @show="opened">
      <template #reference>
        <button type="button" class="filter-trigger" :class="{ active: values.length }" :aria-label="`${label}筛选`" :title="values.length ? `${label}已筛选 ${values.length} 项` : `筛选${label}`">
          <el-icon><Filter /></el-icon><span v-if="values.length" class="filter-count">{{ values.length }}</span>
        </button>
      </template>
      <div class="filter-popover">
        <div class="filter-popover-title"><strong>筛选{{ label }}</strong><span v-if="draft.length">已选 {{ draft.length }} 项</span></div>
        <el-input v-if="options.length" v-model="search" clearable :prefix-icon="Search" placeholder="输入关键字过滤选项" class="filter-search" />
        <div v-if="filteredOptions.length" class="filter-select-all">
          <el-checkbox :model-value="allVisibleSelected" :indeterminate="someVisibleSelected" @change="toggleAll">全选当前结果</el-checkbox>
          <span>{{ filteredOptions.length }} 项</span>
        </div>
        <el-checkbox-group v-if="filteredOptions.length" v-model="draft" class="filter-options">
          <el-checkbox v-for="option in filteredOptions" :key="option.value" :value="option.value" :label="option.value">{{ option.label }}</el-checkbox>
        </el-checkbox-group>
        <el-empty v-else :description="options.length ? '没有匹配的筛选项' : '暂无可筛选项'" :image-size="42" />
        <div class="filter-popover-footer"><el-button text :disabled="!values.length && !draft.length" @click="clear">清空</el-button><el-button type="primary" size="small" @click="apply">确定</el-button></div>
      </div>
    </el-popover>
  </div>
</template>

<style scoped>
.table-header-filter { display:inline-flex; align-items:center; justify-content:center; gap:5px; }
.filter-trigger { position:relative; width:24px; height:24px; display:inline-grid; place-items:center; border:0; border-radius:5px; background:transparent; color:#98a2b3; cursor:pointer; transition:color .18s,background .18s; }
.filter-trigger:hover { color:#315efb; background:#edf0ff; }
.filter-trigger.active { color:#315efb; background:#e8edff; }
.filter-trigger .el-icon { font-size:14px; }
.filter-count { position:absolute; top:-4px; right:-7px; min-width:14px; height:14px; padding:0 3px; display:grid; place-items:center; border-radius:7px; background:#315efb; color:#fff; font-size:12px; line-height:1; border:1px solid #fff; transform:scale(.86); }
.filter-popover-title { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
.filter-popover-title strong { color:#344054; font-size:14px; }
.filter-popover-title span { color:#315efb; font-size:12px; }
.filter-search { margin-bottom:8px; }
.filter-search :deep(.el-input__inner) { font-size:13px; }
.filter-select-all { display:flex; align-items:center; justify-content:space-between; min-height:34px; padding:0 2px 6px; border-bottom:1px solid #edf0f4; margin-bottom:4px; }
.filter-select-all>span { color:#98a2b3; font-size:12px; }
.filter-select-all :deep(.el-checkbox__label), .filter-options :deep(.el-checkbox__label) { color:#475467; font-size:13px; }
.filter-options { display:flex; flex-direction:column; max-height:240px; overflow:auto; padding:1px 2px; }
.filter-options :deep(.el-checkbox) { height:34px; margin-right:0; flex:none; }
.filter-popover-footer { display:flex; align-items:center; justify-content:space-between; border-top:1px solid #edf0f4; margin-top:9px; padding-top:10px; }
.filter-popover :deep(.el-empty) { padding:10px 0; }
.filter-popover :deep(.el-empty__description) { margin-top:5px; font-size:12px; }
</style>
