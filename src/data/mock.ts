import type { ArtifactItem, BootstrapOptions, ExecuteStage, Wkd, WkdStatus } from '../types'

type Seed = [string, string, string, string, string, ExecuteStage, WkdStatus, string, Wkd['operation']]
const seeds: Seed[] = [
  ['WKD202610240012','修复晶圆加载后坐标偏移问题','AQ-2000','运动控制','陈墨','post_start','APPROVED','2026-10-24','执行脚本'],
  ['WKD202610230011','调整图像采集超时重试机制','AQ-2000','视觉系统','林舟','post_init','VERIFY','2026-10-23','上传文件'],
  ['WKD202610220010','规避高温状态下传感器误报','AQ-3000','温度控制','周然','post_upgrade','REVIEW','2026-10-22','执行命令'],
  ['WKD202610210009','更新设备自检参数配置','AQ-2000','系统服务','陈墨','pre_upgrade','NEW_WKD','2026-10-21','上传文件'],
  ['WKD202610200008','修复配方切换后参数未刷新','AQ-1000','配方管理','赵一','post_start','APPROVED','2026-10-20','执行脚本'],
  ['WKD202610190007','增加真空泵异常状态保护','AQ-3000','真空系统','林舟','post_init','VERIFY','2026-10-19','执行脚本'],
  ['WKD202610180006','临时关闭冗余日志采集','AQ-1000','系统服务','陈墨','pre_upgrade','DISABLED','2026-10-18','执行命令'],
  ['WKD202610170005','修正转盘回零顺序','AQ-2000','运动控制','赵一','post_upgrade','APPROVED','2026-10-17','执行脚本'],
  ['WKD202610160004','屏蔽无效光源校准告警','AQ-3000','视觉系统','林舟','post_start','REVIEW','2026-10-16','上传文件'],
  ['WKD202610150003','优化数据库连接断线恢复','AQ-1000','数据服务','周然','post_init','VERIFY','2026-10-15','执行命令'],
  ['WKD202610140002','补充安全门状态初始化','AQ-2000','安全控制','陈墨','pre_upgrade','APPROVED','2026-10-14','执行脚本'],
  ['WKD202610130001','修复报警记录重复写入','AQ-3000','数据服务','赵一','post_start','NEW_WKD','2026-10-13','执行脚本'],
]

export const demoOptions: BootstrapOptions = {
  projects: [
    { id: 'demo-project', name: '晶圆检测设备', code: 'WAFER-INSPECT', status: 'ENABLED' },
    { id: 'demo-project-2', name: '薄膜沉积设备', code: 'THIN-FILM', status: 'ENABLED' },
    { id: 'demo-project-3', name: '封装测试设备', code: 'PACKAGE-TEST', status: 'ENABLED' },
  ],
  versions: [
    { id: 'demo-version', name: 'V3.2.0', number: 'V3.2.0', project_id: 'demo-project', status: 'DEVELOPING' },
    { id: 'demo-version-31', name: 'V3.1.0', number: 'V3.1.0', project_id: 'demo-project', status: 'RELEASED' },
    { id: 'demo-version-30', name: 'V3.0.2', number: 'V3.0.2', project_id: 'demo-project', status: 'ARCHIVED' },
  ],
  machines: [
    { id: 'demo-machine', name: 'AQ-2000', project_id: 'demo-project', model: 'AQ 系列', location: 'A 栋实验室', status: 'RUNNING' },
    { id: 'demo-machine-3000', name: 'AQ-3000', project_id: 'demo-project', model: 'AQ 系列', location: 'B 栋实验室', status: 'RUNNING' },
    { id: 'demo-machine-1000', name: 'AQ-1000', project_id: 'demo-project', model: 'AQ 系列', location: '客户现场', status: 'MAINTENANCE' },
  ],
  subsystems: [
    { id: 'demo-subsystem', name: '运动控制', code: 'MOTION', project_id: 'demo-project', status: 'ENABLED' },
    { id: 'demo-subsystem-vision', name: '视觉系统', code: 'VISION', project_id: 'demo-project', status: 'ENABLED' },
    { id: 'demo-subsystem-temperature', name: '温度控制', code: 'TEMPERATURE', project_id: 'demo-project', status: 'ENABLED' },
    { id: 'demo-subsystem-service', name: '系统服务', code: 'SYSTEM', project_id: 'demo-project', status: 'ENABLED' },
    { id: 'demo-subsystem-recipe', name: '配方管理', code: 'RECIPE', project_id: 'demo-project', status: 'ENABLED' },
    { id: 'demo-subsystem-vacuum', name: '真空系统', code: 'VACUUM', project_id: 'demo-project', status: 'ENABLED' },
    { id: 'demo-subsystem-data', name: '数据服务', code: 'DATA', project_id: 'demo-project', status: 'ENABLED' },
    { id: 'demo-subsystem-safety', name: '安全控制', code: 'SAFETY', project_id: 'demo-project', status: 'ENABLED' },
  ],
  users: [
    { id: 'demo-admin', name: '张明', username: 'admin', employee_id: 'E1024', email: 'zhangming@wmp.local', role: '系统管理员' },
    { id: 'demo-owner', name: '陈墨', username: 'chenmo', employee_id: 'E1088', email: 'chenmo@wmp.local', role: '开发人员' },
    { id: 'demo-owner-lin', name: '林舟', username: 'linzhou', employee_id: 'E1102', email: 'linzhou@wmp.local', role: '软件经理' },
    { id: 'demo-owner-zhou', name: '周然', username: 'zhouran', employee_id: 'E1160', email: 'zhouran@wmp.local', role: '软件经理' },
    { id: 'demo-owner-zhao', name: '赵一', username: 'zhaoyi', employee_id: 'E1201', email: 'zhaoyi@wmp.local', role: '开发人员' },
  ],
  roles: [
    { id: 'demo-role-developer', name: '开发人员', description: '登记、验证 WKD，参与调试构建', built_in: true },
    { id: 'demo-role-manager', name: '软件经理', description: '审核规避措施并跟踪项目交付', built_in: true },
    { id: 'demo-role-project-admin', name: '项目管理员', description: '管理项目业务数据与正式构建', built_in: true },
    { id: 'demo-role-system-admin', name: '系统管理员', description: '拥有平台全部模块与操作权限', built_in: true },
  ],
}

