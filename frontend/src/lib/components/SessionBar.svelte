<script lang="ts">
  import { session } from '../session.svelte'
  import TopicPicker from './TopicPicker.svelte'
</script>

<div class="session-bar card">
  <TopicPicker />
  <button class="btn btn-danger" onclick={() => session.stop(true)}>Terminar sesión</button>
</div>