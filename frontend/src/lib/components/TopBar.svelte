<script lang="ts">
  import { profileStore } from '../profile.svelte'
  import Icon from './Icon.svelte'
  import SettingsMenu from './SettingsMenu.svelte'

  let open = $state(false)

  const initials = (n?: string) => (n ? n.trim().slice(0, 2).toUpperCase() : '?')

  function toggle() {
    open = !open
  }
</script>

<header class="topbar">
  <div class="brand">
    <span class="logo"><Icon name="graduation-cap" /></span>
    <span class="brand-name">Nova</span>
    {#if profileStore.current}
      <span class="who">{profileStore.current.name}</span>
    {/if}
  </div>

  <div style="position:relative; display:flex; gap:10px; align-items:center;">
    <button
      class="person-chip"
      id="personChip"
      aria-label="Cambiar de persona"
      title="Cambiar de persona"
      onclick={() => profileStore.switchPerson()}
    >
      <span class="menu-avatar">{initials(profileStore.current?.name)}</span>
    </button>

    <button
      class="menu-btn"
      id="menuBtn"
      aria-haspopup="true"
      aria-expanded={open}
      aria-controls="settingsMenu"
      aria-label="Ajustes"
      onclick={toggle}
    >
      <Icon name="settings-2" />
    </button>

    {#if open}
      <SettingsMenu
        onclose={() => {
          open = false
        }}
      />
    {/if}
  </div>
</header>