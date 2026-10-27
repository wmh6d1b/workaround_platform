<script setup lang="ts">import StateNoteEditor from './StateNoteEditor.vue'; defineProps<{ modelValue:string; disabled?:boolean }>(); defineEmits<{ 'update:modelValue':[value:string] }>()</script>
<template><StateNoteEditor :model-value="modelValue" label="新建说明" placeholder="记录问题背景、规避思路和初始说明" :disabled="disabled" @update:model-value="$emit('update:modelValue',$event)" /></template>
