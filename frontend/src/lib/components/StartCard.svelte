<script lang="ts">
  // Tarjeta de inicio ("la invitación"): composición editorial cálida.
  // El selector de temas (TopicPicker) actúa a la vez de campo visual: cuando
  // hay tema elegido muestra el nombre y un botón para cambiarlo.
  import { NOVA_TOPICS, topicIcon, topicLabel } from '../topics'
  import { session } from '../session.svelte'
  import { settings } from '../settings.svelte'
  import Icon from './Icon.svelte'
  import TopicPicker from './TopicPicker.svelte'

  let { onStart }: { onStart: () => void } = $props()

  const hasTopic = $derived(session.requestedTopic !== '')
</script>

<section class="start-card card" aria-labelledby="startTitle">
  <span class="start-eyebrow" aria-hidden="true">
    <span class="pulse-dot"></span>
    Listo para practicar
  </span>

  <h1 class="start-title" id="startTitle">
    Habla sin miedo,
    <em>se te <span class="u">corrige</span> al instante</em>
  </h1>

  <TopicPicker />

  {#if hasTopic}
    <p class="start-chosen" aria-live="polite">
      <span class="chosen-ic"><Icon name={topicIcon(session.requestedTopic)} size="sm" /></span>
      Tema: <b>{topicLabel(session.requestedTopic)}</b>
      <button
        type="button"
        class="chosen-clear"
        aria-label="Quitar el tema elegido"
        onclick={() => {
          session.requestedTopic = ''
        }}
      >
        <Icon name="x" size="sm" />
      </button>
    </p>
  {/if}

  <button class="btn btn-primary start-btn" onclick={onStart}>
    <Icon name={settings.mode === 'voice' ? 'mic' : 'send'} />
    <span>{settings.mode === 'voice' ? 'Iniciar conversación' : 'Iniciar (texto)'}</span>
    <span class="btn-arrow" aria-hidden="true">→</span>
  </button>

  <p class="start-hint">
    {settings.mode === 'voice'
      ? 'Pulsa el orbe y habla. PracticeSpeak te escucha y te corrige al momento.'
      : 'PracticeSpeak te saluda por escrito. Tú respondes escribiendo.'}
  </p>
</section>
