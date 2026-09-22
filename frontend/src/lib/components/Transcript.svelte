<script lang="ts">
  import { session } from '../session.svelte'
  import Icon from './Icon.svelte'

  let panelEl: HTMLDivElement | null = $state(null)

  $effect(() => {
    if (panelEl) panelEl.scrollTop = panelEl.scrollHeight
  })
</script>

{#if session.transcriptOpen}
  <section class="nova-transcript" role="log" aria-label="Historial de la conversación">
    <header class="panel-head">
      <h2>Historial</h2>
      <button
        class="panel-close"
        aria-label="Ocultar historial"
        onclick={() => session.setTranscriptOpen(false)}
      >
        <Icon name="x" size="sm" />
      </button>
    </header>
    <div class="transcript-list" bind:this={panelEl}>
      {#each session.history as h, i (i)}
        <div class="t-turn {h.role === 'user' ? 't-user' : 't-ai'}">
          <span class="t-who">{h.role === 'user' ? 'Tú' : 'Nova'}</span>
          <span class="t-text">{h.content}</span>
        </div>
      {/each}
      {#if session.streamText !== null}
        <div class="t-turn t-ai">
          <span class="t-who">Nova</span>
          <span class="t-text t-stream">{session.streamText}<span class="blink" aria-hidden="true"></span></span>
        </div>
      {/if}
    </div>
  </section>
{/if}