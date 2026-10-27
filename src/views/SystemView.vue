<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import BusinessManagement from '../components/system/BusinessManagement.vue'
import MemberManagement from '../components/system/MemberManagement.vue'
import RoleManagement from '../components/system/RoleManagement.vue'
import { can } from '../store'
const route = useRoute()
const router = useRouter()
const tab = computed({ get: () => String(route.params.tab || 'business'), set: value => router.push(`/system/${value}`) })
const tabs = computed(() => [{key:'business',label:'业务管理',icon:'Briefcase',permission:'system.business.view'},{key:'members',label:'成员管理',icon:'User',permission:'system.member.view'},{key:'roles',label:'角色管理',icon:'Key',permission:'system.role.view'}].filter(item => can(item.permission)))
</script>
<template>
  <div><PageHeader title="系统管理" description="维护平台业务数据、项目成员与精细化角色权限。" /><div class="system-tabs"><button v-for="item in tabs" :key="item.key" :class="{active:tab===item.key}" @click="tab=item.key"><el-icon><component :is="item.icon" /></el-icon>{{ item.label }}</button></div><BusinessManagement v-if="tab==='business' && can('system.business.view')" /><MemberManagement v-else-if="tab==='members' && can('system.member.view')" /><RoleManagement v-else-if="tab==='roles' && can('system.role.view')" /><el-empty v-else description="当前项目角色没有系统管理权限" /></div>
</template>
<style scoped>
.system-tabs { display:flex; gap:6px; margin-bottom:18px; border-bottom:1px solid #e2e6ed; }.system-tabs button { display:flex; gap:7px; align-items:center; height:40px; padding:0 16px; color:#7a8494; background:transparent; border:0; border-bottom:2px solid transparent; font-size:12px; margin-bottom:-1px; cursor:pointer; }.system-tabs button.active { color:#315efb; border-bottom-color:#315efb; font-weight:600; }.system-tabs button:hover { color:#315efb; }
</style>
