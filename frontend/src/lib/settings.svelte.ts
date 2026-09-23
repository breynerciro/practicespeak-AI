// Ajustes de práctica (idioma, modo, voz) persistidos en localStorage.
import type { VADSensitivity } from './audio/vad'
import type { Language, Mode } from './types'

type Gender = 'female' | 'male'

const LANGS: Language[] = ['en', 'pt', 'fr', 'de', 'it', 'es', 'ru', 'zh']

export const SPEEDS = [0.75, 1, 1.25, 1.5]

function langFromStorage(): Language {
  const v = localStorage.getItem('lang')
  return (LANGS as string[]).includes(v ?? '') ? (v as Language) : 'en'
}
function modeFromStorage(): Mode {
  const v = localStorage.getItem('mode')
  return v === 'text' || v === 'voice' ? v : 'voice'
}
function genderFromStorage(): Gender {
  const v = localStorage.getItem('gender')
  return v === 'male' || v === 'female' ? v : 'female'
}
function speedFromStorage(): number {
  const v = Number(localStorage.getItem('ttsSpeed'))
  return SPEEDS.includes(v) ? v : 1
}
function sensitivityFromStorage(): VADSensitivity {
  const v = localStorage.getItem('micSensitivity')
  return v === 'baja' || v === 'alta' ? v : 'normal'
}
function voicesFromStorage(): Partial<Record<Language, string>> {
  try {
    const raw = localStorage.getItem('ttsVoice')
    const parsed = raw ? JSON.parse(raw) : {}
    if (parsed && typeof parsed === 'object') return parsed as Partial<Record<Language, string>>
  } catch {
    // almacen dañado: empezar de vacío
  }
  return {}
}

class SettingsStore {
  lang: Language = $state(langFromStorage())
  mode: Mode = $state(modeFromStorage())
  gender: Gender = $state(genderFromStorage())
  /** Voz concreta elegida por idioma (id de piper o de edge); vacío = Auto. */
  ttsVoice: Partial<Record<Language, string>> = $state(voicesFromStorage())
  /** Velocidad de habla de Nova (0.75×–1.5×). */
  speed: number = $state(speedFromStorage())
  /** Sensibilidad del micrófono (umbral del VAD). */
  micSensitivity: VADSensitivity = $state(sensitivityFromStorage())

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

  setSpeed = (speed: number) => {
    this.speed = speed
    localStorage.setItem('ttsSpeed', String(speed))
  }

  setMicSensitivity = (sensitivity: VADSensitivity) => {
    this.micSensitivity = sensitivity
    localStorage.setItem('micSensitivity', sensitivity)
  }

  /** Guarda la voz elegida para un idioma ('' = Auto según género). */
  setTtsVoice = (lang: Language, voice: string) => {
    const next = { ...this.ttsVoice }
    if (voice) next[lang] = voice
    else delete next[lang]
    this.ttsVoice = next
    localStorage.setItem('ttsVoice', JSON.stringify(next))
  }
}

export const settings = new SettingsStore()