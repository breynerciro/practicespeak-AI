// Reproducción de audio TTS buffer con un solo AudioContext reutilizable.
// `playBuffer` devuelve un handle; `stopPlayback()` corta la reproducción
// actual (vista previa o respuesta de Nova).

let ctx: AudioContext | null = null
let current: { id: number; src: AudioBufferSourceNode } | null = null
let nextId = 0

function ensureCtx(): AudioContext | null {
  if (!ctx) {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext
    if (!Ctx) return null
    ctx = new Ctx()
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {})
  return ctx
}

/** Descarta cualquier reproducción en curso. */
export function stopPlayback() {
  if (current) {
    try {
      current.src.onended = null
      current.src.stop()
    } catch {
      // ya parado
    }
    current = null
  }
}

export interface PlaybackHandle {
  id: number
  stop: () => void
  get current(): boolean
}

/**
 * Reproduce un buffer de audio; `onEnded` se llama al terminar o al cortarlo.
 * Devuelve null si no hay AudioContext (o falla la decodificación).
 */
export async function playBuffer(
  data: ArrayBuffer,
  onEnded?: () => void,
): Promise<PlaybackHandle | null> {
  const audio = ensureCtx()
  if (!audio) return null
  try {
    const buffer = await audio.decodeAudioData(data)
    const src = audio.createBufferSource()
    src.buffer = buffer
    src.connect(audio.destination)
    const id = ++nextId
    let settled = false
    const done = () => {
      if (settled) return
      settled = true
      if (current && current.id === id) current = null
      onEnded?.()
    }
    src.onended = done
    current = { id, src }
    src.start()
    return {
      id,
      get current() {
        return current?.id === id
      },
      stop: () => {
        if (current?.id === id) stopPlayback()
        done()
      },
    }
  } catch {
    onEnded?.()
    return null
  }
}

/** Precalienta el AudioContext (requiere un gesto del usuario, p. ej. tocar Iniciar). */
export function unlockAudio() {
  ensureCtx()
}