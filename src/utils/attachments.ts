import { createSHA256 } from 'hash-wasm'
import { api } from '../api'
import type { AttachmentItem } from '../types'

export interface UploadSession {
  id: string
  project_id: string
  wkd_id: string | null
  status: 'OPEN' | 'EXPIRED' | 'CLOSED'
  expires_at: string
  attachments: AttachmentItem[]
}

export interface UploadStart extends AttachmentItem {
  object_key: string
  upload_url?: string
  upload_id?: string
  part_size?: number
  part_count?: number
}

interface CompletedPart {
  part_number: number
  etag: string
}

export function createUploadSession(projectId: string, wkdId?: string) {
  return api.post<UploadSession>('/files/upload-sessions', { project_id: projectId, wkd_id: wkdId || null })
}

export function getUploadSession(sessionId: string) {
  return api.get<UploadSession>(`/files/upload-sessions/${sessionId}`)
}

export function removeUpload(attachmentId: string) {
  return api.delete(`/files/uploads/${attachmentId}`)
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('上传已取消', 'AbortError')
}

export async function fileSha256(file: File, onProgress: (ratio: number) => void, signal?: AbortSignal) {
  const hasher = await createSHA256()
  hasher.init()
  const chunkSize = 8 * 1024 * 1024
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    throwIfAborted(signal)
    const buffer = await file.slice(offset, Math.min(offset + chunkSize, file.size)).arrayBuffer()
    hasher.update(new Uint8Array(buffer))
    onProgress(Math.min(offset + chunkSize, file.size) / file.size)
    await new Promise<void>(resolve => window.setTimeout(resolve, 0))
  }
  return hasher.digest('hex')
}

function putOnce(url: string, body: Blob, contentType: string | null, onProgress: (ratio: number) => void, signal?: AbortSignal) {
  return new Promise<string>((resolve, reject) => {
    throwIfAborted(signal)
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.timeout = 120_000
    if (contentType) xhr.setRequestHeader('Content-Type', contentType)
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onerror = () => reject(new Error('网络连接中断'))
    xhr.ontimeout = () => reject(new Error('上传请求超时'))
    xhr.onabort = () => reject(new DOMException('上传已取消', 'AbortError'))
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        const error = new Error(`文件上传失败（${xhr.status}）`) as Error & { status?: number }
        error.status = xhr.status
        return reject(error)
      }
      resolve(xhr.getResponseHeader('ETag') || '')
    }
    signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(body)
  })
}

async function putWithRetry(getUrl: () => Promise<string>, body: Blob, contentType: string | null,
                            onProgress: (ratio: number) => void, signal?: AbortSignal) {
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt += 1) {
    throwIfAborted(signal)
    try {
      const url = await getUrl()
      return await putOnce(url, body, contentType, onProgress, signal)
    } catch (error) {
      lastError = error
      const status = (error as { status?: number })?.status || 0
      if (signal?.aborted || (status >= 400 && status < 500) || attempt === 2) break
      onProgress(0)
      await new Promise<void>((resolve, reject) => {
        const timer = window.setTimeout(resolve, 500 * 2 ** attempt)
        signal?.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('上传已取消', 'AbortError')) }, { once: true })
      })
    }
  }
  throw lastError instanceof Error ? lastError : new Error('上传失败')
}

export async function uploadSessionAttachment(sessionId: string, file: File, callbacks: {
  onStart: (item: UploadStart) => void
  onProgress: (attachmentId: string, progress: number) => void
  signal?: AbortSignal
}) {
  const start = await api.post<UploadStart>(`/files/upload-sessions/${sessionId}/uploads`, {
    filename: file.name, size: file.size, content_type: file.type || null,
  })
  callbacks.onStart(start)
  try {
    const sha256 = await fileSha256(file, ratio => callbacks.onProgress(start.id, Math.floor(ratio * 10)), callbacks.signal)
    const parts: CompletedPart[] = []
    if (start.multipart) {
      const partSize = start.part_size!
      const partCount = start.part_count!
      for (let index = 0; index < partCount; index += 1) {
        throwIfAborted(callbacks.signal)
        const partNumber = index + 1
        const blob = file.slice(index * partSize, Math.min((index + 1) * partSize, file.size))
        const etag = await putWithRetry(async () => {
          const result = await api.post<{ upload_url: string }>(`/files/uploads/${start.id}/part-url`, { part_number: partNumber })
          return result.upload_url
        }, blob, null, ratio => {
          const uploaded = index * partSize + blob.size * ratio
          callbacks.onProgress(start.id, 10 + Math.floor((uploaded / file.size) * 89))
        }, callbacks.signal)
        if (!etag) throw new Error(`第 ${partNumber} 个分片未返回 ETag，请检查 RustFS CORS 暴露响应头`)
        parts.push({ part_number: partNumber, etag })
      }
    } else {
      await putWithRetry(async () => start.upload_url!, file, file.type || null,
        ratio => callbacks.onProgress(start.id, 10 + Math.floor(ratio * 89)), callbacks.signal)
    }
    throwIfAborted(callbacks.signal)
    const item = await api.post<AttachmentItem>(`/files/uploads/${start.id}/complete`, { sha256, parts })
    callbacks.onProgress(start.id, 100)
    return item
  } catch (error) {
    callbacks.onProgress(start.id, -1)
    throw error
  }
}
