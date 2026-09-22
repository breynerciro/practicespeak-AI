import { describe, expect, it } from 'vitest'
import { NOVA_TOPICS, topicIcon, topicLabel } from './topics'

describe('topics', () => {
  it('devuelve la etiqueta en español del tema', () => {
    expect(topicLabel('travel')).toBe('Viajes')
    expect(topicLabel('food and cooking')).toBe('Comida')
  })

  it('deja pasar temas desconocidos', () => {
    expect(topicLabel('Astronomía')).toBe('Astronomía')
  })

  it('tiene un icono para cada tema y la opción sorpresa', () => {
    for (const t of NOVA_TOPICS) {
      expect(topicIcon(t.id || 'any')).toBeTruthy()
    }
    expect(NOVA_TOPICS[NOVA_TOPICS.length - 1].id).toBe('')
  })
})