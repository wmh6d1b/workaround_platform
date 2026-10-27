<script setup lang="ts">
import { ref } from 'vue'

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

function opened() {
  draft.value = [...props.values]
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
    <el-popover v-model:visible="open" placement="bottom-start" :width="220" trigger="click" @show="opened">
      <template #reference>
        <button type="button" class="filter-trigger" :class="{ active: values.length }" :aria-label="`${label}筛选`" :title="values.length ? `${label}已筛选 ${values.length} 项` : `筛选${label}`">
          <el-icon><Filter /></el-icon><span v-if="values.length" class="filter-count">{{ values.length }}</span>
        </button>
      </template>
      <div class="filter-popover">
        <div class="filter-popover-title"><strong>筛选{{ label }}</strong><span v-if="draft.length">已选 {{ draft.length }} 项</span></div>
        <el-checkbox-group v-model="draft" class="filter-options">
          <el-checkbox v-for="option in options" :key="option.value" :value="option.value" :label="option.value">{{ option.label }}</el-checkbox>
        </el-checkbox-group>
        <el-empty v-if="!options.length" description="暂无可筛选项" :image-size="42" />
        <div class="filter-popover-footer"><el-button text :disabled="!values.length && !draft.length" @click="clear">清空</el-button><el-button type="primary" size="small" @click="apply">确定</el-button></div>
      </div>
    </el-popover>
  </div>
</template>

<style scoped>
.table-header-filter { display:inline-flex; align-items:center; justify-content:center; gap:5px; }
.filter-trigger { position:relative; width:22px; height:22px; display:inline-grid; place-items:center; border:0; border-radius:5px; background:transparent; color:#a0a8b7; cursor:pointer; transition:color .18s,background .18s; }
.filter-trigger:hover { color:#315efb; background:#edf0ff; }
.filter-trigger.active { color:#315efb; background:#e8edff; }
.filter-trigger .el-icon { font-size:13px; }
.filter-count { position:absolute; top:-4px; right:-6px; min-width:13px; height:13px; padding:0 3px; display:grid; place-items:center; border-radius:7px; background:#315efb; color:#fff; font-size:8px; line-height:1; border:1px solid #fff; }
.filter-popover-title { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
.filter-popover-title strong { color:#344054; font-size:12px; }
.filter-popover-title span { color:#315efb; font-size:9px; }
.filter-options { display:flex; flex-direction:column; max-height:240px; overflow:auto; padding:1px 2px; }
.filter-options :deep(.el-checkbox) { height:31px; margin-right:0; }
.filter-options :deep(.el-checkbox__label) { color:#475467; font-size:11px; }
.filter-popover-footer { display:flex; align-items:center; justify-content:space-between; border-top:1px solid #edf0f4; margin-top:9px; padding-top:10px; }
.filter-popover :deep(.el-empty) { padding:10px 0; }
.filter-popover :deep(.el-empty__description) { margin-top:5px; font-size:10px; }
</style>
