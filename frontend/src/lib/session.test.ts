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
  },
}))

vi.mock('./audio/vad', () => ({
  DEFAULT_VAD: { threshold: 0.03, silenceMs: 2200, maxMs: 20000, minBlobBytes: 1500 },
  tooSmall: (size: number) => size < 100,
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
    mocks.playBuffer.mockResolvedValue({ id: 1, stop: vi.fn(), get current() { return false } })
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

  it('ante un fallo de red muestra error y deja de correr', async () => {
    mocks.immersiveStream.mockImplementation(async function* () {
      throw new Error('Immersive down')
      yield
    })
    await session.start()
    expect(session.running).toBe(false)
    expect(session.history).toHaveLength(0)
  })

  it('ante un evento error de Nova deja de correr sin añadir turnos', async () => {
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
  mocks.playBuffer.mockResolvedValue({ id: 1, stop: vi.fn(), get current() { return false } })
  mocks.transcribeAudio.mockResolvedValue('hola')
  settings.setMode('voice')
  settings.setLang('en')
  settings.setGender('female')
  session.stop(false)
}

describe('session (modo voz: TTS por frases)', () => {
  beforeEach(voiceBefore)

  it('habla la primera frase en cuanto se completa en el stream', async () => {
    await session.start()
    const spoken = mocks.getTtsBuffer.mock.calls.map((c) => c[0] as string)
    expect(spoken[0]).toBe('Hello!')
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

  it('si el audio falla enseña el historial y reintenta escuchar', async () => {
    mocks.getTtsBuffer.mockResolvedValue(null)
    mocks.immersiveStream.mockImplementation(async function* () {
      yield { type: 'session_id', session_id: 7 }
      yield { type: 'topic', topic: 'travel' }
      yield { type: 'done', reply: 'Hi!', corrections: [] }
    })
    await session.start()
    await flush()
    expect(session.transcriptOpen).toBe(true)
    await session.stop(true)
  })
})