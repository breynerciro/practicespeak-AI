// Controlador de la conversación con PracticeSpeak: un único objeto reactivo que
// coordina texto, voz (VAD), TTS, histórico y correcciones.
import {
  finishSession,
  getTtsBuffer,
  immersiveStream,
  sendLog,
  stripCorrections,
  transcribeAudio,
} from './api'
import { micRecorder } from './audio/recorder'
import { playBuffer, stopPlayback, unlockAudio } from './audio/playback'
import { vadFor, tooSmall } from './audio/vad'
import { LANG_NAMES_ES } from './i18n'
import { profileStore } from './profile.svelte'
import { settings } from './settings.svelte'
import { extractCompleted } from './speech'
import { toast } from './toast.svelte'
import type { Correction, Turn } from './types'

export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking'

class SessionStore {
  running = $state(false)
  busy = $state(false)
  speaking = $state(false)
  orb: OrbState = $state('idle')
  energy = $state(0)
  status = $state('')
  topic = $state('')
  history: Turn[] = $state([])
  corrections: Correction[] = $state([])
  correctionsOpen = $state(false)
  transcriptOpen = $state(false)
  sessionId = $state<number | null>(null)
  requestedTopic = $state('')
  /** Texto provisional mientras PracticeSpeak escribe (streaming). */
  streamText = $state<string | null>(null)
  /** Contador para pedir foco al input tras una respuesta en modo texto. */
  focusTick = $state(0)

  private autoListenTimer: ReturnType<typeof setTimeout> | undefined

  // ------------------------------------------------------- habla en streaming
  /** Frases completas pendientes de sintetizar y reproducir. */
  private speechQueue: string[] = []
  /** Caracteres del stream ya llevados a la cola de habla. */
  private spokenChars = 0
  private streamFinished = false
  private speechFailed = false
  private drainJob: Promise<void> | null = null
  /** Escucha de interrupción activa mientras PracticeSpeak habla. */
  private bargeOn = false
  /** El estudiante ya habló por encima de PracticeSpeak (interrumpió). */
  private bargeInFired = false
  /** El blob de la interrupción está siendo transcrito/procesado. */
  private bargeProcessing = false
  /** Generación del habla actual: la invalida un barge y cada respuesta nueva. */
  private speechGen = 0

  // ---------------------------------------------------------------- helpers
  resetStream() {
    this.streamText = null
  }

  addTurn(role: 'user' | 'assistant', content: string) {
    this.history = [...this.history, { role, content }]
  }

  showCorrections(corrections: Correction[]) {
    this.corrections = corrections
    this.correctionsOpen = corrections.length > 0
  }

  hideCorrections() {
    this.correctionsOpen = false
  }

  setCorrectionsOpen(open: boolean) {
    this.correctionsOpen = open
  }

  setTranscriptOpen(open: boolean) {
    this.transcriptOpen = open
  }

