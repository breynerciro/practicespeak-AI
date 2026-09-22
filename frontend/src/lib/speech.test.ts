import { describe, expect, it } from 'vitest'
import { extractCompleted } from './speech'

describe('extractCompleted', () => {
  it('extrae las frases completas y deja la cola para otro turno', () => {
    expect(extractCompleted('Hello! How are you? world', 0)).toEqual({
      consumed: 19,
      sentences: ['Hello!', 'How are you?'],
    })
  })

  it('respeta el índice desde donde empezar (fracciones del stream)', () => {
    expect(extractCompleted('Nice try. Let us ', 0)).toEqual({ consumed: 9, sentences: ['Nice try.'] })
  })

  it('no devuelve frases sin signo de cierre', () => {
    expect(extractCompleted('Hello there', 0)).toEqual({ consumed: 0, sentences: [] })
  })

  it('agrupa varios signos al final de la frase', () => {
    expect(extractCompleted('Wow!! Ready?', 0)).toEqual({ consumed: 12, sentences: ['Wow!!', 'Ready?'] })
  })
})