import { describe, expect, it } from 'vitest'
import { DEFAULT_VAD, computeRms, tooSmall, vadFor } from './vad'

describe('vad', () => {
  it('vadFor devuelve una configuración por sensibilidad sin mutar la de fábrica', () => {
    const baja = vadFor('baja')
    const normal = vadFor('normal')
    const alta = vadFor('alta')
    expect(baja.threshold).toBeCloseTo(0.045)
    expect(baja.silenceMs).toBe(2500)
    expect(alta.threshold).toBeCloseTo(0.015)
    expect(alta.silenceMs).toBe(900)
    expect(normal).toEqual(DEFAULT_VAD)
    expect(normal).not.toBe(DEFAULT_VAD)
    expect(DEFAULT_VAD.silenceMs).toBe(800)
  })

  it('por defecto usa sensibilidad normal (copia fresca)', () => {
    const cfg = vadFor()
    expect(cfg).toEqual(DEFAULT_VAD)
    expect(cfg).not.toBe(DEFAULT_VAD)
  })

  it('computeRms distingue silencio de señal fuerte', () => {
    const silence = new Uint8Array(128).fill(128)
    const loud = new Uint8Array(128)
    for (let i = 0; i < 128; i++) loud[i] = i % 2 ? 250 : 6
    expect(computeRms(silence)).toBe(0)
    expect(computeRms(loud)).toBeGreaterThan(0.5)
  })

  it('tooSmall descarta grabaciones minúsculas', () => {
    expect(tooSmall(10)).toBe(true)
    expect(tooSmall(5000)).toBe(false)
  })
})