import entryScript from '../../backend/app/templates/wmp_entry.py?raw'
import type { Wkd } from '../types'

const encoder = new TextEncoder()

function jsonBytes(value: unknown) {
  return encoder.encode(JSON.stringify(value, null, 2))
}
function writeText(target: Uint8Array, offset: number, length: number, value: string) {
  target.set(encoder.encode(value).slice(0, length), offset)
}
function writeOctal(target: Uint8Array, offset: number, length: number, value: number) {
  writeText(target, offset, length, `${value.toString(8).padStart(length - 1, '0')}\0`)
}
function tarEntry(name: string, content: Uint8Array, mode = 0o644) {
  if (encoder.encode(name).length > 100) throw new Error(`包内路径过长：${name}`)
  const header = new Uint8Array(512)
  writeText(header, 0, 100, name)
  writeOctal(header, 100, 8, mode)
  writeOctal(header, 108, 8, 0)
  writeOctal(header, 116, 8, 0)
  writeOctal(header, 124, 12, content.length)
  writeOctal(header, 136, 12, Math.floor(Date.now() / 1000))
  writeText(header, 148, 8, '        ')
  writeText(header, 156, 1, '0')
  writeText(header, 257, 6, 'ustar\0')
  writeText(header, 263, 2, '00')
  const checksum = header.reduce((sum, value) => sum + value, 0)
  writeText(header, 148, 8, `${checksum.toString(8).padStart(6, '0')}\0 `)
  const padding = new Uint8Array((512 - content.length % 512) % 512)
  return [header, content, padding]
}
function base64Bytes(value: string) {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index)
  return bytes
}
async function sha256(content: Uint8Array) {
  const hash = await crypto.subtle.digest('SHA-256', content.slice().buffer as ArrayBuffer)
  return [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('')
}
function snapshot(row: Wkd) {
  const base = row.packageData || {}
  return {
    ...base, id: row.id, number: row.number || row.id, title: row.title, description: row.description,
    project_id: row.projectId, project: row.project, version_id: row.versionId, version: row.version,
    subsystem_id: row.subsystemId, subsystem: row.subsystem, owner_id: row.ownerId, owner: row.owner,
    machine_ids: row.machineIds || [], execution_type: row.executionType || 'AUTOMATED', status: row.status,
    stage: row.stage, custom_stage_name: row.customStageName || null,
    created_at: base.created_at || row.createdAt, updated_at: base.updated_at || row.updatedAt,
    operations: row.operations?.length ? row.operations : base.operations || [
      { type: 'UPLOAD_FILE', params: { target_path: '/opt/wmp/patches', overwrite: '覆盖', permission: '0644', files: [{ name: 'config.yaml', content: 'enabled: true\n' }] } },
      { type: 'LINUX_COMMAND', params: { command: 'true', workdir: '/opt/wmp', timeout: '30', exit_code: '0' } },
    ],
  }
}

export async function buildDemoExecutablePackage({ artifactId, kind, machineId, rows }: {
  artifactId: string
  kind: 'DEBUG' | 'RELEASE'
  machineId: string
  rows: Wkd[]
}) {
  const entries: Uint8Array[][] = []
  const add = (name: string, content: Uint8Array | string, mode = 0o644) => {
    entries.push(tarEntry(name, typeof content === 'string' ? encoder.encode(content) : content, mode))
  }
  add('wmp_entry.py', entryScript, 0o755)
  const packages = []
  const details = []
  for (const wkd of rows.map(snapshot)) {
    const packageName = wkd.number
    const packageDir = `packages/${packageName}`
    const stageParameter = wkd.stage === 'custom' ? wkd.custom_stage_name : wkd.stage
    if (wkd.execution_type === 'AUTOMATED' && !stageParameter) throw new Error(`${packageName} 缺少执行阶段参数`)
    const operations = []
    const sourceOperations = [...wkd.operations].sort((a, b) => (a.position || 0) - (b.position || 0))
    for (let index = 0; index < sourceOperations.length; index++) {
      const operation = sourceOperations[index]
      const position = operation.position || index + 1
      const params = JSON.parse(JSON.stringify(operation.params || {}))
      if (operation.type === 'UPLOAD_FILE') {
        const files = []
        for (let fileIndex = 0; fileIndex < (params.files || []).length; fileIndex++) {
          const item = params.files[fileIndex]
          if (!item.name || item.name.includes('/') || item.name.includes('\\')) throw new Error(`上传文件名非法：${item.name || '空文件名'}`)
          const content = item.encoding === 'base64' ? base64Bytes(String(item.content || '')) : encoder.encode(String(item.content || ''))
          const storedPath = `files/${String(position).padStart(2, '0')}/${String(fileIndex + 1).padStart(2, '0')}/${item.name}`
          add(`${packageDir}/${storedPath}`, content)
          files.push({ name: item.name, stored_path: storedPath, size: content.length, sha256: await sha256(content) })
        }
        params.files = files
      }
      operations.push({ position, type: operation.type, params })
    }
    add(`${packageDir}/package.json`, jsonBytes({
      schema_version: 1, package_name: packageName, stage: wkd.stage, stage_parameter: stageParameter,
      wkd: Object.fromEntries(Object.entries(wkd).filter(([key]) => key !== 'operations')), operations,
    }))
    packages.push({ package_name: packageName, wkd_id: wkd.id, stage_parameter: stageParameter,
      manifest: `${packageDir}/package.json`, operation_count: operations.length })
    details.push(wkd)
  }
  add('MANIFEST.json', jsonBytes({ schema_version: 1, artifact_id: artifactId, type: kind, project_id: rows[0]?.projectId,
    machine_id: machineId, created_at: new Date().toISOString(), entry: 'wmp_entry.py', packages }))
  add('WKD_LIST.json', jsonBytes(details))
  add('README.md', '# WMP 规避措施软件包\n\n```bash\npython3 wmp_entry.py <WKD编号> <阶段参数>\n```\n')
  const chunks = [...entries.flat(), new Uint8Array(1024)]
  const tar = new Blob(chunks as BlobPart[])
  const stream = tar.stream().pipeThrough(new CompressionStream('gzip'))
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer())
  const blob = new Blob([bytes], { type: 'application/gzip' })
  return { blob, size: blob.size, sha256: await sha256(bytes) }
}
