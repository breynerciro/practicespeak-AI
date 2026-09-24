import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { StreamEvent } from './types'

const mocks = vi.hoisted(() => ({
  immersiveStream: vi.fn(),
  finishSession: vi.fn(),
  transcribeAudio: vi.fn(),
  getTtsBuffer: vi.fn(),
  sendLog: vi.fn(),
  listProfiles: vi.fn(),
  createProfile: vi.fn(),
  playBuffer: vi.fn(),
  stopPlayback: vi.fn(),
  unlockAudio: vi.fn(),
  ensureMic: vi.fn(),
  beginRec: vi.fn(),
  releaseRec: vi.fn(),
  stopRec: vi.fn(),
  cancelRec: vi.fn(),
  wakeScreenOn: vi.fn(),
}))

vi.mock('./api', () => ({
  finishSession: mocks.finishSession,
  getTtsBuffer: mocks.getTtsBuffer,
  immersiveStream: mocks.immersiveStream,
  listProfiles: mocks.listProfiles,
  createProfile: mocks.createProfile,
  sendLog: mocks.sendLog,
  stripCorrections: (raw: unknown[] | null | undefined) =>
    Array.isArray(raw) ? raw.filter((c) => c && typeof (c as { error?: string }).error === 'string') : [],
}))

vi.mock('./audio/playback', () => ({
  playBuffer: mocks.playBuffer,
  stopPlayback: mocks.stopPlayback,
  unlockAudio: mocks.unlockAudio,
}))

vi.mock('./audio/recorder', () => ({
  micRecorder: {
    get recording() {
      return false
    },
    ensureMic: mocks.ensureMic,
    begin: mocks.beginRec,
    stop: mocks.stopRec,
    release: mocks.releaseRec,
    cancel: mocks.cancelRec,
  },
}))

vi.mock('./audio/vad', () => ({
  DEFAULT_VAD: { threshold: 0.03, silenceMs: 2200, maxMs: 20000, minBlobBytes: 1500 },
  tooSmall: (size: number) => size < 100,
  vadFor: () => ({ threshold: 0.03, silenceMs: 2200, maxMs: 20000, minBlobBytes: 1500 }),
}))

vi.mock('./wake-lock', () => ({
  wakeScreenOn: mocks.wakeScreenOn,
}))

import { session } from './session.svelte'
import { settings } from './settings.svelte'

const docs: Record<string, StreamEvent[]> = {
  start: [
    { type: 'session_id', session_id: 5 },
    { type: 'topic', topic: 'travel' },
    { type: 'delta', text: 'Hell' },
    { type: 'delta', text: 'Hello!' },
    { type: 'done', reply: 'Hello!', corrections: [] },
  ],
  continue: [
    { type: 'topic', topic: 'travel' },
    { type: 'delta', text: 'Nic' },
    { type: 'delta', text: 'Nice!' },
    { type: 'done', reply: 'Nice!', corrections: [] },
  ],
}

async function* fakeStream(events: StreamEvent[]): AsyncGenerator<StreamEvent> {
  for (const ev of events) yield ev
}

