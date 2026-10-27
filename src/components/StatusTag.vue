<script setup lang="ts">
import { computed } from 'vue'
import type { WkdStatus } from '../types'
const props = defineProps<{ status: WkdStatus }>()
const meta = computed(() => ({
  NEW_WKD: { label: '新建规避措施', type: 'neutral' },
  VERIFY: { label: '自验证', type: 'warning' },
  REVIEW: { label: '软件经理审核', type: 'processing' },
  APPROVED: { label: '审核通过', type: 'success' },
  DISABLE_CONFIRM: { label: '软件经理确认禁用', type: 'warning' },
  DISABLED: { label: '禁用', type: 'disabled' },
}[props.status]))
</script>
<template><span class="status-tag" :class="`status-${meta.type}`"><i />{{ meta.label }}</span></template>