  // ---------------------------------------------------------------- session
  async start() {
    if (this.running || this.busy) return
    sendLog('INICIAR_CLICK modo=' + settings.mode)
    this.running = true
    this.resetStream()
    if (settings.mode === 'voice') unlockAudio()
    this.orb = 'thinking'
    this.status = 'Eligiendo tema y preparando la conversación…'

    if (settings.mode === 'voice') {
      try {
        await micRecorder.ensureMic()
      } catch (e) {
        const err = e as { name?: string; message?: string }
        sendLog('MIC_ERR ' + (err.name || '') + ' ' + (err.message || ''))
        this.running = false
        this.orb = 'idle'
        this.status = 'Necesito el micrófono para hablar contigo.'
        toast(err.name === 'NotAllowedError' ? 'Permite el micrófono en Ajustes → Safari.' : err.message || 'No se pudo acceder al micrófono.')
        this.reset()
        return
      }
    }

    const profileId = profileStore.current?.id ?? null
    const topic = this.requestedTopic
    try {
      this.history = []
      let reply = ''
      let corrections: Correction[] = []
      let gotTopic = ''
      this.resetStream()
      const gen = ++this.speechGen
      this.spokenChars = 0
      for await (const ev of immersiveStream({ mode: 'start', language: settings.lang, topic, profile_id: profileId })) {
        if (ev.type === 'session_id') this.sessionId = ev.session_id
        else if (ev.type === 'topic') gotTopic = ev.topic
        else if (ev.type === 'delta') {
          this.streamText = ev.text
          if (settings.mode === 'voice') this.pumpSpeech(gen, ev.text)
        }
        else if (ev.type === 'corrections') corrections = stripCorrections(ev.corrections)
        else if (ev.type === 'done') {
          reply = ev.reply
          corrections = stripCorrections(ev.corrections ?? corrections)
        } else if (ev.type === 'error') {
          throw new Error(ev.detail)
        }
      }
      this.resetStream()
      if (gotTopic) this.topic = gotTopic
      this.addTurn('assistant', reply)
      this.showCorrections(corrections)
      if (settings.mode === 'text') {
        this.orb = 'idle'
        this.status = 'Escribe tu respuesta en ' + (LANG_NAMES_ES[settings.lang] || 'inglés') + '…'
        this.transcriptOpen = false
        this.requestFocus()
      } else {
        this.finishSpeech(reply, gen)
      }
    } catch (e) {
      sendLog('IMMERSIVE_ERR ' + (e instanceof Error ? e.message : String(e)))
      this.errorStop(e instanceof Error ? e.message : '', 'No se pudo iniciar la conversación.')
    }
  }

  requestFocus() {
    this.focusTick++
  }

  cancelAutoListen() {
    clearTimeout(this.autoListenTimer)
  }

  async stop(notify = true) {
    this.cancelAutoListen()
    micRecorder.release()
    stopPlayback()
    const sid = this.sessionId
    if (sid !== null) finishSession(sid)
    this.reset()
    if (notify) this.status = 'Sesión terminada. Pulsa iniciar cuando quieras.'
  }

  private reset() {
    this.running = false
    this.busy = false
    this.clearSpeech()
    this.history = []
    this.sessionId = null
    this.topic = ''
    this.corrections = []
    this.correctionsOpen = false
    this.transcriptOpen = false
    this.resetStream()
    this.orb = 'idle'
  }

  private errorStop(errMsg: string, genericStatus: string) {
    this.running = false
    this.busy = false
    this.orb = 'idle'
    this.status = genericStatus
    if (errMsg) toast(errMsg)
    this.reset()
    this.status = genericStatus
  }

  // ---------------------------------------------------------------- text
  async sendText(raw: string) {
    const text = raw.trim()
    if (!text || !this.running || this.busy) return
    this.busy = true
    this.orb = 'thinking'
    this.status = 'PracticeSpeak está leyendo tu mensaje…'
    this.resetStream()
    this.addTurn('user', text)
    await this.continueTurn(text, 'text')
  }

  // ---------------------------------------------------------------- voice
  /** Punto de entrada al pulsar el orbe (mientras escucha, habla o termina). */
  orbTap() {
    if (!this.running || this.busy || settings.mode === 'text') return
    if (this.speaking) {
      this.bargeIn()
      return
    }
    if (micRecorder.recording) {
      micRecorder.stop()
    } else {
      this.startListening()
    }
  }

  async startListening() {
    if (!this.running || this.busy || this.speaking) return
    this.busy = true
    this.orb = 'listening'
    this.status = 'Escuchando… habla, o toca el orbe al terminar'
    try {
      const blob = await micRecorder.begin(vadFor(settings.micSensitivity), {
        onLevel: (level) => (this.energy = level),
        onPauseWarn: () => {
          this.status = 'Te sigo escuchando… (pausa)'
        },
      })
      this.busy = false
      if (!this.running) return
      await this.processVoiceBlob(blob)
    } catch (e) {
      sendLog('REC_ERR ' + (e instanceof Error ? e.message : String(e)))
      this.busy = false
      if (!this.running) return
      this.orb = 'idle'
      this.status = 'Micrófono no disponible.'
      const err = e as { name?: string; message?: string }
      toast(err.name === 'NotAllowedError' ? 'Permite el micrófono en Ajustes → Safari.' : err.message || 'Error con el micrófono.')
    }
  }

