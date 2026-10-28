<script setup lang="ts">
import { defaultWkdColumns, wkdColumnOptions } from '../utils/tablePreferences'
import type { WkdTableKey } from '../utils/tablePreferences'

const props = defineProps<{
  modelValue: string[]
  tableKey: WkdTableKey
}>()
const emit = defineEmits<{ 'update:modelValue': [columns: string[]] }>()

function reset() {
  emit('update:modelValue', [...defaultWkdColumns[props.tableKey]])
}
</script>

<template>
  <el-popover placement="bottom-end" :width="292" trigger="click">
    <template #reference>
      <el-button><el-icon><SetUp /></el-icon>显示字段<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
    </template>
    <div class="column-setting">
      <div class="column-setting-head">
        <div><strong>自定义表格字段</strong><p>字段偏好将保存到当前用户</p></div>
        <el-button text type="primary" @click="reset">恢复默认</el-button>
      </div>
      <el-checkbox-group :model-value="modelValue" @update:model-value="emit('update:modelValue', $event as string[])">
        <el-checkbox v-for="col in wkdColumnOptions" :key="col.key" :value="col.key" :label="col.key" :disabled="col.required">
          {{ col.label }}<span v-if="col.required" class="required-column">固定</span>
        </el-checkbox>
      </el-checkbox-group>
    </div>
  </el-popover>
</template>

<style scoped>
.column-setting-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:12px; }
.column-setting-head strong { color:#344054; font-size:14px; }
.column-setting-head p { color:#98a2b3; font-size:12px; margin:5px 0 0; }
.column-setting-head .el-button { flex:none; padding:0; height:24px; font-size:12px; }
.column-setting :deep(.el-checkbox-group) { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); column-gap:10px; }
.column-setting :deep(.el-checkbox) { display:flex; margin-right:0; height:34px; min-width:0; }
.column-setting :deep(.el-checkbox__label) { font-size:13px; white-space:nowrap; }
.required-column { color:#98a2b3; font-size:12px; margin-left:4px; }
</style>
