// Fillers auditivos: frases cortas que el tutor dice mientras "piensa".
// Hacen la conversación más natural, como un humano real.

import { getTtsBuffer } from '../api'
import { playBuffer, stopPlayback } from './playback'
import { settings } from '../settings.svelte'
import type { Language } from '../types'

const FILLERS: Record<string, string[]> = {
  en: ['Hmm, let me think…', 'Okay, so…', 'Well…', 'Let me see…'],
  pt: ['Hmm, deixa eu pensar…', 'Então…', 'Bom…', 'Deixa ver…'],
  fr: ['Hmm, laisse-moi réfléchir…', 'Alors…', 'Bon…', 'Voyons…'],
  de: ['Hmm, lass mich nachdenken…', 'Also…', 'Nun…', 'Mal sehen…'],
  it: ['Hmm, fammi pensare…', 'Allora…', 'Beh…', 'Vediamo…'],
  es: ['Mmm, déjame pensar…', 'A ver…', 'Bueno…', 'Veamos…'],
  ru: ['Хм, дай подумать…', 'Итак…', 'Ну…', 'Посмотрим…'],
  zh: ['嗯，让我想想…', '那么…', '好的…', '看看…'],
}

function randomChoice<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

/**
 * Reproduce un filler auditivo mientras el tutor "piensa".
 * Retorna una promesa que se resuelve cuando termina o al cancelar.
 * Máximo 1.5s de duración para no retrasar la respuesta real.
 */
export async function playFiller(language: Language): Promise<void> {
  const filler = randomChoice(FILLERS[language] || FILLERS.en)
  const voice = settings.ttsVoice[language] || ''
  const buffer = await getTtsBuffer(
    filler,
    language,
    settings.gender,
    voice,
    settings.speed,
  )
  if (!buffer) return

  const handle = await playBuffer(buffer)
  if (!handle) return

  // Timeout de 1.5s: si el LLM tarda más, cortar el filler
  await Promise.race([
    handle.waited,
    new Promise<void>((r) => setTimeout(() => {
      if (handle.current) stopPlayback()
      r()
    }, 1500)),
  ])
}