  private retryListen(delay = 1600) {
    this.cancelAutoListen()
    this.autoListenTimer = setTimeout(() => {
      if (this.running) this.startListening()
    }, delay)
  }

  private async processVoiceBlob(blob: Blob) {
    if (!this.running || settings.mode === 'text') return
    if (tooSmall(blob.size)) {
      sendLog('GRABACION_VACIA bytes=' + blob.size)
      this.status = 'No te escuché. Habla más cerca del micrófono…'
      this.retryListen()
      return
    }
    this.orb = 'thinking'
    this.status = 'Procesando tu respuesta…'
    let transcript = ''
    try {
      sendLog('AUDIO_POST bytes=' + blob.size)
      transcript = await transcribeAudio(blob, settings.lang)
    } catch (e) {
      sendLog('TRANSCRIBE_ERR ' + (e instanceof Error ? e.message : String(e)))
      this.orb = 'idle'
      this.status = 'Error transcribiendo. Intenta de nuevo.'
      return
    }
    sendLog('TRANSCRIPT ' + JSON.stringify(transcript.slice(0, 40)))
    if (!transcript) {
      this.status = 'No te entendí. Intenta de nuevo…'
      this.retryListen()
      return
    }
    this.addTurn('user', transcript)
    await this.continueTurn(transcript, 'voice')
  }

  private async continueTurn(text: string, origin: 'text' | 'voice') {
    this.resetStream()
    const gen = ++this.speechGen
    this.spokenChars = 0
    try {
      let reply = ''
      let corrections: Correction[] = []
      let topic = ''
      for await (const ev of immersiveStream({
        mode: 'continue',
        language: settings.lang,
        message: text,
        history: this.history.slice(0, -1),
        session_id: this.sessionId,
      })) {
        if (ev.type === 'topic') topic = ev.topic
        else if (ev.type === 'delta') {
          this.streamText = ev.text
          if (settings.mode === 'voice') this.pumpSpeech(gen, ev.text)
        }
        else if (ev.type === 'corrections') corrections = stripCorrections(ev.corrections)
        else if (ev.type === 'done') {
          reply = ev.reply
          corrections = stripCorrections(ev.corrections ?? corrections)
        } else if (ev.type === 'error') {
          throw new Error(ev.detail)
        }
      }
      this.resetStream()
      if (topic) this.topic = topic
      this.addTurn('assistant', reply)
      this.showCorrections(corrections)
      this.busy = false
      if (origin === 'text') {
        if (this.orb === 'thinking') this.orb = 'idle'
        this.status = 'Escribe tu respuesta…'
        this.requestFocus()
      } else {
        this.finishSpeech(reply, gen)
      }
    } catch (e) {
      this.busy = false
      this.orb = 'idle'
      const msg = e instanceof Error ? e.message : String(e)
      sendLog('CONTINUE_ERR ' + msg)
      if (origin === 'text') {
        this.status = 'Error de conexión con PracticeSpeak.'
        this.requestFocus()
      } else {
        this.status = 'Error de conexión con PracticeSpeak.'
        this.setTranscriptOpen(true)
      }
      toast(msg)
    }
  }

  // ------------------------------------------------ habla en streaming (TTS)
  /** Con cada delta del stream: encola las frases ya completas. */
  private pumpSpeech(gen: number, streamed: string) {
    if (gen !== this.speechGen) return
    if (streamed.length <= this.spokenChars) return
    const { consumed, sentences } = extractCompleted(streamed, this.spokenChars)
    if (sentences.length) this.enqueueSpeech(gen, sentences)
    if (consumed > this.spokenChars) this.spokenChars = Math.min(consumed, streamed.length)
  }

