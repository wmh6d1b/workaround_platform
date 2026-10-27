<script setup lang="ts">import StateNoteEditor from './StateNoteEditor.vue'; defineProps<{ modelValue:string; disabled?:boolean }>(); defineEmits<{ 'update:modelValue':[value:string] }>()</script>
<template><StateNoteEditor :model-value="modelValue" label="禁用申请说明（必填）" placeholder="发起软件经理确认禁用时，请填写禁用原因" :disabled="disabled" @update:model-value="$emit('update:modelValue',$event)" /></template>
