// Tipos compartidos con el backend (espejo de backend/schemas.py + respuestas)

export type Language = 'en' | 'pt' | 'fr' | 'de' | 'it' | 'es' | 'ru' | 'zh'

export type Mode = 'voice' | 'text'

export interface Turn {
  role: 'user' | 'assistant'
  content: string
}

export interface Correction {
  error: string
  correction: string
  explanation?: string
}

export interface GrammarError {
  error: string
  correction: string
  explanation?: string
}

export interface GrammarResult {
  corrected: string
  errors: GrammarError[]
  summary: string
}

export interface PronunciationScore {
  score: number
  transcript: string
  feedback: string[]
  missing: string[]
}

export interface Profile {
  id: number
  name: string
  created_at: number
  sessions: number
}

export interface Stats {
  total_sessions: number
  sessions_last_7d: number
  total_corrections: number
  by_language: Record<string, number>
  top_topics_with_errors: Record<string, number>
}

export interface Health {
  ollama: boolean
  model: string
  whisper: string
  ok: boolean
  public_hostname: string
  /** Puerto HTTPS público anunciado (p. ej. 443 con Tailscale Funnel). */
  https_port?: number
  /** true si el servidor exige código de acceso compartido. */
  needs_code?: boolean
}

export interface Voice {
  lang: Language
  gender: 'female' | 'male'
}

export interface TtsVoice {
  id: string
  name: string
  source: 'local' | 'edge'
  installed: boolean
}

// Eventos del streaming SSE (/api/immersive/stream)
export type StreamEvent =
  | { type: 'topic'; topic: string }
  | { type: 'delta'; text: string }
  | { type: 'corrections'; corrections: Correction[] }
  | { type: 'session_id'; session_id: number }
  | { type: 'done'; reply: string; corrections: Correction[] }
  | { type: 'error'; detail: string }