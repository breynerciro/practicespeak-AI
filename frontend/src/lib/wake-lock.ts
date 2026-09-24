let sentinel: WakeLockSentinel | null = null
let desired = false
let isSupported = typeof navigator !== 'undefined' && 'wakeLock' in navigator

function visible(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'visible'
}

async function acquire() {
  if (!isSupported || !desired || sentinel) return
  try {
    sentinel = await navigator.wakeLock.request('screen')
    sentinel.addEventListener('release', () => {
      sentinel = null
      if (desired && visible()) void acquire()
    })
  } catch {
    sentinel = null
  }
}

function releaseNow() {
  const s = sentinel
  sentinel = null
  if (s) s.release().catch(() => {})
}

export function wakeScreenOn(on: boolean) {
  desired = on
  if (!on) {
    releaseNow()
    return
  }
  void acquire()
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (desired && visible()) void acquire()
  })
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', () => {
      if (desired && visible()) void acquire()
    })
  }
}
