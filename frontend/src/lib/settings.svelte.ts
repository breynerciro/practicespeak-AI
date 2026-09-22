// Ajustes de práctica (idioma, modo, voz) persistidos en localStorage.
import type { Language, Mode } from './types'

type Gender = 'female' | 'male'

function langFromStorage(): Language {
  const v = localStorage.getItem('lang')
  return v === 'pt' || v === 'fr' || v === 'de' || v === 'it' || v === 'en' ? v : 'en'
}
function modeFromStorage(): Mode {
  const v = localStorage.getItem('mode')
  return v === 'text' || v === 'voice' ? v : 'voice'
}
function genderFromStorage(): Gender {
  const v = localStorage.getItem('gender')
  return v === 'male' || v === 'female' ? v : 'female'
}

class SettingsStore {
  lang: Language = $state(langFromStorage())
  mode: Mode = $state(modeFromStorage())
  gender: Gender = $state(genderFromStorage())

  setLang = (lang: Language) => {
    this.lang = lang
    localStorage.setItem('lang', lang)
  }

  setMode = (mode: Mode) => {
    this.mode = mode
    localStorage.setItem('mode', mode)
  }

  setGender = (gender: Gender) => {
    this.gender = gender
    localStorage.setItem('gender', gender)
  }
}

export const settings = new SettingsStore()