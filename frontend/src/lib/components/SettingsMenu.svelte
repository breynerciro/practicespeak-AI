<script lang="ts">
  import { getTtsBuffer, listTtsVoices } from '../api'
  import { playBuffer, stopPlayback } from '../audio/playback'
  import { LANG_NAMES, LANG_NAMES_ES, VOICE_PREVIEW } from '../i18n'
  import { settings } from '../settings.svelte'
  import { readTheme, watchSystemTheme, applyTheme, setTheme, type ThemeMode } from '../theme'
  import { toast } from '../toast.svelte'
  import type { Language, TtsVoice } from '../types'
  import Icon from './Icon.svelte'

  let { onclose }: { onclose: () => void } = $props()

  const LANGS: Language[] = ['en', 'pt', 'fr', 'de', 'it', 'es', 'ru', 'zh']
  const THEMES: { mode: ThemeMode; label: string }[] = [
    { mode: 'auto', label: 'Auto' },
    { mode: 'light', label: 'Día' },
    { mode: 'dark', label: 'Noche' },
  ]

  let previewing = $state(false)
  let themeMode = $state(readTheme())
  let voices: TtsVoice[] = $state([])

  $effect(() => {
    themeMode = applyTheme()
    const off = watchSystemTheme(() => {
      themeMode = applyTheme()
    })
    const onDoc = (e: MouseEvent) => {
      const el = e.target as HTMLElement
      if (!el.closest('#settingsMenu') && !el.closest('#menuBtn') && !el.closest('#personChip')) onclose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onclose()
    }
    document.addEventListener('click', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      off()
      document.removeEventListener('click', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  })

  $effect(() => {
    const lang = settings.lang
    listTtsVoices(lang)
      .then((list) => {
        voices = list
      })
      .catch(() => {
        voices = []
      })
  })

  function pickTheme(mode: ThemeMode) {
    themeMode = mode
    setTheme(mode)
  }

  async function preview(gender: 'female' | 'male') {
    if (previewing) {
      stopPlayback()
      previewing = false
      return
    }
    stopPlayback()
    const data = await getTtsBuffer(
      VOICE_PREVIEW[settings.lang],
      settings.lang,
      gender,
      settings.ttsVoice[settings.lang],
      settings.speed,
    ).catch(() => null)
    if (!data) {
      toast('Voz no disponible ahora (sin conexión).')
      return
    }
    previewing = true
    const h = await playBuffer(data, () => {
      previewing = false
    })
    if (!h) previewing = false
  }
</script>

<div class="menu" id="settingsMenu">
  <div class="menu-group">
    <div class="menu-label">¿Qué quieres practicar?</div>
    <div class="seg">
      {#each LANGS as lang (lang)}
        <button
          type="button"
          class="seg-btn"
          class:active={settings.lang === lang}
          onclick={() => settings.setLang(lang)}
        >
          {LANG_NAMES[lang]}
        </button>
      {/each}
    </div>
  </div>

  <div class="menu-group">
    <div class="menu-label">Modo de práctica</div>
    <div class="seg">
      <button
        type="button"
        class="seg-btn"
        class:active={settings.mode === 'voice'}
        onclick={() => settings.setMode('voice')}
      >
        Hablando
      </button>
      <button
        type="button"
        class="seg-btn"
        class:active={settings.mode === 'text'}
        onclick={() => settings.setMode('text')}
      >
        Texto
      </button>
    </div>
  </div>

  <div class="menu-group">
    <div class="menu-label">Voz de Nova</div>
    <div class="seq">
      <button
        type="button"
        class="seq-btn"
        class:active={settings.gender === 'female'}
        onclick={() => settings.setGender('female')}
      >
        Mujer
      </button>
      <button type="button" class="seq-btn" onclick={() => preview('female')} aria-label="Escuchar la voz de mujer">
        <Icon name="audio-lines" size="sm" />
      </button>
      <button
        type="button"
        class="seq-btn"
        class:active={settings.gender === 'male'}
        onclick={() => settings.setGender('male')}
      >
        Hombre
      </button>
      <button type="button" class="seq-btn" onclick={() => preview('male')} aria-label="Escuchar la voz de hombre">
        <Icon name="audio-lines" size="sm" />
      </button>
      {#if previewing}
        <button
          type="button"
          class="hear-btn"
          aria-label="Detener la voz de muestra"
          onclick={() => {
            stopPlayback()
            previewing = false
          }}
        >
          <Icon name="square" size="sm" />
        </button>
      {/if}
    </div>
    <div class="voice-pick">
      <label for="ttsVoice">Voz concreta de {LANG_NAMES_ES[settings.lang]}</label>
      <select
        id="ttsVoice"
        value={settings.ttsVoice[settings.lang] ?? ''}
        onchange={(e) => settings.setTtsVoice(settings.lang, (e.currentTarget as HTMLSelectElement).value)}
      >
        <option value="">Auto ({settings.gender === 'male' ? 'Hombre' : 'Mujer'})</option>
        {#each voices as v (v.id)}
          <option value={v.id}>{v.name}</option>
        {/each}
      </select>
    </div>
  </div>

  <div class="menu-group">
    <div class="menu-label">Velocidad de voz</div>
    <div class="seg">
      <button
        type="button"
        class="seg-btn"
        class:active={settings.speed === 0.75}
        onclick={() => settings.setSpeed(0.75)}
      >
        Lenta
      </button>
      <button
        type="button"
        class="seg-btn"
        class:active={settings.speed === 1}
        onclick={() => settings.setSpeed(1)}
      >
        Normal
      </button>
      <button
        type="button"
        class="seg-btn"
        class:active={settings.speed === 1.25}
        onclick={() => settings.setSpeed(1.25)}
      >
        Rápida
      </button>
      <button
        type="button"
        class="seg-btn"
        class:active={settings.speed === 1.5}
        onclick={() => settings.setSpeed(1.5)}
      >
        Turbo
      </button>
    </div>
  </div>

  <div class="menu-group">
    <div class="menu-label">Sensibilidad del micrófono</div>
    <div class="seg">
      <button
        type="button"
        class="seg-btn"
        class:active={settings.micSensitivity === 'baja'}
        onclick={() => settings.setMicSensitivity('baja')}
      >
        Baja
      </button>
      <button
        type="button"
        class="seg-btn"
        class:active={settings.micSensitivity === 'normal'}
        onclick={() => settings.setMicSensitivity('normal')}
      >
        Normal
      </button>
      <button
        type="button"
        class="seg-btn"
        class:active={settings.micSensitivity === 'alta'}
        onclick={() => settings.setMicSensitivity('alta')}
      >
        Alta
      </button>
    </div>
  </div>

  <div class="menu-group">
    <div class="menu-label">Apariencia</div>
    <div class="seg">
      {#each THEMES as th (th.mode)}
        <button
          type="button"
          class="seg-btn"
          class:active={themeMode === th.mode}
          onclick={() => pickTheme(th.mode)}
        >
          {th.label}
        </button>
      {/each}
    </div>
  </div>
</div>