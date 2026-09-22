<script lang="ts">
  import { session } from '../session.svelte'
  import Icon from './Icon.svelte'
</script>

{#if session.corrections.length > 0 && session.correctionsOpen}
  <section class="corrections" aria-label="Correcciones de Nova">
    <header class="panel-head">
      <h2><Icon name="sparkles" size="sm" /> Correcciones de Nova</h2>
      <button
        class="panel-close"
        aria-label="Ocultar correcciones"
        onclick={() => session.setCorrectionsOpen(false)}
      >
        <Icon name="x" size="sm" />
      </button>
    </header>
    {#each session.corrections as c, i (i)}
      <div class="correction">
        <span class="corr-wrong">{c.error}</span>
        <span class="arrow">→</span>
        <span class="corr-right">{c.correction}</span>
        {#if c.explanation}
          <p class="corr-note">{c.explanation}</p>
        {/if}
      </div>
    {/each}
  </section>
{/if}