// División de frases completas para reproducir al tutor mientras escribe
// (TTS por oraciones en modo voz).

const SENTENCE = /[.!?]+(?=\s|$)/g

/**
 * Extrae las frases completas de `text` a partir del índice `from`.
 * Devuelve cuántos caracteres quedaron consumidos (hasta el final de la
 * última frase cerrada) y la lista de frases. El tramo final sin signo de
 * cierre no se cuenta: se habla cuando llegue el evento `done`.
 */
export function extractCompleted(text: string, from = 0): { consumed: number; sentences: string[] } {
  const sentences: string[] = []
  let cursor = from
  for (const m of text.slice(from).matchAll(SENTENCE)) {
    const end = from + m.index + m[0].length
    const sentence = text.slice(cursor, end).trim()
    if (sentence) sentences.push(sentence)
    cursor = end
  }
  return { consumed: cursor, sentences }
}