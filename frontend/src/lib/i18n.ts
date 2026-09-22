import type { Language } from './types'

export const LANG_NAMES: Record<Language, string> = {
  en: 'English',
  pt: 'Portuguese (Brazíl)',
  fr: 'French',
  de: 'German',
  it: 'Italian',
}

export const LANG_NAMES_ES: Record<Language, string> = {
  en: 'Inglés',
  pt: 'Portugués',
  fr: 'Francés',
  de: 'Alemán',
  it: 'Italiano',
}

export const PLACEHOLDERS: Record<Language, string> = {
  en: 'Escribe en inglés…',
  pt: 'Escribe en portugués…',
  fr: 'Écris en français…',
  de: 'Schreib auf Deutsch…',
  it: 'Scrivi in italiano…',
}

export const VOICE_PREVIEW: Record<Language, string> = {
  en: "Hello! I'm Nova. Let's practice English!",
  pt: 'Olá! Eu sou a Nova. Vamos praticar português?',
  fr: 'Bonjour ! Je suis Nova. On pratique le français ?',
  de: 'Hallo! Ich bin Nova. Lass uns Deutsch üben!',
  it: 'Ciao! Sono Nova. Pratichiamo l\'italiano?',
}