<script lang="ts">
  // Puerta de acceso: pide el código compartido antes de usar PracticeSpeak AI
  // cuando el servidor está protegido con NOVA_ACCESS_CODE. Reutiliza el estilo de la
  // puerta de persona (.profile-gate / .gate-card / .gate-form).
  import { access } from '../access.svelte'
  import Icon from './Icon.svelte'

  let code = $state('')
  let busy = $state(false)
  let codeInput = $state<HTMLInputElement | null>(null)

  $effect(() => {
    codeInput?.focus()
  })

  async function submit() {
    if (busy) return
    busy = true
    const ok = await access.submit(code)
    busy = false
    if (ok) code = ''
  }
</script>

{#if access.gateOpen}
  <div class="profile-gate" role="dialog" aria-modal="true" aria-label="Introduce el código de acceso">
    <div class="gate-card">
      <div class="gate-logo"><Icon name="lock" /></div>
      <h1>PracticeSpeak AI</h1>
      <p class="gate-hint">Este servidor es privado. Escribe el código que te compartió tu anfitrión para entrar.</p>

      <form
        class="gate-form"
        onsubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <input
          bind:this={codeInput}
          bind:value={code}
          type="text"
          inputmode="text"
          autocapitalize="characters"
          autocomplete="off"
          spellcheck="false"
          maxlength="64"
          placeholder="Código de acceso…"
          aria-label="Código de acceso"
          aria-invalid={access.errorMsg ? 'true' : undefined}
          aria-describedby={access.errorMsg ? 'access-error' : undefined}
        />
        <button class="btn" type="submit" disabled={busy || !code.trim()}>
          <Icon name={busy ? 'loader' : 'send'} />
          <span>Entrar</span>
        </button>
      </form>

      {#if access.errorMsg}
        <p class="gate-empty" id="access-error" role="alert">{access.errorMsg}</p>
      {/if}
    </div>
  </div>
{/if}
