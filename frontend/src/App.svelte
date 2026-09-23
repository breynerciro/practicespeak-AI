<script lang="ts">
  import { ankiUrl, fetchStats, sendLog } from './lib/api'
  import { access } from './lib/access.svelte'
  import { profileStore } from './lib/profile.svelte'
  import { session } from './lib/session.svelte'
  import { settings } from './lib/settings.svelte'
  import { toast } from './lib/toast.svelte'
  import AccessGate from './lib/components/AccessGate.svelte'
  import Composer from './lib/components/Composer.svelte'
  import CorrectionPanel from './lib/components/CorrectionPanel.svelte'
  import GrammarPanel from './lib/components/GrammarPanel.svelte'
  import HttpsNotice from './lib/components/HttpsNotice.svelte'
  import Icon from './lib/components/Icon.svelte'
  import Orb from './lib/components/Orb.svelte'
  import ProfileGate from './lib/components/ProfileGate.svelte'
  import SessionBar from './lib/components/SessionBar.svelte'
  import StartCard from './lib/components/StartCard.svelte'
  import Toast from './lib/components/Toast.svelte'
  import TopBar from './lib/components/TopBar.svelte'
  import Transcript from './lib/components/Transcript.svelte'
  import { topicLabel } from './lib/topics'

  async function stats() {
    try {
      const s = await fetchStats(profileStore.current?.id)
      if (!s || typeof s.total_sessions !== 'number') {
        toast('Sin talleres todavía. Empieza a practicar.')
        return
      }
      const langs = Object.entries(s.by_language || {})
        .map(([l, c]) => `${l} (${c})`)
        .join(', ')
      toast(
        `Talleres: ${s.total_sessions} · Esta semana: ${s.sessions_last_7d ?? 0} · Correcciones: ${s.total_corrections ?? 0}` +
          (langs ? ` · Idiomas: ${langs}` : ''),
      )
    } catch {
      toast('Progreso no disponible ahora.')
    }
  }

  function exportAnki() {
    const url = ankiUrl(profileStore.current?.id)
    sendLog('EXPORT_ANKI ' + url)
    window.open(url, '_blank')
  }

  const correctionsCount = $derived(session.corrections.length)
  let grammarOpen = $state(false)
</script>

<a class="skip-link" href="#nova-content">Saltar al contenido</a>
<HttpsNotice />
<div class="atmo" aria-hidden="true"></div>
<TopBar />

<main class="nova-view" id="nova-content">
  {#if session.topic}
    <p class="topic-pill">
      <span class="topic-pill-ic"><Icon name="target" size="sm" /></span>
      {topicLabel(session.topic)}
    </p>
  {/if}

  <div class="nova-stage">
    <Orb />
    <p class="status" role="status" aria-live="polite">{session.status}</p>
  </div>

  {#if !session.running}
    <StartCard
      onStart={() => {
        session.start()
      }}
    />
  {:else}
    <SessionBar />

    <Composer />

    <div class="ghost-row">
      <button
        class="ghost-link"
        onclick={() => session.setTranscriptOpen(!session.transcriptOpen)}
        aria-expanded={session.transcriptOpen}
      >
        <Icon name="list" size="sm" />
        Historial
      </button>
      {#if correctionsCount > 0}
        <button
          class="ghost-link"
          onclick={() => session.setCorrectionsOpen(!session.correctionsOpen)}
          aria-expanded={session.correctionsOpen}
        >
          <Icon name="sparkles" size="sm" />
          Correcciones ({correctionsCount})
        </button>
      {/if}
    </div>
  {/if}

  <CorrectionPanel />
  <Transcript />

  <footer class="tool-row">
    <button class="ghost-link" onclick={stats}>
      <Icon name="bar-chart" size="sm" />
      Progreso
    </button>
    <button class="ghost-link" onclick={() => (grammarOpen = true)}>
      <Icon name="pen-line" size="sm" />
      Corregir texto
    </button>
    <button class="ghost-link" onclick={exportAnki}>
      <Icon name="chevron-down-circle" size="sm" />
      Exportar a Anki
    </button>
  </footer>
</main>

<Toast />

{#if grammarOpen}
  <GrammarPanel
    onclose={() => {
      grammarOpen = false
    }}
  />
{/if}

{#if profileStore.gateOpen && !access.gateOpen}
  <ProfileGate />
{/if}

{#if access.gateOpen}
  <AccessGate />
{/if}