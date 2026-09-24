// Controlador de la conversación con PracticeSpeak: un único objeto reactivo que
// coordina texto, voz (VAD), TTS, histórico y correcciones.
import {
  analyzePronunciation,
  finishSession,
  getTtsBuffer,
  immersiveStream,
  sendLog,
  stripCorrections,
  transcribeAudioDetailed,
} from './api'
import { micRecorder } from './audio/recorder'
import { playBuffer, stopPlayback, unlockAudio } from './audio/playback'
import { vadFor, tooSmall } from './audio/vad'
import { LANG_NAMES_ES } from './i18n'
import { profileStore } from './profile.svelte'
import { settings } from './settings.svelte'
import { extractCompleted } from './speech'
import { toast } from './toast.svelte'
import type { Correction, PronunciationCoach, Turn } from './types'

/** Espera entre dos intentos de sintetizar la misma frase (red/edge inestable). */
const TTS_RETRY_DELAY_MS = 250
/** Tope para esperar a que una frase termine de sonar (AudioContext suspendido). */
const PLAYBACK_WAIT_MAX_MS = 15_000

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
  /** Despierta al drenaje cuando la cola vacía recibe frases nuevas. */
  private queueWake: (() => void) | null = null
  /** El estudiante ya habló por encima de PracticeSpeak (interrumpió). */
  private bargeInFired = false
  /** Generación del habla actual: la invalida un barge y cada respuesta nueva. */
  private speechGen = 0

  // -------------------------------------------------- entrenador de pronunciación
  /** Activo mientras se corrige una palabra: modela, escucha 2 intentos. */
  coachActive = $state(false)
  /** La palabra a practicar (en el idioma meta). */
  coachWord = $state('')
  /** Intentos restantes antes de seguir la conversación. */
  coachAttemptsLeft = $state(0)
  /** Frase reparada que el coach adivinó (para el turno del estudiante). */
  private coachGuessed = ''

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
    // Un intento del entrenador va directo a validar la palabra, no al tutor.
    if (this.coachActive) {
      await this.coachEvaluateAttempt(blob)
      return
    }
    this.orb = 'thinking'
    this.status = 'Procesando tu respuesta…'
    let transcript = ''
    let confidence: number | null = null
    try {
      sendLog('AUDIO_POST bytes=' + blob.size)
      const detail = await transcribeAudioDetailed(blob, settings.lang)
      transcript = detail.transcript || ''
      confidence = detail.confidence ?? null
    } catch (e) {
      sendLog('TRANSCRIBE_ERR ' + (e instanceof Error ? e.message : String(e)))
      this.orb = 'idle'
      this.status = 'Error transcribiendo. Intenta de nuevo.'
      return
    }
    sendLog('TRANSCRIPT ' + JSON.stringify(transcript.slice(0, 40)) + ' conf=' + confidence)
    if (!transcript) {
      this.status = 'No te entendí. Intenta de nuevo…'
      this.retryListen()
      return
    }
    // Confianza baja del ASR = probablemente pronunció mal: entra el entrenador
    // en vez de mandarle al tutor algo que no es lo que quisiste decir.
    if (confidence !== null && confidence < 0.55) {
      await this.startCoach(transcript)
      return
    }
    this.addTurn('user', transcript)
    await this.continueTurn(transcript, 'voice')
  }

  /** Modo entrenador: adivina la palabra, la corrige por voz y pide 2 intentos. */
  private async startCoach(badTranscript: string) {
    this.orb = 'thinking'
    this.status = 'Déjame adivinar lo que quisiste decir…'
    sendLog('COACH_START')
    let coach: PronunciationCoach = { guessed: badTranscript, target_word: '', tip: '' }
    try {
      // Contexto: el último turno del tutor ancla la reparación al vocabulario
      // de la pregunta que el estudiante está respondiendo.
      const lastTutor = [...this.history].reverse().find((t) => t.role === 'assistant')
      coach = await analyzePronunciation(badTranscript, settings.lang, lastTutor?.content ?? '')
    } catch {
      // Sin coach (p. ej. LLM ocupado): continúa la conversación normal.
    }
    const word = coach.target_word.trim()
    if (!word) {
      // No hay palabra clara que practicar: usa lo adivinado y sigue.
      this.addTurn('user', coach.guessed)
      await this.continueTurn(coach.guessed, 'voice')
      return
    }
    this.coachActive = true
    this.coachWord = word
    this.coachAttemptsLeft = 2
    this.coachGuessed = coach.guessed
    // Corrección por voz: lo que entendí, lo que quiso decir, tip y modelar.
    const msg =
      `Creo que quisiste decir "${coach.guessed}", ¿verdad? ` +
      (coach.tip ? coach.tip + ' ' : '') +
      `Escucha: "${word}". ` +
      `Ahora repite tú: "${word}". Te escucho — tienes 2 intentos.`
    this.addTurn('assistant', msg)
    await this.speakNow(msg)
    // Al terminar de modelar la palabra, escucha el intento 1.
    this.startListening()
  }

  /** Valida un intento del estudiante durante el entrenador. */
  private async coachEvaluateAttempt(blob: Blob) {
    this.busy = true
    this.orb = 'thinking'
    this.status = 'Escuchando tu intento…'
    let transcript = ''
    let confidence: number | null = null
    try {
      const detail = await transcribeAudioDetailed(blob, settings.lang)
      transcript = detail.transcript || ''
      confidence = detail.confidence ?? null
    } catch {
      transcript = ''
    }
    const word = this.coachWord
    // Error de red al transcribir: no consume intento, vuelve a escuchar.
    if (!transcript && confidence === null) {
      this.busy = false
      this.startListening()
      return
    }
    const norm = (s: string) =>
      s
        .toLowerCase()
        .replace(/[^\p{L}\p{N}\s']/gu, ' ')
        .trim()
    const said = norm(transcript)
    const target = norm(word)
    const hit =
      said.includes(target) ||
      (target.length > 6 && said.split(/\s+/).some((w) => w.startsWith(target.slice(0, Math.ceil(target.length * 0.7)))))
    // Si el ASR ya leyó la palabra objetivo en lo dicho, la pronunciación fue
    // inteligible: aceptamos sin mirar la confianza (el micrófono puede ser
    // ruidoso y un intento perfecto no merece rechazarse por un 0.53 global).
    const ok = hit
    sendLog(`COACH_ATTEMPT left=${this.coachAttemptsLeft} ok=${ok} said='${said.slice(0, 30)}'`)
    if (ok) {
      // ¡Logrado! Vuelve la conversación normal con lo que quiso decir.
      const praise = this.coachAttemptsLeft === 2 ? '¡Eso es! ' : '¡Muy bien! '
      this.coachActive = false
      this.coachWord = ''
      this.coachAttemptsLeft = 0
      const turn = this.coachGuessed ? `(${this.coachGuessed}) ` : ''
      this.addTurn('user', turn)
      await this.speakNow(praise + 'Sigamos.')
      await this.continueTurn(turn, 'voice')
      return
    }
    this.coachAttemptsLeft -= 1
    if (this.coachAttemptsLeft > 0) {
      await this.speakNow(`Casi. Escucha otra vez: "${word}". Último intento, dilo tú.`)
      this.busy = false
      this.startListening()
      return
    }
    // Sin intentos: sigue la conversación con la frase adivinada.
    const guessed = this.coachGuessed
    this.coachActive = false
    this.coachWord = ''
    this.coachAttemptsLeft = 0
    await this.speakNow('¡Tranquilo, esa palabra es difícil! La seguiremos practicando. Sigo contigo.')
    this.addTurn('user', guessed ? `(${guessed}) ` : '')
    await this.continueTurn(guessed, 'voice')
  }

  /** Habla un texto YA decidido (correcciones del entrenador) y espera el final. */
  private async speakNow(text: string) {
    const gen = ++this.speechGen
    this.spokenChars = 0
    this.streamFinished = true
    this.speechFailed = false
    this.speechQueue = [text]
    this.busy = true
    this.orb = 'speaking'
    this.status = ''
    await new Promise<void>((resolve) => {
      const job = this.drain(false).finally(() => {
        if (this.drainJob === job) this.drainJob = null
        resolve()
      })
      this.drainJob = job
    })
    this.busy = false
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
    else {
      // Respuesta ya consumida por el streaming: un drenaje aparcado esperando
      // frases jamás volvería a despertar sin esto (kickDrain no hace nada si
      // ya hay un drenaje vivo). Sin el toque, la sesión se quedaba en
      // "speaking" y nunca volvía a escuchar.
      this.queueWake?.()
      this.kickDrain()
    }
  }

  private enqueueSpeech(gen: number, chunks: string[]) {
    if (gen !== this.speechGen) return
    this.speechQueue.push(...chunks)
    this.queueWake?.()
    this.kickDrain()
  }

  private kickDrain() {
    if (this.drainJob) return
    this.drainJob = this.drain().finally(() => {
      this.drainJob = null
    })
  }

  /** Espera msec sin bloquear el event loop. */
  private sleep(ms: number): Promise<void> {
    return new Promise((r) => setTimeout(r, ms))
  }

  /**
   * Sintetiza y reproduce un fragmento, devolviendo si llegó a sonar.
   * Un solo fallo (red, rate-limit, salto) NO tumba la respuesta entera: se
   * reintenta de inmediato y, si aún falla, se aparca en `deferred` para un
   * último intento al final (todas las frases se leen, no solo las primeras).
   */
  private async speakChunk(chunk: string, gen: number, deferred: string[]): Promise<boolean> {
    for (let attempt = 0; attempt < 2; attempt++) {
      if (gen !== this.speechGen) return false
      let data: ArrayBuffer | null = null
      try {
        data = await getTtsBuffer(chunk, settings.lang, settings.gender, settings.ttsVoice[settings.lang], settings.speed)
      } catch {
        data = null
      }
      if (gen !== this.speechGen) return false
      if (!data) {
        if (attempt === 0) await this.sleep(TTS_RETRY_DELAY_MS)
        continue
      }
      try {
        const h = await playBuffer(data, () => {})
        if (gen !== this.speechGen) return false
        if (!h || !h.current) continue
        // Esperar a que la frase TERMINE de sonar (sin esto el bucle pasaba al
        // siguiente chunk y stopPlayback() de la entrada cortaba la anterior),
        // con tope de seguridad: si el AudioContext se suspende (pestaña en
        // segundo plano) onended nunca llega y no queremos congelar el habla.
        await Promise.race([h.waited, this.sleep(PLAYBACK_WAIT_MAX_MS)])
        return gen === this.speechGen
      } catch {
        continue
      }
    }
    deferred.push(chunk)
    return false
  }

  private async drain(standalone = false) {
    // La reproducción anterior se corta una sola vez al entrar (p. ej. al
    // interrumpir); dentro del bucle NUNCA se corta: playBuffer resuelve
    // cuando el audio EMPIEZA, no cuando termina.
    stopPlayback()
    const deferred: string[] = []
    let anySpoken = false
    while (this.running || standalone) {
      // Cola vacía con stream aún abierto: ESPERAR a que lleguen frases
      // (antes el bucle salía y el tramo final nunca se sintetizaba).
      while ((this.running || standalone) && !this.speechQueue.length && !this.streamFinished) {
        await new Promise<void>((wake) => (this.queueWake = wake)).finally(() => (this.queueWake = null))
      }
      if (!(this.running || standalone)) break
      if (!this.speechQueue.length) break
      const gen = this.speechGen
      const chunk = this.speechQueue.shift()!
      this.orb = 'speaking'
      this.speaking = true
      this.status = ''
      const played = await this.speakChunk(chunk, gen, deferred)
      if (gen !== this.speechGen) break
      if (played) anySpoken = true
    }
    // Último intento para las frases que fallaron: se leen tras el resto, que
    // ya sonaron; todo menos dejar la respuesta a medias.
    if ((this.running || standalone) && deferred.length) {
      const gen = this.speechGen
      for (const chunk of deferred) {
        if (gen !== this.speechGen) break
        if (await this.speakChunk(chunk, gen, [])) anySpoken = true
      }
    }
    if (this.streamFinished) {
      this.speechQueue = []
      this.speaking = false
      if (!this.running && !standalone) return
      if (this.bargeInFired) return
      if (standalone) {
        // Habla del entrenador: la escucha siguiente la gestiona quien llamó.
        return
      }
      if (!anySpoken) {
        sendLog(`TTS_FALLO pendientes=${deferred.length}`)
        this.orb = 'idle'
        this.setTranscriptOpen(true)
        this.status = 'Sin voz (¿internet?). Tu respuesta está arriba — toca el orbe para responder.'
        this.startListeningWithDelay()
      } else {
        if (deferred.length) sendLog(`TTS_PARCIAL faltaron=${deferred.length}`)
        this.orb = 'idle'
        if (this.coachActive) {
          // La escucha del intento ya la lanza quien activó el coach.
        } else {
          this.startListening()
        }
      }
    }
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
    // Despertar al drenaje aparcado: ve la cola vacía y vuelve a esperar
    // sobre un despertador nuevo (el turno del estudiante lo reactivará).
    this.queueWake?.()
  }

  private clearSpeech() {
    this.speechQueue = []
    this.spokenChars = 0
    this.streamFinished = false
    this.speechFailed = false
    this.speaking = false
    this.bargeInFired = false
    this.speechGen = 0
    // Si el drenaje está aparcado esperando frases, despertarlo para que
    // vea el reset y termine limpio (sin esto bloquearía el habla futura).
    this.queueWake?.()
  }

  private startListeningWithDelay() {
    this.cancelAutoListen()
    this.autoListenTimer = setTimeout(() => {
      if (this.running) this.startListening()
    }, 400)
  }
}

export const session = new SessionStore()