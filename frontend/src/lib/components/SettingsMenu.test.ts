import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/svelte'
import userEvent from '@testing-library/user-event'
import SettingsMenu from './SettingsMenu.svelte'
import { settings } from '../settings.svelte'

function voicesFor(lang: string) {
  if (lang === 'es') {
    return [
      { id: 'es_ES-sharvard-medium', name: 'Sharvard · es (medium, local)', source: 'local', installed: false },
      { id: 'es_ES-davefx-medium', name: 'Davefx · es (medium, local)', source: 'local', installed: false },
      { id: 'es-ES-ElviraNeural', name: 'Elvira · es-ES (nube)', source: 'edge', installed: true },
    ]
  }
  return [
    { id: 'en_US-amy-medium', name: 'Amy · en (medium, local)', source: 'local', installed: false },
    { id: 'en-US-AriaNeural', name: 'Aria · en-US (nube)', source: 'edge', installed: true },
  ]
}

function stubVoicesApi() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/tts/voices')) {
      const lang = new URL(url, 'http://x').searchParams.get('lang') || 'en'
      return { ok: true, json: async () => ({ lang, voices: voicesFor(lang) }) } as Response
    }
    return { ok: true, json: async () => ({}) } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('SettingsMenu · selector de voz', () => {
  beforeEach(() => {
    localStorage.clear()
    settings.setLang('en')
    settings.setMode('voice')
    settings.setGender('female')
    settings.setTtsVoice('en', '')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('carga las voces del idioma activo en el selector', async () => {
    stubVoicesApi()
    render(SettingsMenu, { props: { onclose: () => {} } })
    const select = screen.getByLabelText('Voz concreta de Inglés') as HTMLSelectElement
    await waitFor(() => {
      expect(select.options.length).toBe(3) // Auto + 2 voces
    })
    expect(select.options[1].textContent).toContain('Amy')
    expect(select.options[2].textContent).toContain('Aria')
  })

  it('guardar una voz la persiste y la aplica al sintetizar', async () => {
    stubVoicesApi()
    render(SettingsMenu, { props: { onclose: () => {} } })
    const select = screen.getByLabelText('Voz concreta de Inglés') as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBe(3))
    const user = userEvent.setup()
    await user.selectOptions(select, 'en_US-amy-medium')
    expect(settings.ttsVoice.en).toBe('en_US-amy-medium')
    expect(JSON.parse(localStorage.getItem('ttsVoice') || '{}')).toEqual({ en: 'en_US-amy-medium' })
  })

  it('recarga las voces al cambiar de idioma', async () => {
    const fetchMock = stubVoicesApi()
    render(SettingsMenu, { props: { onclose: () => {} } })
    const select = screen.getByLabelText('Voz concreta de Inglés') as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBe(3))
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Spanish' }))
    const esSelect = await screen.findByLabelText('Voz concreta de Español') as HTMLSelectElement
    await waitFor(() => expect(esSelect.options.length).toBe(4)) // Auto + 3 voces de es
    const calls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(calls.some((c) => c.includes('/api/tts/voices') && c.includes('lang=es'))).toBe(true)
    await user.selectOptions(esSelect, 'es_ES-davefx-medium')
    expect(settings.ttsVoice.es).toBe('es_ES-davefx-medium')
  })

  it('muestra solo Auto si la lista de voces falla', async () => {
    const fetchMock = vi.fn(async () => ({ ok: false, json: async () => ({}) } as Response))
    vi.stubGlobal('fetch', fetchMock)
    render(SettingsMenu, { props: { onclose: () => {} } })
    const select = screen.getByLabelText('Voz concreta de Inglés') as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBe(1))
    expect(select.options[0].value).toBe('')
  })
})