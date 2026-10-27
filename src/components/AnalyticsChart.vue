<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
const props = defineProps<{ option: EChartsOption }>()
const el = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined
const resize = () => chart?.resize()
onMounted(() => { chart = echarts.init(el.value); chart.setOption(props.option); window.addEventListener('resize', resize) })
watch(() => props.option, value => chart?.setOption(value, true), { deep: true })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart?.dispose() })
</script>
<template><div ref="el" class="analytics-chart" /></template>
<style scoped>.analytics-chart { width: 100%; height: 100%; min-height: 260px; }</style>