  /** Al recibir `done`: habla el tramo final e inicia la escucha al terminar. */
  private finishSpeech(reply: string, gen: number) {
    if (gen !== this.speechGen) return
    this.streamFinished = true
    const rest = reply.slice(this.spokenChars).trim()
    if (rest) this.enqueueSpeech(gen, [rest])
    else this.kickDrain()
  }

  private enqueueSpeech(gen: number, chunks: string[]) {
    if (gen !== this.speechGen) return
    this.speechQueue.push(...chunks)
    this.kickDrain()
  }

  private kickDrain() {
    if (this.drainJob) return
    this.drainJob = this.drain().finally(() => {
      this.drainJob = null
    })
  }

  private async drain() {
    while (this.running && this.speechQueue.length) {
      if (!this.bargeOn && !this.bargeInFired) this.startBarge()
      const gen = this.speechGen
      const chunk = this.speechQueue.shift()!
      this.orb = 'speaking'
      this.speaking = true
      this.status = ''
      stopPlayback()
      let ok = false
      try {
        const data = await getTtsBuffer(chunk, settings.lang, settings.gender, settings.ttsVoice[settings.lang], settings.speed)
        if (gen !== this.speechGen) break
        if (data) {
          const h = await playBuffer(data, () => {})
          ok = h !== null
        }
      } catch {
        ok = false
      }
      if (gen !== this.speechGen) break
      if (!ok) {
        this.speechFailed = true
        break
      }
    }
    if (this.streamFinished) {
      this.speechQueue = []
      this.speaking = false
      if (!this.running) return
      if (this.bargeInFired || this.bargeProcessing) return
      this.stopBarge()
      if (this.speechFailed) {
        this.speechFailed = false
        sendLog('TTS_FALLO')
        this.orb = 'idle'
        this.setTranscriptOpen(true)
        this.status = 'Sin voz (¿internet?). Tu respuesta está arriba — toca el orbe para responder.'
        this.startListeningWithDelay()
      } else {
        this.orb = 'idle'
        this.startListening()
      }
    }
  }

  /** Empieza a escuchar en segundo plano para que el estudiante interrumpa. */
  private startBarge() {
    this.bargeOn = true
    micRecorder
      .begin(vadFor(settings.micSensitivity), {
        onLevel: (level) => (this.energy = level),
        onBarge: () => this.bargeIn(),
      })
      .then(async (blob) => {
        this.bargeOn = false
        if (!this.running) return
        if (!this.bargeInFired) return
        this.bargeInFired = false
        this.bargeProcessing = true
        try {
          await this.processVoiceBlob(blob)
        } finally {
          this.bargeProcessing = false
        }
      })
      .catch(() => {
        this.bargeOn = false
      })
  }

  /** Interrupción: corta a PracticeSpeak y pasa a escucharte a ti. */
  private bargeIn() {
    if (!this.running || this.bargeInFired || this.orb !== 'speaking') return
    this.bargeInFired = true
    this.speechGen++
    this.speechQueue = []
    stopPlayback()
    this.speaking = false
    this.orb = 'listening'
    this.status = 'Vale, te escucho…'
    sendLog('BARGE_IN')
  }

  /** Cancela la escucha de fondo ya no necesaria (solo si no hubo interrupción). */
  private stopBarge() {
    this.bargeOn = false
    this.bargeInFired = false
    micRecorder.cancel()
  }

  private clearSpeech() {
    this.speechQueue = []
    this.spokenChars = 0
    this.streamFinished = false
    this.speechFailed = false
    this.speaking = false
    this.bargeOn = false
    this.bargeInFired = false
    this.bargeProcessing = false
    this.speechGen = 0
  }

  private startListeningWithDelay() {
    this.cancelAutoListen()
    this.autoListenTimer = setTimeout(() => {
      if (this.running) this.startListening()
    }, 400)
  }
}

export const session = new SessionStore()