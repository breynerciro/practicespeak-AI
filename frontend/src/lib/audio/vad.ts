// Configuración y helpers puros de detección de voz (testeables sin DOM).

export interface VADConfig {
  /** RMS por debajo = silencio. */
  threshold: number
  /** Silencio continuo antes de considerar que terminaste de hablar (ms). */
  silenceMs: number
  /** Tiempo máximo de una grabación (ms). */
  maxMs: number
  /** Por debajo de este tamaño (bytes) la grabación se descarta. */
  minBlobBytes: number
}

export const DEFAULT_VAD: VADConfig = {
  threshold: 0.03,
  silenceMs: 2200,
  maxMs: 20000,
  minBlobBytes: 1500,
}

/** RMS de un buffer de dominio temporal (analyser.getByteTimeDomainData). */
export function computeRms(buf: Uint8Array): number {
  let acc = 0
  for (let i = 0; i < buf.length; i++) {
    const v = (buf[i] - 128) / 128
    acc += v * v
  }
  return Math.sqrt(acc / buf.length)
}

/** Decide si una grabación debe descartarse por vacía. */
export function tooSmall(size: number, min = DEFAULT_VAD.minBlobBytes): boolean {
  return size < min
}