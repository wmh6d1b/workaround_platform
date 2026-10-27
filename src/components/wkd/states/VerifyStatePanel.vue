<script setup lang="ts">import StateNoteEditor from './StateNoteEditor.vue'; defineProps<{ modelValue:string; disabled?:boolean }>(); defineEmits<{ 'update:modelValue':[value:string] }>()</script>
<template><StateNoteEditor :model-value="modelValue" label="自验证说明" placeholder="记录验证过程、结果和仍需关注的问题" :disabled="disabled" @update:model-value="$emit('update:modelValue',$event)" /></template>
