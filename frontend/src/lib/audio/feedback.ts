// Feedback sonoro sutil para acciones del usuario (beep al empezar a escuchar).

let ctx: AudioContext | null = null

function ensureCtx(): AudioContext | null {
  if (!ctx) {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext
    if (!Ctx) return null
    ctx = new Ctx()
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {})
  return ctx
}

/**
 * Beep suave al empezar a escuchar (100ms, 440Hz, volumen bajo).
 * Da feedback auditivo claro sin ser invasivo.
 */
export function playListenBeep(): void {
  const audio = ensureCtx()
  if (!audio) return
  try {
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.frequency.value = 440
    gain.gain.value = 0.08
    osc.connect(gain)
    gain.connect(audio.destination)
    osc.start()
    osc.stop(audio.currentTime + 0.1)
  } catch {
    // sin audio context, no hacer nada
  }
}

/** Precalienta el AudioContext (requiere gesto del usuario). */
export function unlockFeedback(): void {
  ensureCtx()
}
