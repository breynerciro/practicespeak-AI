import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

import { applyTheme } from './lib/theme'

applyTheme()

const target = document.getElementById('app')
if (target) mount(App, { target })

// PWA: el service worker da shell offline e instalabilidad (solo en producción).
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}