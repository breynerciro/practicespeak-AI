// Tests de la puerta de acceso compartido.
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  getHealth: vi.fn(),
  sendLog: vi.fn(),
  setAccessCode: vi.fn(),
}))

import { getHealth, setAccessCode } from './api'
import { AccessStore } from './access.svelte'

vi.mocked(getHealth)

function health(needs_code: boolean) {
  return { ollama: true, model: 'qwen3:4b', whisper: 'small', ok: true, public_hostname: '', needs_code }
}

async function settled(store: AccessStore) {
  await vi.waitFor(() => expect(store.checking).toBe(false))
}

describe('AccessStore', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    history.replaceState(null, '', '/')
  })

  it('no abre la puerta si el servidor no pide código', async () => {
    vi.mocked(getHealth).mockResolvedValue(health(false))
    const store = new AccessStore()
    await settled(store)
    expect(store.gateOpen).toBe(false)
  })

  it('abre la puerta cuando el servidor pide código', async () => {
    vi.mocked(getHealth).mockResolvedValue(health(true))
    const store = new AccessStore()
    await settled(store)
    expect(store.gateOpen).toBe(true)
  })

  it('verifica y recuerda un código válido', async () => {
    vi.mocked(getHealth).mockResolvedValue(health(true))
    const store = new AccessStore()
    await settled(store)

    vi.mocked(getHealth).mockResolvedValue(health(false))
    const ok = await store.submit('  nova2026 ')
    expect(ok).toBe(true)
    expect(store.gateOpen).toBe(false)
    expect(localStorage.getItem('nova-access')).toBe('nova2026')
    expect(setAccessCode).toHaveBeenCalledWith('nova2026')
  })

  it('rechaza un código inválido con mensaje claro', async () => {
    vi.mocked(getHealth).mockResolvedValue(health(true))
    const store = new AccessStore()
    await settled(store)

    vi.mocked(getHealth).mockRejectedValue(new Error('Código de acceso incorrecto.'))
    const ok = await store.submit('malo')
    expect(ok).toBe(false)
    expect(store.gateOpen).toBe(true)
    expect(store.errorMsg).toMatch(/no es válido/)
  })

  it('valida el código que viene en la URL (?code=) y lo limpia de la barra', async () => {
    history.replaceState(null, '', '/?code=URLCODE')
    vi.mocked(getHealth).mockResolvedValueOnce(health(true)).mockResolvedValueOnce(health(false))
    const store = new AccessStore()
    await settled(store)
    expect(getHealth).toHaveBeenCalledWith('URLCODE')
    expect(setAccessCode).toHaveBeenCalledWith('URLCODE')
    expect(store.gateOpen).toBe(false)
    expect(location.search).not.toContain('URLCODE')
  })

  it('submit sin código muestra aviso', async () => {
    vi.mocked(getHealth).mockResolvedValue(health(true))
    const store = new AccessStore()
    await settled(store)
    const ok = await store.submit('   ')
    expect(ok).toBe(false)
    expect(store.errorMsg).toMatch(/código/i)
  })
})
