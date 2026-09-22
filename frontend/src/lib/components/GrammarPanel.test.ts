import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import userEvent from '@testing-library/user-event'
import GrammarPanel from './GrammarPanel.svelte'

describe('GrammarPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('corrige el texto y muestra el resultado en un diálogo accesible', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/grammar') {
        return {
          ok: true,
          json: async () => ({
            corrected: 'I have a cat.',
            errors: [{ error: 'I has', correction: 'I have', explanation: 'tercera persona' }],
            summary: 'Bien. Revisa la primera persona.',
          }),
        } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    const onclose = vi.fn()
    render(GrammarPanel, { props: { onclose } })
    expect(screen.getByRole('dialog', { name: /corregir un texto/i })).toBeTruthy()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Texto a corregir'), 'I has a cat')
    await user.click(screen.getByRole('button', { name: 'Corregir' }))

    expect(await screen.findByText('I have a cat.')).toBeTruthy()
    expect(screen.getByText('I has')).toBeTruthy()
    expect(screen.getByText('I have')).toBeTruthy()
    expect(screen.getByText('Bien. Revisa la primera persona.')).toBeTruthy()
  })

  it('llama onclose con la tecla Escape', async () => {
    const onclose = vi.fn()
    render(GrammarPanel, { props: { onclose } })
    await userEvent.keyboard('{Escape}')
    expect(onclose).toHaveBeenCalledTimes(1)
  })
})