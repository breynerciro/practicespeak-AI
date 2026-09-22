import { beforeEach, describe, expect, it, vi } from 'vitest'

const LS_KEY = 'nova-profile'

describe('profile store (persona anónima)', () => {
  beforeEach(() => localStorage.clear())

  it('abre la puerta sin perfil guardado', async () => {
    vi.resetModules()
    const { profileStore } = await import('./profile.svelte')
    expect(profileStore.gateOpen).toBe(true)
    expect(profileStore.current).toBeNull()
  })

  it('recuerda el apodo guardado y salta la puerta', async () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ id: 7, name: 'Lía' }))
    vi.resetModules()
    const { profileStore } = await import('./profile.svelte')
    expect(profileStore.gateOpen).toBe(false)
    expect(profileStore.current?.name).toBe('Lía')
    expect(profileStore.current?.id).toBe(7)
  })

  it('crea un perfil, lo selecciona y persiste', async () => {
    vi.resetModules()
    const { profileStore } = await import('./profile.svelte')
    const realFetch = window.fetch
    window.fetch = (async () => ({ ok: true, json: async () => ({ id: 11, name: 'Ana' }) })) as unknown as typeof fetch
    try {
      await profileStore.create('  Ana  ')
    } finally {
      window.fetch = realFetch
    }
    expect(profileStore.current?.name).toBe('Ana')
    expect(profileStore.gateOpen).toBe(false)
    expect(localStorage.getItem(LS_KEY)).toBe(JSON.stringify({ id: 11, name: 'Ana' }))
  })

  it('rechaza nombres vacíos', async () => {
    vi.resetModules()
    const { profileStore } = await import('./profile.svelte')
    await expect(profileStore.create('   ')).rejects.toThrow('Escribe un nombre primero.')
  })
})