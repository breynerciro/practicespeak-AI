// Cliente API tipado contra el backend FastAPI.
import type {
  Correction,
  GrammarResult,
  Health,
  Profile,
  PronunciationScore,
  Stats,
  StreamEvent,
  TtsVoice,
} from './types'

// Código de acceso compartido (si el servidor lo pide). Lo rellena el store
// `access` al validar la puerta; también se puede fijar desde la URL (?code=).
let accessCode = ''

/** Fija el código que viaja en cada petición (cabecera X-Nova-Code). */
export function setAccessCode(code: string): void {
  accessCode = code
}

function headers(): Record<string, string> {
  const h: Record<string, string> = {}
  if (accessCode) h['X-Nova-Code'] = accessCode
  return h
}

async function jsonOrThrow(resp: Response): Promise<any> {
  let data: any = null
  try {
    data = await resp.json()
  } catch {
    data = null
  }
  if (!resp.ok) {
    const detail = data && (data.detail || data.error)
    throw new Error(typeof detail === 'string' ? detail : `Error (${resp.status})`)
  }
  return data
}

export function getHealth(code?: string): Promise<Health> {
  const h = code !== undefined ? { 'X-Nova-Code': code } : headers()
  return fetch('/api/health', { headers: h }).then((r) => r.json())
}

export function listProfiles(): Promise<Profile[]> {
  return fetch('/api/profiles', { headers: headers() }).then(jsonOrThrow)
}

export async function createProfile(name: string): Promise<Profile> {
  const d = await jsonOrThrow(
    await fetch('/api/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers() },
      body: JSON.stringify({ name }),
    }),
  )
  return { id: d.id, name: d.name, created_at: 0, sessions: 0 }
}

export interface StreamPayload {
  mode: 'start' | 'continue'
  language: string
  /** Solo en `start`: tema sugerido por el estudiante (vacío = elige Nova). */
  topic?: string
  /** Solo en `continue`: mensaje transcrito del estudiante. */
  message?: string
  history?: { role: string; content: string }[]
  session_id?: number | null
  profile_id?: number | null
}

/**
 * Streaming SSE: POST /api/immersive/stream → eventos `session_id` (start),
 * `topic`, `delta`*, `corrections`? y `done`/`error`. Devuelve un
 * async-iterable; un evento `error` no lanza, se entrega como dato.
 */
export async function* immersiveStream(p: StreamPayload): AsyncGenerator<StreamEvent> {
  const resp = await fetch('/api/immersive/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify({
      mode: p.mode,
      language: p.language,
      topic: p.mode === 'start' ? p.topic : undefined,
      message: p.mode === 'continue' ? p.message : undefined,
      history: p.mode === 'continue' ? p.history : undefined,
      session_id: p.mode === 'continue' ? p.session_id : undefined,
      profile_id: p.profile_id,
    }),
  })
  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => '')
    throw new Error(text ? `Error (${resp.status}): ${text.slice(0, 200)}` : `Error (${resp.status})`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const raw = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        for (const line of raw.split('\n')) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (!payload) continue
          try {
            yield JSON.parse(payload) as StreamEvent
          } catch {
            // evento ilegible: ignorar
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function transcribeAudio(blob: Blob, language: string): Promise<string> {
  const form = new FormData()
  form.append('audio', blob, 'audio.webm')
  form.append('expected', '')
  form.append('language', language)
  const resp = await fetch('/api/audio', { method: 'POST', headers: headers(), body: form })
  const data = await jsonOrThrow(resp)
  return (data as PronunciationScore).transcript || ''
}

export async function getTtsBuffer(
  text: string,
  language: string,
  gender: string,
  voice?: string,
  speed = 1,
): Promise<ArrayBuffer | null> {
  const params = new URLSearchParams({
    lang: language,
    gender: gender,
    text: text,
  })
  if (voice) params.set('voice', voice)
  if (speed !== 1) params.set('speed', String(speed))
  const resp = await fetch(`/api/tts?${params.toString()}`, { headers: headers() })
  if (!resp.ok) return null
  return resp.arrayBuffer()
}

export function listTtsVoices(lang: string): Promise<TtsVoice[]> {
  return fetch(`/api/tts/voices?lang=${encodeURIComponent(lang)}`, { headers: headers() })
    .then(jsonOrThrow)
    .then((d) => d.voices as TtsVoice[])
}

export function fetchStats(profileId?: number | null): Promise<Stats> {
  const q = profileId ? `?profile_id=${profileId}` : ''
  return fetch(`/api/stats${q}`, { headers: headers() }).then(jsonOrThrow)
}

export function ankiUrl(profileId?: number | null): string {
  return profileId ? `/api/export/anki?profile_id=${profileId}` : '/api/export/anki'
}

export function finishSession(sessionId: number): Promise<void> {
  return fetch('/api/session/finish', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify({ session_id: sessionId }),
  })
    .then(() => undefined)
    .catch(() => undefined)
}

export function correctGrammar(text: string, language: string): Promise<GrammarResult> {
  return fetch('/api/grammar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify({ text, language }),
  }).then(jsonOrThrow)
}

export function sendLog(msg: string): void {
  fetch('/api/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify({ msg }),
  }).catch(() => {})
}

export function stripCorrections(raw: Correction[] | null | undefined): Correction[] {
  return Array.isArray(raw) ? raw.filter((c) => c && typeof c.error === 'string') : []
}