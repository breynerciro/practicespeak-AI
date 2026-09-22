<script lang="ts">
  import { NOVA_TOPICS, topicLabel } from '../topics'
  import { session } from '../session.svelte'
  import { toast } from '../toast.svelte'
  import Icon from './Icon.svelte'

  let open = $state(false)

  function pick(id: string, label: string) {
    session.requestedTopic = id
    session.setTranscriptOpen(false)
    if (label) toast('Tema: ' + label)
    open = false
  }
</script>

<details
  class="topic-picker"
  bind:open={open}
>
  <summary aria-label="Elegir tema de conversación">
    <Icon name="list" size="sm" />
    <span>Temas</span>
  </summary>
  <div class="topic-chips">
    {#each NOVA_TOPICS as t (t.id || 'random')}
      <button
        type="button"
        class="topic-chip"
        class:selected={session.requestedTopic === t.id}
        onclick={() => pick(t.id, t.label)}
      >
        <Icon name={t.icon} size="sm" />
        <span>{t.label}</span>
      </button>
    {/each}
  </div>
</details>

{#if session.requestedTopic}
  <p class="requested-topic">Tema elegido: {topicLabel(session.requestedTopic)}</p>
{/if}