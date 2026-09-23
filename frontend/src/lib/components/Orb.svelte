<script lang="ts">
  import { untrack } from 'svelte'
  import { session, type OrbState } from '../session.svelte'
  import { settings } from '../settings.svelte'
  import Icon from './Icon.svelte'

  const W = 336
  const CX = W / 2
  const CY = W / 2

  const CORE_ICON: Record<OrbState, string> = {
    idle: 'mic',
    listening: 'mic',
    thinking: 'loader',
    speaking: 'audio-lines',
  }

  const LABELS: Record<OrbState, string> = {
    idle: 'Pulsa para empezar a hablar',
    listening: 'Grabando. Pulsa para terminar de hablar',
    speaking: 'PracticeSpeak está hablando',
    thinking: 'Procesando tu respuesta',
  }

  let canvasEl: HTMLCanvasElement | null = $state(null)
  let raf = 0

  const cls: OrbState = $derived(session.orb)
  const label: string = $derived(LABELS[session.orb])

  let cachedTheme = ''
  let cachedPrimary = '#b34726'

  function primaryHex(): string {
    const theme = document.documentElement.dataset.theme ?? ''
    if (theme !== cachedTheme) {
      cachedTheme = theme
      const cs = getComputedStyle(document.documentElement)
      cachedPrimary = cs.getPropertyValue('--primary').trim() || '#b34726'
    }
    return cachedPrimary
  }

  function rgba(hex: string, a: number): string {
    const m = hex.replace('#', '')
    const h = m.length === 3 ? m.split('').map((c) => c + c).join('') : m
    const r = parseInt(h.slice(0, 2), 16)
    const g = parseInt(h.slice(2, 4), 16)
    const b = parseInt(h.slice(4, 6), 16)
    return `rgba(${r}, ${g}, ${b}, ${a})`
  }

  function amplitude(orb: OrbState, energy: number, t: number): number {
    switch (orb) {
      case 'listening':
        return 0.62 + Math.min(1, energy * 1.8) * 0.38
      case 'speaking':
        return 0.8 + 0.15 * Math.sin(t * 2.6)
      case 'thinking':
        return 0.72 + 0.1 * Math.sin(t * 0.9)
      default:
        return 0.52 + 0.06 * Math.sin(t * 1.4)
    }
  }

  function frame(ctx: CanvasRenderingContext2D, orb: OrbState, energy: number, t: number) {
    ctx.clearRect(0, 0, W, W)
    const primary = primaryHex()
    const amp = amplitude(orb, energy, t)
    const mainR = 132 * (0.6 + amp * 0.6)
    const haloR = 168

    // halo exterior suave
    let g = ctx.createRadialGradient(CX, CY, mainR * 0.4, CX, CY, haloR)
    g.addColorStop(0, rgba(primary, 0))
    g.addColorStop(0.55, rgba(primary, 0.28 * amp))
    g.addColorStop(1, rgba(primary, 0))
    ctx.fillStyle = g
    ctx.fillRect(0, 0, W, W)

    // disco principal
    g = ctx.createRadialGradient(CX, CY, 6, CX, CY, mainR)
    g.addColorStop(0, rgba(primary, 0.85))
    g.addColorStop(0.55, rgba(primary, 0.55))
    g.addColorStop(1, rgba(primary, 0))
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(CX, CY, mainR, 0, Math.PI * 2)
    ctx.fill()

    // núcleo luminoso
    const coreR = 46 + (orb === 'listening' ? energy * 26 : 0)
    g = ctx.createRadialGradient(CX, CY, 2, CX, CY, coreR)
    g.addColorStop(0, 'rgba(255,255,255,0.95)')
    g.addColorStop(0.4, rgba(primary, 0.55))
    g.addColorStop(1, rgba(primary, 0))
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(CX, CY, coreR, 0, Math.PI * 2)
    ctx.fill()

    // motas orbitantes
    const orbitR = mainR * 0.62
    const speeds = [1.15, -0.8]
    for (let i = 0; i < speeds.length; i++) {
      const a = t * speeds[i] + i * Math.PI
      const bx = CX + Math.cos(a) * orbitR
      const by = CY + Math.sin(a) * orbitR
      const br = 16 + energy * 22
      g = ctx.createRadialGradient(bx, by, 1, bx, by, br)
      g.addColorStop(0, rgba('#ffffff', 0.5))
      g.addColorStop(1, rgba(primary, 0))
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.arc(bx, by, br, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  $effect(() => {
    const canvas = canvasEl
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const draw = () => {
      if (!reduced) raf = requestAnimationFrame(draw)
      const orb = untrack(() => session.orb) as OrbState
      const energy = untrack(() => session.energy)
      frame(ctx, orb, energy, reduced ? 0 : performance.now() / 1000)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  })
</script>

<div
  id="novaOrb"
  class="orb {cls}"
  role="button"
  tabindex={settings.mode === 'text' ? -1 : 0}
  aria-disabled={settings.mode === 'text'}
  aria-label={label}
  onclick={() => session.orbTap()}
  onkeydown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      session.orbTap()
    }
  }}
>
  <canvas bind:this={canvasEl} width={W} height={W} aria-hidden="true"></canvas>
  <span class="orb-core"><Icon name={CORE_ICON[cls]} /></span>
</div>