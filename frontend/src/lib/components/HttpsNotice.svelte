<script lang="ts">
  import { getHealth } from '../api'
  import Icon from './Icon.svelte'

  let show = $state(false)
  let href = $state('')

  $effect(() => {
    if (location.protocol !== 'http:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1') return
    getHealth()
      .then((h) => {
        if (h.public_hostname) {
          href = 'https://' + h.public_hostname + ':8443'
          show = true
        }
      })
      .catch(() => {})
  })
</script>

{#if show}
  <div class="https-overlay">
    <div class="https-lock"><Icon name="lock" /></div>
    <p class="https-msg">
      <b>Necesitas la versión segura</b><br />
      El micrófono solo funciona con HTTPS.
    </p>
    <a class="btn" href={href}>Abrir Nova segura</a>
  </div>
{/if}