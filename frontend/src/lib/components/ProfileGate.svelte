<script lang="ts">
  import { profileStore } from '../profile.svelte'
  import { toast } from '../toast.svelte'
  import Icon from './Icon.svelte'

  let name = $state('')
  let creating = $state(false)
  let nameInput = $state<HTMLInputElement | null>(null)

  $effect(() => {
    nameInput?.focus()
  })

  const initials = (n: string) => n.trim().slice(0, 2).toUpperCase() || '?'

  async function submit() {
    const clean = name.trim()
    if (!clean || creating) return
    creating = true
    try {
      await profileStore.create(clean)
      name = ''
    } catch (e) {
      toast(e instanceof Error ? e.message : 'No se pudo crear la persona.')
    } finally {
      creating = false
    }
  }
</script>

{#if profileStore.gateOpen}
  <div class="profile-gate" role="dialog" aria-modal="true" aria-label="Elige quién quieres ser">
    <div class="gate-card">
      <div class="gate-logo"><Icon name="graduation-cap" /></div>
      <h1>Hola</h1>
      <p class="gate-hint">Elige tu nombre o apodo para que Nova guarde tu progreso aparte.</p>

      <form
        class="gate-form"
        onsubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <input
          bind:this={nameInput}
          bind:value={name}
          maxlength="40"
          placeholder="Tu nombre o apodo…"
          aria-label="Tu nombre o apodo"
          autocomplete="off"
          spellcheck="false"
        />
        <button class="btn" type="submit" disabled={creating || !name.trim()}>
          <Icon name="send" />
          <span>Entrar</span>
        </button>
      </form>

      {#if profileStore.list.length}
        <ul class="gate-people">
          {#each profileStore.list as p (p.id)}
            <li>
              <button
                type="button"
                class="person-btn"
                onclick={() => profileStore.select(p)}
              >
                <span class="avatar">{initials(p.name)}</span>
                <span class="person-name">{p.name}</span>
                {#if p.sessions > 0}<span class="person-sessions">{p.sessions} sesiones</span>{/if}
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        {#if profileStore.loaded}
          <p class="gate-empty">Eres el primero. Crea tu nombre y empieza.</p>
        {/if}
      {/if}
    </div>
  </div>
{/if}