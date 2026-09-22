<script lang="ts">
  import { toastStore } from '../toast.svelte'
</script>

{#if toastStore.visible}
  <div class="toast" role="status" aria-live="polite">{toastStore.message}</div>
{/if}