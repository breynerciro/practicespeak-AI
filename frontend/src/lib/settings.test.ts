import { beforeEach, describe, expect, it } from 'vitest'
import { settings } from './settings.svelte'

describe('settings', () => {
  beforeEach(() => localStorage.clear())

  it('usa voz por defecto', () => {
    expect(settings.mode).toBe('voice')
    expect(settings.lang).toBe('en')
    expect(settings.gender).toBe('female')
  })

  it('persiste el idioma elegido', () => {
    settings.setLang('de')
    expect(settings.lang).toBe('de')
    expect(localStorage.getItem('lang')).toBe('de')
  })

  it('persiste el modo y la voz', () => {
    settings.setMode('text')
    settings.setGender('male')
    expect(settings.mode).toBe('text')
    expect(settings.gender).toBe('male')
    expect(localStorage.getItem('mode')).toBe('text')
    expect(localStorage.getItem('gender')).toBe('male')
  })
})