// Micro de voz: getUserMedia + MediaRecorder + VAD (fin de habla automático).
// El VAD (detector de nivel RMS) se ejecuta con requestAnimationFrame y se
// cancela al parar; el micrófono se pide una vez y se reutiliza.
import { DEFAULT_VAD, computeRms, type VADConfig } from './vad'

export interface RecorderEvents {
  onLevel?: (level: number) => void
  onPauseWarn?: () => void
  /** Voz sostenida detectada (≈100 ms) — usado para interrumpir a PracticeSpeak. */
  onBarge?: () => void
}

function pickMime(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
  for (const m of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m
  }
  return ''
}

export class MicRecorder {
  private stream: MediaStream | null = null
  private audioCtx: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private recorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private raf = 0
  private vadOn = false
  private lastVoiceAt: number | null = null
  private sawVoice = false
  private maxTimer: ReturnType<typeof setTimeout> | undefined
  private stopTimer: ReturnType<typeof setTimeout> | undefined
  private resolve!: (blob: Blob) => void
  private config: VADConfig = DEFAULT_VAD
  private warnPause = false
  private events: RecorderEvents = {}
  private bargeFired = false
  private bargeFrames = 0
  /** Promesa en vuelo del getUserMedia (evita pedir el permiso dos veces). */
  private micPromise: Promise<MediaStream> | null = null

  get recording(): boolean {
    return !!this.recorder
  }

  hasLiveMic(): boolean {
    return !!this.stream && this.stream.getAudioTracks().some((t) => t.readyState === 'live')
  }

  /** Pide el micrófono una sola vez por vida de la app y reutiliza el stream. */
  async ensureMic(): Promise<MediaStream> {
    if (this.micPromise && this.hasLiveMic()) return this.micPromise
    this.micPromise = navigator.mediaDevices
      .getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      .then((stream) => {
        this.stream = stream
        this.setupGraph(stream)
        return stream
      })
      .catch((err) => {
        this.micPromise = null
        throw err
      })
    return this.micPromise
  }

  private setupGraph(stream: MediaStream) {
    try {
      const Ctx = window.AudioContext || (window as any).webkitAudioContext
      if (!Ctx) return
      this.audioCtx = new Ctx()
      const src = this.audioCtx.createMediaStreamSource(stream)
      this.analyser = this.audioCtx.createAnalyser()
      this.analyser.fftSize = 2048
      src.connect(this.analyser)
    } catch {
      this.audioCtx = null
      this.analyser = null
    }
  }

  async begin(config: VADConfig = DEFAULT_VAD, events: RecorderEvents = {}): Promise<Blob> {
    this.config = config
    this.events = events
    this.bargeFired = false
    this.bargeFrames = 0
    const stream = await this.ensureMic()
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      try {
        await this.audioCtx.resume()
      } catch {
        // sin permisos de audio el VAD nivel se queda en 0
      }
    }
    const mime = pickMime()
    this.chunks = []
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    this.recorder = rec
    this.warnPause = false
    rec.ondataavailable = (e) => {
      if (e.data && e.data.size) this.chunks.push(e.data)
    }
    rec.onstop = () => {
      clearTimeout(this.maxTimer)
      clearTimeout(this.stopTimer)
      this.stopVAD()
      this.recorder = null
      const type = rec.mimeType || 'audio/webm'
      this.resolve(new Blob(this.chunks, { type }))
    }
    rec.onerror = () => {
      this.stopVAD()
      this.resolve(new Blob([], { type: 'audio/webm' }))
    }
    return new Promise<Blob>((resolve) => {
      this.resolve = resolve
      rec.start()
      this.startVAD()
    })
  }

  /** Para la grabación (también la dispara el VAD al detectar silencio). */
  stop(): void {
    if (this.recorder && this.recorder.state !== 'inactive') {
      this.recorder.stop()
    }
  }

  /** Cancela sin resolver blob (reset limpio de la interfaz). */
  cancel(): void {
    if (this.recorder) {
      clearTimeout(this.maxTimer)
      clearTimeout(this.stopTimer)
      this.stopVAD()
      try {
        this.recorder.onstop = null
        this.recorder.stop()
      } catch {
        // ya inactivo
      }
      this.recorder = null
    }
  }

  /** Detiene tracks, contextos de audio y analizadores. */
  release(): void {
    this.cancel()
    this.micPromise = null
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop())
      this.stream = null
    }
    if (this.audioCtx) {
      try {
        this.audioCtx.close()
      } catch {
        // ya cerrado
      }
      this.audioCtx = null
      this.analyser = null
    }
  }

  // ---------- VAD ----------
  private startVAD() {
    if (!this.analyser) return
    this.vadOn = true
    this.lastVoiceAt = null
    this.sawVoice = false
    const buf = new Uint8Array(this.analyser.fftSize)
    // Tope absoluto de grabación: un único timer (antes se programaba dentro
    // del loop de cada frame y se acumulaban cientos que cortaban a los 20 s).
    clearTimeout(this.maxTimer)
    this.maxTimer = setTimeout(() => this.stop(), this.config.maxMs)
    const loop = () => {
      if (!this.vadOn) return
      this.raf = requestAnimationFrame(loop)
      this.analyser!.getByteTimeDomainData(buf)
      const level = computeRms(buf)
      this.events.onLevel?.(level)
      const now = performance.now()
      if (level > this.config.threshold) {
        if (!this.sawVoice) {
          // Primera voz detectada: re-basa el umbral con el nivel real del
          // hablante (micrófono lejano o voz suave ya no vuelan al silencio).
          this.config.threshold = Math.min(0.012, level * 0.45)
        }
        this.sawVoice = true
        this.lastVoiceAt = now
        this.warnPause = false
        this.bargeFrames++
        if (this.events.onBarge && !this.bargeFired && this.bargeFrames >= 6) {
          this.bargeFired = true
          this.events.onBarge()
        }
      } else {
        this.bargeFrames = 0
        if (this.sawVoice && this.lastVoiceAt !== null) {
          const quiet = now - this.lastVoiceAt
          if (quiet > this.config.silenceMs * 0.55 && !this.warnPause) {
            this.warnPause = true
            this.events.onPauseWarn?.()
          }
          if (quiet > this.config.silenceMs) {
            this.stop()
            return
          }
        }
      }
    }
    this.raf = requestAnimationFrame(loop)
  }

  private stopVAD() {
    this.vadOn = false
    if (this.raf) cancelAnimationFrame(this.raf)
    this.raf = 0
    this.events.onLevel?.(0)
  }
}

const _recorder = new MicRecorder()
export const micRecorder = _recorder

// Al cerrar la app (o cambiar de pestaña en iOS), soltamos el micro para no
// dejarlo ocupado. Durante la sesión el stream se mantiene vivo para evitar
// que iOS/WebKit vuelva a pedir el permiso.
if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => _recorder.release())
}