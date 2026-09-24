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
  // 1.5 s de silencio por defecto: equilibrio entre no cortar pausas de
  // pensamiento y responder rápido. Ajustable en Ajustes (Paciente/Normal/Rápida).
  silenceMs: 1500,
  maxMs: 45000,
  minBlobBytes: 1500,
}

export type VADSensitivity = 'baja' | 'normal' | 'alta'

/** Variantes de escucha según la sensibilidad elegida en Ajustes.
 *  - `baja` (Paciente): espera 2.5 s de silencio, evita cortes con pausas largas.
 *  - `normal`: espera 1.5 s de silencio, equilibrio.
 *  - `alta` (Rápida): espera 0.9 s de silencio, respuesta más veloz.
 */
export function vadFor(sensitivity: VADSensitivity = 'normal'): VADConfig {
  switch (sensitivity) {
    case 'baja':
      return { threshold: 0.045, silenceMs: 2500, maxMs: DEFAULT_VAD.maxMs, minBlobBytes: DEFAULT_VAD.minBlobBytes }
    case 'alta':
      return { threshold: 0.015, silenceMs: 900, maxMs: DEFAULT_VAD.maxMs, minBlobBytes: DEFAULT_VAD.minBlobBytes }
    default:
      return { ...DEFAULT_VAD }
  }
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