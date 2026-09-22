<script lang="ts">
  import { PLACEHOLDERS } from '../i18n'
  import { session } from '../session.svelte'
  import { settings } from '../settings.svelte'
  import Icon from './Icon.svelte'

  let text = $state('')
  let inputEl: HTMLInputElement | null = $state(null)

  $effect(() => {
    if (session.focusTick > 0) inputEl?.focus()
  })

  function send() {
    const v = text
    if (!v.trim()) return
    text = ''
    session.sendText(v)
  }
</script>

{#if settings.mode === 'text'}
  <div class="composer">
    <input
      bind:this={inputEl}
      bind:value={text}
      type="text"
      autocomplete="off"
      spellcheck="false"
      enterkeyhint="send"
      maxlength="1000"
      placeholder={PLACEHOLDERS[settings.lang]}
      aria-label="Escribe tu respuesta a Nova"
      onkeydown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          send()
        }
      }}
    />
    <button class="send-btn" aria-label="Enviar mensaje" onclick={send} disabled={!text.trim()}>
      <Icon name="send" />
    </button>
  </div>
{/if}