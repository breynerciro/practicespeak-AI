import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import App from './App.svelte'

describe('App', () => {
  it('muestra la puerta de persona al arrancar sin perfil', () => {
    localStorage.clear()
    const { container } = render(App)
    expect(container.querySelector('.topbar')).toBeTruthy()
    expect(container.querySelector('.profile-gate')).toBeTruthy()
    expect(screen.getByPlaceholderText('Tu nombre o apodo…')).toBeTruthy()
  })

  it('escribe el nombre y crea la persona', async () => {
    localStorage.clear()
    const realFetch = window.fetch
    window.fetch = (async () => ({ ok: true, json: async () => ({ id: 3, name: 'Ana' }) })) as unknown as typeof fetch
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