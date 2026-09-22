// Stubs de jsdom para tests: matchMedia, requestAnimationFrame, canvas 2D y fetch.
// jsdom no implementa nada de esto y los módulos de la app los usan en import/efectos.

export function stubMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      // matches:true evita que el orbe use bucles rAF infinitos en tests
      matches: true,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}

export function stubRaf() {
  Object.defineProperty(window, 'requestAnimationFrame', {
    writable: true,
    value: (cb: () => void) => {
      cb()
      return 1
    },
  })
  Object.defineProperty(window, 'cancelAnimationFrame', { writable: true, value: () => {} })
}

export function stubCanvas() {
  const gradient = { addColorStop: () => {} }
  const ctx = new Proxy(
    {},
    {
      get: (_, prop) => {
        if (prop === 'createRadialGradient') return () => gradient
        if (prop === 'fillStyle') return undefined
        return () => {}
      },
      set: () => true,
    },
  ) as CanvasRenderingContext2D
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    writable: true,
    value: () => ctx,
  })
}

export function stubFetch() {
  window.fetch = (() => Promise.reject(new Error('no network in tests'))) as typeof fetch
}

stubMatchMedia()
stubRaf()
stubCanvas()
stubFetch()