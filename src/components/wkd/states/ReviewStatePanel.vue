<script setup lang="ts">import StateNoteEditor from './StateNoteEditor.vue'; defineProps<{ modelValue:string; disabled?:boolean }>(); defineEmits<{ 'update:modelValue':[value:string] }>()</script>
<template><StateNoteEditor :model-value="modelValue" label="审核意见（必填）" placeholder="请填写审核意见，审核通过或驳回时均为必填" :disabled="disabled" @update:model-value="$emit('update:modelValue',$event)" /></template>
