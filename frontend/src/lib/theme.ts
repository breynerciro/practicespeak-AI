export type ThemeMode = 'auto' | 'light' | 'dark'

const THEME_KEY = 'theme'
const systemDark = window.matchMedia('(prefers-color-scheme: dark)')

export function readTheme(): ThemeMode {
  const v = localStorage.getItem(THEME_KEY)
  return v === 'light' || v === 'dark' || v === 'auto' ? v : 'auto'
}

export function resolvedTheme(mode: ThemeMode): 'light' | 'dark' {
  return mode === 'dark' || (mode === 'auto' && systemDark.matches) ? 'dark' : 'light'
}

export function applyTheme() {
  const mode = readTheme()
  const resolved = resolvedTheme(mode)
  document.documentElement.dataset.theme = resolved
  document.documentElement.style.colorScheme = resolved
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', resolved === 'dark' ? '#171320' : '#f6f2ec')
  return mode
}

export function setTheme(mode: ThemeMode) {
  localStorage.setItem(THEME_KEY, mode)
  applyTheme()
}

/** Devuelve un cancelador para no suscribirse dos veces (componentes en modo runes). */
export function watchSystemTheme(handler: () => void): () => void {
  systemDark.addEventListener('change', handler)
  return () => systemDark.removeEventListener('change', handler)
}