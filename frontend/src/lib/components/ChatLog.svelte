<script lang="ts">
  // Conversación visible en modo texto: burbujas tú/PracticeSpeak con la
  // respuesta en streaming en vivo (antes había que abrir el Historial).
  import { session } from '../session.svelte'
  import Icon from './Icon.svelte'

  let listEl: HTMLDivElement | null = $state(null)

  // Auto-scroll al llegar un turno nuevo o con cada tramo del streaming.
  $effect(() => {
    void session.history.length
    void session.streamText
    if (listEl) listEl.scrollTop = listEl.scrollHeight
  })
</script>

{#if session.history.length === 0 && session.streamText === null}
  <p class="chat-empty" role="status">PracticeSpeak está abriendo la conversación…</p>
{/if}

<div class="chat-log" bind:this={listEl} role="log" aria-label="Conversación con PracticeSpeak">
  {#each session.history as h, i (i)}
    <div class="chat-row {h.role === 'user' ? 'is-user' : 'is-ai'}">
      {#if h.role === 'assistant'}
        <span class="chat-avatar" aria-hidden="true"><Icon name="audio-lines" size="sm" /></span>
      {/if}
      <div class="chat-bubble">
        <span class="chat-who">{h.role === 'user' ? 'Tú' : 'PracticeSpeak'}</span>
        <p class="chat-text">{h.content}</p>
      </div>
    </div>
  {/each}
  {#if session.streamText !== null}
    <div class="chat-row is-ai">
      <span class="chat-avatar" aria-hidden="true"><Icon name="audio-lines" size="sm" /></span>
      <div class="chat-bubble">
        <span class="chat-who">PracticeSpeak</span>
        <p class="chat-text">{session.streamText}<span class="blink" aria-hidden="true"></span></p>
      </div>
    </div>
  {/if}
</div>
