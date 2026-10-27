export interface WkdDraft {
  status: string
  visitKey: string
  lockVersion: number
  form: Record<string, unknown>
  note: string
  savedAt: string
}

function key(userId: string, wkdId: string, status: string, visitKey: string) {
  return `wmp-wkd-draft:${userId}:${wkdId}:${status}:${visitKey || 'current'}`
}

export function saveWkdDraft(userId: string, wkdId: string, draft: WkdDraft) {
  localStorage.setItem(key(userId, wkdId, draft.status, draft.visitKey), JSON.stringify(draft))
}

export function readWkdDraft(userId: string, wkdId: string, status: string, visitKey: string, lockVersion: number): WkdDraft | null {
  try {
    const draft = JSON.parse(localStorage.getItem(key(userId, wkdId, status, visitKey)) || 'null') as WkdDraft | null
    return draft?.status === status && draft.visitKey === visitKey && draft.lockVersion === lockVersion ? draft : null
  } catch { return null }
}

export function clearWkdDraft(userId: string, wkdId: string, status: string, visitKey: string) {
  localStorage.removeItem(key(userId, wkdId, status, visitKey))
}
