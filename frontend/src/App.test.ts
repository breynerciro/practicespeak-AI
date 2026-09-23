import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import App from './App.svelte'

vi.mock('./lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/api')>()),
  getHealth: vi.fn().mockResolvedValue({
    ollama: true,
    model: 'qwen3:4b',
    whisper: 'small',
    ok: true,
    public_hostname: '',
    needs_code: false,
  }),
}))

describe('App', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('muestra la puerta de persona al arrancar sin perfil', () => {
    const { container } = render(App)
    expect(container.querySelector('.topbar')).toBeTruthy()
    expect(container.querySelector('.profile-gate')).toBeTruthy()
    expect(screen.getByPlaceholderText('Tu nombre o apodo…')).toBeTruthy()
  })

it('escribe el nombre y crea la persona', async () => {
    const realFetch = window.fetch
    // Respuesta distinta según ruta y método: la lista (GET) es un array,
    // la creación (POST) un objeto.
    window.fetch = (async (input: any, init?: RequestInit) => ({
      ok: true,
      json: async () =>
        String(input).includes('/api/profiles') && (init?.method || 'GET').toUpperCase() === 'GET'
          ? [{ id: 1, name: 'Ana', created_at: 0, sessions: 0 }]
          : { id: 3, name: 'Ana' },
    })) as unknown as typeof fetch
    render(App)
    try {
      const input = screen.getByPlaceholderText('Tu nombre o apodo…') as HTMLInputElement
      await import('@testing-library/user-event').then(async ({ default: userEvent }) => {
        const user = userEvent.setup()
        await user.type(input, 'Ana')
        await user.click(screen.getByRole('button', { name: /entrar/i }))
      })
      expect(screen.queryByPlaceholderText('Tu nombre o apodo…')).toBeNull()
    } finally {
      window.fetch = realFetch
    }
  })
})