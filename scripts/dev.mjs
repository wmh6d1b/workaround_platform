import { createServer } from 'vite'
import config from '../vite.config.mjs'

const args = process.argv.slice(2)
const valueOf = (name) => {
  const index = args.indexOf(name)
  return index >= 0 && args[index + 1] && !args[index + 1].startsWith('--') ? args[index + 1] : undefined
}
const port = Number(valueOf('--port') || config.server?.port || 7100)
const host = args.includes('--host') ? (valueOf('--host') || '0.0.0.0') : config.server?.host
const server = await createServer({ ...config, configFile: false, server: { ...config.server, host, port } })
await server.listen()
server.printUrls()

const shutdown = async () => {
  await server.close()
  process.exit(0)
}
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
