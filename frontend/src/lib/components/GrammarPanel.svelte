<script lang="ts">
  import { correctGrammar, sendLog } from '../api'
  import { LANG_NAMES_ES } from '../i18n'
  import { settings } from '../settings.svelte'
  import { toast } from '../toast.svelte'
  import type { GrammarResult } from '../types'
  import Icon from './Icon.svelte'

  let { onclose }: { onclose: () => void } = $props()

  let text = $state('')
  let busy = $state(false)
  let result: GrammarResult | null = $state(null)
  let panelEl = $state<HTMLElement | null>(null)

  $effect(() => {
    panelEl?.querySelector<HTMLTextAreaElement>('textarea')?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onclose()
        return
      }
      if (e.key !== 'Tab' || !panelEl) return
      const focusables = Array.from(
        panelEl.querySelectorAll<HTMLElement>('button, textarea, [href], [tabindex]:not([tabindex="-1"])'),
      ).filter((el) => !el.hasAttribute('disabled'))
      if (!focusables.length) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement
      if (e.shiftKey) {
        if (active === first || active === panelEl) {
          e.preventDefault()
          last.focus()
        }
      } else if (active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  async function check() {
    const v = text.trim()
    if (!v || busy) return
    busy = true
    result = null
    sendLog('GRAMMAR_LEN ' + v.length)
    try {
      result = await correctGrammar(v, settings.lang)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      sendLog('GRAMMAR_ERR ' + msg)
      toast(msg)
    } finally {
      busy = false
    }
  }
</script>

<button type="button" class="mt-backdrop" aria-label="Cerrar el corrector" tabindex="-1" onclick={onclose}></button>
<div class="grammar-board" bind:this={panelEl} role="dialog" aria-modal="true" aria-label="Corregir un texto">
  <header class="panel-head">
    <h2>
      <Icon name="pen-line" size="sm" />
      Corregir un texto
    </h2>
    <button class="panel-close" aria-label="Cerrar el corrector" onclick={onclose}>
      <Icon name="x" size="sm" />
    </button>
  </header>

  <p class="grammar-lang">
    Practica {LANG_NAMES_ES[settings.lang].toLowerCase()} · escribe lo que dirías y PracticeSpeak lo corrige y explica.
  </p>

  <div class="grammar-form">
    <textarea
      bind:value={text}
      rows="4"
      maxlength="2000"
      placeholder="Escribe aquí lo que te gustaría decir…"
      aria-label="Texto a corregir"
      onkeydown={(e) => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
          e.preventDefault()
          check()
        }
      }}
    ></textarea>
    <button class="btn btn-primary" onclick={check} disabled={busy || !text.trim()}>
      {#if busy}<span class="mini-spin" aria-hidden="true"></span>{/if}
      {busy ? 'Corrigiendo…' : 'Corregir'}
    </button>
  </div>

  {#if result}
    <div class="grammar-result">
      {#if result.corrected}
        <div class="g-corrected">
          <span class="g-label">Texto corregido</span>
          <p class="g-text">{result.corrected}</p>
        </div>
      {/if}
      {#if result.summary}
        <p class="g-summary">{result.summary}</p>
      {/if}
      {#if result.errors.length > 0}
        <ul class="g-errors">
          {#each result.errors as e, i (i)}
            <li class="correction">
              <span class="corr-wrong">{e.error}</span>
              <span class="arrow">→</span>
              <span class="corr-right">{e.correction}</span>
              {#if e.explanation}
                <span class="corr-note">{e.explanation}</span>
              {/if}
            </li>
          {/each}
        </ul>
      {:else}
        <p class="g-allgood">
          <Icon name="sparkles" size="sm" />
          Sin errores. Tu frase está perfecta.
        </p>
      {/if}
    </div>
  {/if}
</div>