describe('session (modo texto)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.immersiveStream.mockImplementation(async function* (p: { mode: string }) {
      yield* fakeStream(docs[p.mode === 'start' ? 'start' : 'continue'])
    })
    mocks.finishSession.mockResolvedValue(undefined)
    mocks.listProfiles.mockResolvedValue([])
    mocks.ensureMic.mockResolvedValue(undefined)
    mocks.beginRec.mockResolvedValue(new Blob(['audio data'.repeat(100)]))
    mocks.releaseRec.mockResolvedValue(undefined)
    mocks.playBuffer.mockResolvedValue({ id: 1, stop: vi.fn(), get current() { return true }, waited: Promise.resolve() })
    settings.setMode('text')
    session.stop(false)
  })

  it('arranca, guarda la sesión y muestra el saludo', async () => {
    await session.start()
    expect(session.running).toBe(true)
    expect(session.sessionId).toBe(5)
    expect(session.topic).toBe('travel')
    expect(session.history).toHaveLength(1)
    expect(session.history[0]).toEqual({ role: 'assistant', content: 'Hello!' })
    expect(mocks.immersiveStream).toHaveBeenCalledWith({ mode: 'start', language: 'en', topic: '', profile_id: null })
  })

  it('ignora un segundo arranque mientras ya corre', async () => {
    await session.start()
    await session.start()
    expect(mocks.immersiveStream).toHaveBeenCalledTimes(1)
    expect(session.history).toHaveLength(1)
  })

  it('envía un mensaje y continúa la conversación', async () => {
    await session.start()
    await session.sendText('  Hello there!  ')
    expect(session.history).toHaveLength(3)
    expect(session.history[1]).toEqual({ role: 'user', content: 'Hello there!' })
    expect(session.history[0].content).toBe('Hello!')
    expect(session.history[2]).toEqual({ role: 'assistant', content: 'Nice!' })
    expect(session.busy).toBe(false)
    expect(mocks.immersiveStream).toHaveBeenCalledTimes(2)
    const second = mocks.immersiveStream.mock.calls[1][0] as { mode: string; message: string; history: unknown[]; session_id: number }
    expect(second).toMatchObject({ mode: 'continue', message: 'Hello there!', session_id: 5 })
    expect(second.history).toEqual([{ role: 'assistant', content: 'Hello!' }])
  })

  it('no envía texto vacío', async () => {
    await session.start()
    await session.sendText('   ')
    expect(mocks.immersiveStream).toHaveBeenCalledTimes(1)
    expect(session.history).toHaveLength(1)
  })

  it('actualiza el historial de correcciones al llegar el evento done', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 5 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'done', reply: 'Hola', corrections: [{ error: 'i go', correction: 'I go', explanation: 'pasado' }] }
    })
    await session.start()
    expect(session.corrections).toEqual([{ error: 'i go', correction: 'I go', explanation: 'pasado' }])
    expect(session.correctionsOpen).toBe(true)
    expect(session.streamText).toBeNull()
  })

  it('termina la sesión llamando a finishSession', async () => {
    await session.start()
    await session.stop(false)
    expect(mocks.finishSession).toHaveBeenCalledWith(5)
    expect(session.running).toBe(false)
    expect(session.history).toHaveLength(0)
    expect(session.sessionId).toBeNull()
  })

  it('mantiene la pantalla encendida mientras corre la sesión', async () => {
    mocks.wakeScreenOn.mockClear()
    await session.start()
    expect(mocks.wakeScreenOn).toHaveBeenCalledWith(true)
    mocks.wakeScreenOn.mockClear()
    await session.stop(false)
    expect(mocks.wakeScreenOn).toHaveBeenCalledWith(false)
  })

  it('no libera el micro al terminar la sesión (evita que iOS vuelva a pedir permiso)', async () => {
    mocks.releaseRec.mockClear()
    await session.start()
    await session.stop(false)
    expect(mocks.releaseRec).not.toHaveBeenCalled()
  })

  it('ante un fallo de red muestra error y deja de correr', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      throw new Error('Immersive down')
      yield
    })
    await session.start()
    expect(session.running).toBe(false)
    expect(session.history).toHaveLength(0)
  })

  it('ante un evento error del tutor deja de correr sin añadir turnos', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 5 }
      yield { type: 'error', detail: 'Modelo local no disponible.' }
    })
    await session.start()
    expect(session.running).toBe(false)
    expect(session.history).toHaveLength(0)
    expect(session.orb).toBe('idle')
  })
})

const flush = () => new Promise((r) => setTimeout(r, 0))

function voiceBefore() {
  vi.clearAllMocks()
  mocks.immersiveStream.mockImplementation(async function* (p: { mode: string }) {
    yield* fakeStream(docs[p.mode === 'start' ? 'start' : 'continue'])
  })
  mocks.finishSession.mockResolvedValue(undefined)
  mocks.listProfiles.mockResolvedValue([])
  mocks.ensureMic.mockResolvedValue(undefined)
  mocks.beginRec.mockResolvedValue(new Blob(['audio data'.repeat(100)]))
  mocks.releaseRec.mockResolvedValue(undefined)
  mocks.getTtsBuffer.mockResolvedValue(new ArrayBuffer(8))
  mocks.playBuffer.mockResolvedValue({ id: 1, stop: vi.fn(), get current() { return true }, waited: Promise.resolve() })
  mocks.transcribeAudio.mockResolvedValue('hola')
  settings.setMode('voice')
  settings.setLang('en')
  settings.setGender('female')
  settings.setSpeed(1)
  session.stop(false)
}

