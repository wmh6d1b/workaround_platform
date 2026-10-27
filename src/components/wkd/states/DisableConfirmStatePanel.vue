<script setup lang="ts">import StateNoteEditor from './StateNoteEditor.vue'; defineProps<{ modelValue:string; disabled?:boolean }>(); defineEmits<{ 'update:modelValue':[value:string] }>()</script>
<template><StateNoteEditor :model-value="modelValue" label="禁用确认意见（必填）" placeholder="请填写确认禁用或拒绝禁用的意见" :disabled="disabled" @update:model-value="$emit('update:modelValue',$event)" /></template>
