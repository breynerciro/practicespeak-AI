<script lang="ts">
  import { iconPath } from '../icons'

  let { name, size = 'md' }: { name: string; size?: 'md' | 'sm' } = $props()
</script>

<span class={size === 'sm' ? 'icon icon-sm' : 'icon'} aria-hidden="true">
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
  >{@html iconPath(name)}</svg>
</span>