describe('session (modo voz: TTS por frases)', () => {
  beforeEach(voiceBefore)

  it('habla la respuesta completa tras recibir el `done` del stream', async () => {
    await session.start()
    const spoken = mocks.getTtsBuffer.mock.calls.map((c) => c[0] as string)
    // Filtrar fillers (frases cortas como "Okay, so…", "Hmm, let me think…")
    const nonFiller = spoken.filter((t) => !t.includes('…') || t.length > 20)
    expect(nonFiller[0]).toBe('Hello!')
    expect(session.history).toHaveLength(1)
    await session.stop(true)
  })

  it('al terminar el stream habla también el tramo sin signo de cierre', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 7 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'Nice try. Let us ' }
      yield { type: 'done', reply: 'Nice try. Let us practice more!', corrections: [] }
    })
    await session.start()
    await flush()
    const spoken = mocks.getTtsBuffer.mock.calls.map((c) => c[0] as string)
    expect(spoken).toContain('Nice try.')
    expect(spoken).toContain('Let us practice more!')
    await session.stop(true)
  })

  it('prefetch: sintetiza la frase siguiente mientras suena la actual', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 11 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'É bom ter uma ideia de onde ir. ' }
      yield { type: 'done', reply: 'É bom ter uma ideia de onde ir. Você já pensou em lugares com atrações diferentes?', corrections: [] }
    })
    let releaseFirst!: () => void
    const firstGate = new Promise<void>((r) => (releaseFirst = r))
    let playCalls = 0
    mocks.playBuffer.mockImplementation(async () => {
      playCalls++
      return { id: playCalls, stop: vi.fn(), get current() { return true }, waited: playCalls === 1 ? firstGate : Promise.resolve() }
    })
    await session.start()
    await flush()
    // Al menos 2 frases del stream se sintetizaron (puede haber fillers también)
    expect(mocks.getTtsBuffer.mock.calls.length).toBeGreaterThanOrEqual(2)
    const spoken = mocks.getTtsBuffer.mock.calls.map((c) => c[0] as string)
    expect(spoken).toContain('É bom ter uma ideia de onde ir.')
    expect(spoken).toContain('Você já pensou em lugares com atrações diferentes?')
    releaseFirst()
    await flush()
    await session.stop(true)
  })

  it('si el audio falla enseña el historial y reintenta escuchar', async () => {
    mocks.getTtsBuffer.mockResolvedValue(null)
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 7 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'done', reply: 'Hi!', corrections: [] }
    })
    await session.start()
    // El drenaje reintenta la frase y hace una pasada final antes de rendirse.
    await new Promise((r) => setTimeout(r, 800))
    await flush()
    expect(session.transcriptOpen).toBe(true)
    await session.stop(true)
  })

  it('reintenta una frase que falla de forma puntual y la acaba leyendo', async () => {
    let seen = 0
    mocks.getTtsBuffer.mockImplementation(async () => {
      seen++
      // Fallar solo los primeros intentos (fillers + primer intento de frase real)
      return seen <= 2 ? null : new ArrayBuffer(8)
    })
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 21 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'Keep going!' }
      yield { type: 'done', reply: 'Keep going!', corrections: [] }
    })
    await session.start()
    await new Promise((r) => setTimeout(r, 400))
    await flush()
    const texts = mocks.getTtsBuffer.mock.calls.map((c) => c[0] as string)
    // La frase 'Keep going!' se reintentó y finalmente se leyó al menos una vez
    expect(texts.filter((t) => t === 'Keep going!').length).toBeGreaterThanOrEqual(1)
    expect(session.speaking).toBe(false)
    expect(session.transcriptOpen).toBe(false)
    await session.stop(true)
  })

  it('no descarta el resto de la respuesta si una frase a mitad falla', async () => {
    mocks.getTtsBuffer.mockImplementation(async (text: string) => (text === 'Hello there.' ? null : new ArrayBuffer(8)))
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 22 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'Hello there. ' }
      yield { type: 'done', reply: 'Hello there. This is a longer reply!', corrections: [] }
    })
    await session.start()
    await new Promise((r) => setTimeout(r, 900))
    await flush()
    const spoken = mocks.getTtsBuffer.mock.calls.map((c) => c[0] as string)
    // La frase que sí se pudo leer NUNCA se abandona por culpa de la otra.
    expect(spoken).toContain('This is a longer reply!')
    expect(session.speaking).toBe(false)
    // Hubo voz (parcial): la sesión sigue normal, sin marcar el transcript.
    expect(session.transcriptOpen).toBe(false)
    await session.stop(true)
  })

  it('tras una respuesta ya consumida por el streaming no queda colgada la escucha', async () => {
    mocks.getTtsBuffer.mockResolvedValue(new ArrayBuffer(8))
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 23 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'Hello!' }
      yield { type: 'done', reply: 'Hello!', corrections: [] }
    })
    await session.start()
    await flush()
    expect(session.speaking).toBe(false)
    expect(['idle', 'listening']).toContain(session.orb)
    await session.stop(true)
  })

  it('pasa la velocidad elegida al sintetizar', async () => {
    settings.setSpeed(1.25)
    await session.start()
    const args = mocks.getTtsBuffer.mock.calls[0]
    expect(args[1]).toBe('en')
    expect(args[2]).toBe('female')
    expect(args[4]).toBe(1.25)
    await session.stop(true)
  })

  it('el tutor termina de leer toda la respuesta sin cortes por ruido del micro', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 9 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'Hello. ' }
      yield { type: 'delta', text: 'How are you? ' }
      yield { type: 'delta', text: 'Nice to meet you.' }
      yield { type: 'done', reply: 'Hello. How are you? Nice to meet you.', corrections: [] }
    })
    mocks.getTtsBuffer.mockResolvedValue(new ArrayBuffer(8))
    await session.start()
    await flush()
    expect(mocks.getTtsBuffer).toHaveBeenCalled()
    expect(session.speaking).toBe(false)
    expect(['idle', 'listening']).toContain(session.orb)
    await session.stop(true)
  })

  it('tocar el orbe mientras el tutor habla la interrumpe', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 10 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'done', reply: 'Let me finish… long reply with more words!', corrections: [] }
    })
    let resolveTts: ((v: ArrayBuffer | null) => void) | null = null
    mocks.getTtsBuffer.mockImplementation(() => new Promise((r) => (resolveTts = r)))
    await session.start()
    await flush()
    expect(session.speaking).toBe(true)
    session.orbTap()
    expect(session.speaking).toBe(false)
    expect(session.orb).toBe('listening')
    expect(session.status).toContain('te escucho')
    resolveTts!(new ArrayBuffer(8))
    await flush()
    await session.stop(true)
  })

  it('sintetiza frases en streaming durante los deltas (TTS progresivo)', async () => {
    let resolveDone: (() => void) | null = null
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 99 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'Hello there. ' }
      yield { type: 'delta', text: 'How are you? ' }
      // El stream se queda "colgado" aquí: los deltas ya llegaron pero no hay done.
      await new Promise<void>((r) => (resolveDone = r))
      yield { type: 'done', reply: 'Hello there. How are you?', corrections: [] }
    })
    mocks.getTtsBuffer.mockResolvedValue(new ArrayBuffer(8))
    const startPromise = session.start()
    // Esperamos a que los deltas se hayan procesado pero sin done.
    await new Promise((r) => setTimeout(r, 50))
    await flush()
    // Con TTS en streaming, las frases se sintetizan durante los deltas.
    expect(mocks.getTtsBuffer).toHaveBeenCalled()
    const spokenBeforeDone = mocks.getTtsBuffer.mock.calls.map((c) => c[0] as string)
    expect(spokenBeforeDone).toContain('Hello there.')
    resolveDone!()
    await startPromise
    await flush()
    // Tras el done, se sintetiza el resto si lo hay.
    expect(mocks.getTtsBuffer).toHaveBeenCalled()
    await session.stop(true)
  })

  it('sintetiza todas las frases sin pausas (prefetch activo)', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 11 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'delta', text: 'Hello there. ' }
      yield { type: 'delta', text: 'How are you? ' }
      yield { type: 'delta', text: 'Nice to meet you.' }
      yield { type: 'done', reply: 'Hello there. How are you? Nice to meet you.', corrections: [] }
    })
    const ttsCalls: string[] = []
    mocks.getTtsBuffer.mockImplementation(async (text: string) => {
      ttsCalls.push(text)
      return new ArrayBuffer(8)
    })
    mocks.playBuffer.mockResolvedValue({
      id: 1,
      stop: vi.fn(),
      get current() { return true },
      waited: Promise.resolve(),
    })

    await session.start()
    await flush()
    await flush()

    // Múltiples frases se sintetizaron (al menos 2)
    expect(ttsCalls.length).toBeGreaterThanOrEqual(2)
    expect(session.speaking).toBe(false)
    expect(['idle', 'listening']).toContain(session.orb)

    await session.stop(true)
  })
})