import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))

vi.mock('./api', () => ({
  api: { get: getMock },
  queryString: (values: Record<string, string | null | undefined>) => {
    const params = new URLSearchParams()
    Object.entries(values).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) params.set(key, value)
    })
    const text = params.toString()
    return text ? `?${text}` : ''
  },
}))

vi.mock('./data/mock', () => ({
  demoOptions: { projects: [], versions: [], machines: [], subsystems: [], users: [], roles: [] },
}))

const realOptions = {
  projects: [{ id: 'project-real', name: '真实项目', code: 'REAL' }],
  versions: [{ id: 'version-real', project_id: 'project-real', number: 'V1.0.0', name: 'V1.0.0' }],
  machines: [],
  subsystems: [],
  users: [],
  roles: [],
}

beforeEach(() => {
  vi.resetModules()
  getMock.mockReset()
  const values = new Map<string, string>([
    ['wmp-session', JSON.stringify({ id: 'member-1', username: 'member', employeeId: 'E1001', role: '项目成员', permissions: ['home.view'], demo: false })],
    ['wmp-token', 'member-token'],
  ])
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  })
})

describe('项目上下文初始化', () => {
  it('并发调用共享请求，任一调用返回时项目均已就绪', async () => {
    let resolveOptions!: (value: typeof realOptions) => void
    getMock.mockImplementation((path: string) => {
      if (path === '/bootstrap/options') return new Promise(resolve => { resolveOptions = resolve })
      return Promise.reject(new Error(`未预期的请求：${path}`))
    })
    const { ensureOptions, store } = await import('./store')

    const layoutReady = ensureOptions()
    const pageReady = ensureOptions()
    expect(getMock).toHaveBeenCalledTimes(1)

    resolveOptions(realOptions)
    await layoutReady
    expect(store.projectId).toBe('project-real')
    expect(store.optionsReady).toBe(true)

    await pageReady
    expect(store.projectId).toBe('project-real')
    expect(getMock).toHaveBeenCalledTimes(1)
  })

  it('项目切换期间忽略旧权限请求的迟到结果', async () => {
    const resolvers = new Map<string, (value: { permissions: string[] }) => void>()
    getMock.mockImplementation((path: string) => {
      if (path.startsWith('/auth/permissions')) {
        const projectId = new URLSearchParams(path.split('?')[1]).get('project_id')!
        return new Promise<{ permissions: string[] }>(resolve => resolvers.set(projectId, resolve))
      }
      return Promise.reject(new Error(`未预期的请求：${path}`))
    })
    const { refreshPermissions, store } = await import('./store')

    store.projectId = 'project-a'
    const oldRequest = refreshPermissions()
    store.projectId = 'project-b'
    const currentRequest = refreshPermissions()

    resolvers.get('project-b')!({ permissions: ['wkd.view'] })
    await currentRequest
    resolvers.get('project-a')!({ permissions: ['project.role.view'] })
    await oldRequest

    expect(store.session?.permissions).toEqual(['wkd.view'])
  })
})
