export const MAX_OPERATION_FILE_SIZE = 20 * 1024 * 1024

export interface UploadOperationFile {
  name: string
  content: string
  encoding?: 'base64'
  size?: number
  loading?: boolean
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  const chunkSize = 0x8000
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return btoa(binary)
}

export async function readOperationFile(file: File): Promise<UploadOperationFile> {
  return {
    name: file.name,
    content: arrayBufferToBase64(await file.arrayBuffer()),
    encoding: 'base64',
    size: file.size,
  }
}

export function operationFileSize(file: UploadOperationFile): number {
  if (typeof file.size === 'number') return file.size
  if (file.encoding === 'base64') return Math.floor(file.content.length * 3 / 4)
  return new TextEncoder().encode(file.content).length
}
