// Reproducción de audio TTS buffer con un solo AudioContext reutilizable.
// `playBuffer` devuelve un handle; `stopPlayback()` corta la reproducción
// actual (vista previa o respuesta de PracticeSpeak).

let ctx: AudioContext | null = null
let current: { id: number; src: AudioBufferSourceNode; done: () => void } | null = null
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

/** Descarta cualquier reproducción en curso (resuelve también su `waited`). */
export function stopPlayback() {
  if (current) {
    const c = current
    current = null
    try {
      c.src.onended = null
      c.src.stop()
    } catch {
      // ya parado
    }
    // Completa el ciclo del handle: sin esto, quien espera `waited` se queda
    // colgado cuando el corte viene de fuera (interrupción, nueva respuesta).
    c.done()
  }
}

export interface PlaybackHandle {
  id: number
  stop: () => void
  get current(): boolean
  /** Resuelve cuando el audio termina de sonar (o al cortarlo). */
  waited: Promise<void>
}

/**
 * Reproduce un buffer de audio; `onEnded` se llama al terminar o al cortarlo.
 * Devuelve el control en cuanto el audio EMPIEZA (no al terminar); para
 * esperar el final usa `handle.waited`. Devuelve null si no hay AudioContext
 * (o falla la decodificación).
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
    let resolveWaited!: () => void
    const waited = new Promise<void>((r) => (resolveWaited = r))
    const done = () => {
      if (settled) return
      settled = true
      if (current && current.id === id) current = null
      onEnded?.()
      resolveWaited()
    }
    src.onended = done
    current = { id, src, done }
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
      waited,
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
