import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('wake-lock', () => {
  let releaseListener: (() => void) | null = null
  const release = vi.fn().mockResolvedValue(undefined)
  const request = vi.fn(async () => {
    releaseListener = null
    return {
      released: false,
      type: 'screen',
      addEventListener: (_evt: string, fn: () => void) => {
        releaseListener = fn
      },
      removeEventListener: () => {},
      release,
    } as unknown as WakeLockSentinel
  })

  beforeEach(() => {
    vi.resetModules()
    releaseListener = null
    release.mockClear()
    request.mockClear()
    vi.stubGlobal('navigator', { wakeLock: { request } })
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('adquiere el lock al activar y lo libera al desactivar', async () => {
    const { wakeScreenOn } = await import('./wake-lock')
    wakeScreenOn(true)
    await vi.waitFor(() => expect(request).toHaveBeenCalledWith('screen'))
    wakeScreenOn(false)
    expect(release).toHaveBeenCalled()
  })

  it('no-op si el navegador no soporta wake lock', async () => {
    vi.stubGlobal('navigator', {})
    const { wakeScreenOn } = await import('./wake-lock')
    wakeScreenOn(true)
    await new Promise((r) => setTimeout(r, 0))
    expect(request).not.toHaveBeenCalled()
  })

  it('re-adquiere al volver a ser visible si sigue activo', async () => {
    const { wakeScreenOn } = await import('./wake-lock')
    wakeScreenOn(true)
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1))

    // El SO libera el lock al ocultar la pestaña
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    releaseListener?.()
    await new Promise((r) => setTimeout(r, 0))
    expect(request).toHaveBeenCalledTimes(1) // no re-adquiere mientras está oculto

    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2))

    wakeScreenOn(false)
  })

  it('no re-adquiere si ya no está activo', async () => {
    const { wakeScreenOn } = await import('./wake-lock')
    wakeScreenOn(true)
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1))
    wakeScreenOn(false)

    // Simular que el SO liberó el lock (aunque ya lo liberamos nosotros)
    releaseListener?.()
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await new Promise((r) => setTimeout(r, 0))
    expect(request).toHaveBeenCalledTimes(1) // no re-adquiere
  })
})
