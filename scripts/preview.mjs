import { preview } from 'vite'
import config from '../vite.config.mjs'

const args = process.argv.slice(2)
const portIndex = args.indexOf('--port')
const port = Number(portIndex >= 0 ? args[portIndex + 1] : 7100)
const server = await preview({ ...config, configFile: false, preview: { host: '0.0.0.0', port } })
server.printUrls()
