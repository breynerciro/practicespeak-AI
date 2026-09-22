<script lang="ts">
  import { settings } from '../settings.svelte'
  import Icon from './Icon.svelte'
  import TopicPicker from './TopicPicker.svelte'

  let { onStart }: { onStart: () => void } = $props()
</script>

<div class="start-card card">
  <TopicPicker />
  <button class="btn btn-primary start-btn" onclick={onStart}>
    <Icon name={settings.mode === 'voice' ? 'mic' : 'message'} />
    <span>{settings.mode === 'voice' ? 'Iniciar conversación' : 'Iniciar (texto)'}</span>
  </button>
  <p class="start-hint">
    {settings.mode === 'voice'
      ? 'Haz clic en el orbe y habla con Nova. Te irá corrigiendo al momento.'
      : 'Nova te saluda por escrito. Tú respondes escribiendo.'}
  </p>
</div>