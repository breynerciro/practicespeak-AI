import type { Language } from './types'

export const LANG_NAMES: Record<Language, string> = {
  en: 'English',
  pt: 'Portuguese (Brazíl)',
  fr: 'French',
  de: 'German',
  it: 'Italian',
  es: 'Spanish',
  ru: 'Russian',
  zh: 'Chinese (Mandarin)',
}

export const LANG_NAMES_ES: Record<Language, string> = {
  en: 'Inglés',
  pt: 'Portugués',
  fr: 'Francés',
  de: 'Alemán',
  it: 'Italiano',
  es: 'Español',
  ru: 'Ruso',
  zh: 'Chino (mandarín)',
}

export const PLACEHOLDERS: Record<Language, string> = {
  en: 'Escribe en inglés…',
  pt: 'Escribe en portugués…',
  fr: 'Écris en français…',
  de: 'Schreib auf Deutsch…',
  it: 'Scrivi in italiano…',
  es: 'Escribe en español…',
  ru: 'Пиши по-русски…',
  zh: '请用中文写…',
}

export const VOICE_PREVIEW: Record<Language, string> = {
  en: "Hello! I'm PracticeSpeak. Let's practice English!",
  pt: 'Olá! Eu sou a PracticeSpeak. Vamos praticar português?',
  fr: 'Bonjour ! Je suis PracticeSpeak. On pratique le français ?',
  de: 'Hallo! Ich bin PracticeSpeak. Lass uns Deutsch üben!',
  it: 'Ciao! Sono PracticeSpeak. Pratichiamo l\'italiano?',
  es: '¡Hola! Soy PracticeSpeak. ¡Vamos a practicar español!',
  ru: 'Привет! Я ПрактикСпик. Давай практиковать русский!',
  zh: '你好！我是PracticeSpeak。我们来练中文吧！',
}