const machineIds: Record<string, string> = { 'AQ-2000': 'demo-machine', 'AQ-3000': 'demo-machine-3000', 'AQ-1000': 'demo-machine-1000' }
const ownerIds: Record<string, string> = { 陈墨: 'demo-owner', 林舟: 'demo-owner-lin', 周然: 'demo-owner-zhou', 赵一: 'demo-owner-zhao' }

export const wkdList: Wkd[] = seeds.map((seed, index) => ({
  id: seed[0], number: seed[0], title: seed[1], machine: seed[2], machineIds: [machineIds[seed[2]]], subsystem: seed[3],
  subsystemId: demoOptions.subsystems.find(item => item.name === seed[3])?.id,
  owner: seed[4], ownerId: ownerIds[seed[4]], stage: seed[5], status: seed[6],
  createdAt: `${seed[7]} 09:12`, updatedAt: `2026-10-${String(26 - index % 5).padStart(2,'0')} 10:32`,
  project: '晶圆检测设备', projectId: 'demo-project', version: index > 4 && index % 2 ? 'V3.1.0' : 'V3.2.0',
  versionId: index > 4 && index % 2 ? 'demo-version-31' : 'demo-version',
  description: `${seed[1]}。通过标准化规避措施保证设备任务稳定执行，并保留完整验证和审核记录。`,
  operation: seed[8], executionType: 'AUTOMATED',
}))

const DEMO_WKD_STORAGE_KEY = 'wmp-demo-wkds'
try {
  const saved = JSON.parse(localStorage.getItem(DEMO_WKD_STORAGE_KEY) || 'null')
  if (Array.isArray(saved)) wkdList.splice(0, wkdList.length, ...saved)
} catch {
  localStorage.removeItem(DEMO_WKD_STORAGE_KEY)
}

export function persistDemoWkds() {
  localStorage.setItem(DEMO_WKD_STORAGE_KEY, JSON.stringify(wkdList))
}

export const artifacts: ArtifactItem[] = [
  { id: 'demo-artifact-1', number: 'BUILD-20261025-01', filename: 'WMP_AQ-2000_V3.2.0_20261025.tar.gz', project_id: 'demo-project', machine_id: 'demo-machine', type: 'RELEASE', size: 29989273, sha256: '8a7f000000000000000000000000000000000000000000000000000000c921', builder_id: 'demo-admin', created_at: '2026-10-25T16:30:00', items: wkdList.filter(item => item.machine === 'AQ-2000' && item.status === 'APPROVED').map((item, index) => ({ wkd_id: item.id, position: index + 1 })), demoContent: 'WMP Demo Release Artifact' },
  { id: 'demo-artifact-2', number: 'BUILD-20261022-01', filename: 'WMP_AQ-3000_V3.2.0_20261022.tar.gz', project_id: 'demo-project', machine_id: 'demo-machine-3000', type: 'RELEASE', size: 16986931, sha256: '35bd0000000000000000000000000000000000000000000000000000004e0a', builder_id: 'demo-admin', created_at: '2026-10-22T11:08:00', items: [{ wkd_id: wkdList[8].id, position: 1 }], demoContent: 'WMP Demo Release Artifact' },
]
