// Persona anónima actual: apodo elegido sin contraseña (multi-usuario sin login).
// Se recuerda en localStorage para saltar la pantalla en el mismo dispositivo.
import { listProfiles, createProfile as apiCreate, sendLog } from './api'
import type { Profile } from './types'

const LS_KEY = 'nova-profile'

interface LocalProfile {
  id: number
  name: string
}

function savedProfile(): LocalProfile | null {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return null
    const p = JSON.parse(raw) as LocalProfile
    return p && typeof p.id === 'number' && typeof p.name === 'string' ? p : null
  } catch {
    return null
  }
}

class ProfileStore {
  current: Profile | null = $state(null)
  list: Profile[] = $state([])
  gateOpen = $state(true)
  /** true tras la primera carga del servidor */
  loaded = $state(false)

  constructor() {
    const saved = savedProfile()
    if (saved) {
      this.current = { id: saved.id, name: saved.name, created_at: 0, sessions: 0 }
      this.gateOpen = false
    }
    // La lista de perfiles NO se pide aquí: App la carga cuando la puerta de
    // acceso está resuelta (sin código o ya validado), evitando 401 prematuros.
  }

  async refresh() {
    try {
      const list = await listProfiles()
      this.list = Array.isArray(list) ? list : []
      this.loaded = true
      // si el perfil guardado existe en el servidor, actualiza sus datos
      if (this.current) {
        const fresh = this.list.find((p) => p.id === this.current!.id)
        if (fresh) this.current = fresh
      }
    } catch {
      // backend sin /api/profiles (versión vieja): se mantiene el apodo local
    }
  }

  open() {
    this.gateOpen = true
    this.refresh()
  }

  close() {
    this.gateOpen = false
  }

  select(profile: Profile) {
    this.current = profile
    localStorage.setItem(LS_KEY, JSON.stringify({ id: profile.id, name: profile.name }))
    sendLog(`PERFIL_SELECCIONADO id=${profile.id} name=${profile.name}`)
    this.close()
  }

  async create(name: string): Promise<void> {
    const clean = name.trim()
    if (!clean) throw new Error('Escribe un nombre primero.')
    try {
      const profile = await apiCreate(clean)
      this.list = [...this.list, profile]
      this.select(profile)
    } catch (e) {
      sendLog('PERFIL_CREAR_ERR ' + (e instanceof Error ? e.message : String(e)))
      throw e
    }
  }

  /** "Cambiar de persona": guarda la sesión y vuelve a la puerta. */
  switchPerson() {
    sendLog('PERFIL_CAMBIAR')
    this.open()
  }
}

export const profileStore = new ProfileStore()