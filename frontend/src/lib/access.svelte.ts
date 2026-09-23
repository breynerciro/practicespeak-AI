// Puerta de acceso compartida: si el servidor pide código (NOVA_ACCESS_CODE),
// se pregunta una vez y se recuerda en localStorage para las siguientes visitas.
// Si la URL trae ?code=…, se valida en silencio y se limpia de la barra.
// Marca: PracticeSpeak AI.
import { getHealth, sendLog, setAccessCode } from './api'

const LS_KEY = 'nova-access'

function savedCode(): string {
  try {
    return localStorage.getItem(LS_KEY) || ''
  } catch {
    return ''
  }
}

export class AccessStore {
  /** Estado de la puerta: comprobando, abierta (sin código/pedirlo) o error. */
  checking = $state(true)
  gateOpen = $state(false)
  errorMsg = $state('')
  code = $state(savedCode())

  constructor() {
    setAccessCode(this.code)
    this.probe()
  }

  /** Habla con el backend: sin código configurado el paso es libre. */
  private async probe(): Promise<void> {
    // Código viajando en la URL (?code=): válido también sin pantalla.
    let urlCode = ''
    try {
      const u = new URL(location.href)
      urlCode = (u.searchParams.get('code') || '').trim()
      if (urlCode) {
        this.code = urlCode
        setAccessCode(urlCode)
        history.replaceState(null, '', u.pathname + u.search.replace(/(^|\?)code=[^&]*&?/, '$1'))
      }
    } catch {
      // URL rara: ignorar
    }
    try {
      const h = await getHealth()
      if (h?.needs_code) {
        const candidate = urlCode || this.code
        if (candidate) {
          const ok = await this.verify(candidate)
          // Código inválido (vino de la URL o recordado): mostrar la puerta.
          if (!ok) this.gateOpen = true
        } else {
          this.gateOpen = true
        }
      }
    } catch {
      // Backend caído o red caída: dejar pasar y que los errores de sesión
      // muestren el problema (no queremos bloquear la app sin motivo).
    } finally {
      this.checking = false
    }
  }

  /** Valida un código contra el servidor. true = correcto. */
  async verify(code: string): Promise<boolean> {
    try {
      const h = await getHealth(code)
      if (h?.needs_code) {
        // Sin mensaje no había feedback visible al pulsar «Entrar».
        this.errorMsg = 'Ese código no es válido. Pídeselo a quien te invitó.'
        return false
      }
      this.code = code
      setAccessCode(code)
      try {
        localStorage.setItem(LS_KEY, code)
      } catch {
        // almacenamiento no disponible: la puerta reaparecerá en cada visita
      }
      this.gateOpen = false
      this.errorMsg = ''
      sendLog('ACCESS_OK')
      return true
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      this.errorMsg = /incorrecto/i.test(msg) ? 'Ese código no es válido. Pídeselo a quien te invitó.' : msg
      return false
    }
  }

  async submit(input: string): Promise<boolean> {
    const code = input.trim()
    if (!code) {
      this.errorMsg = 'Escribe el código que te compartió tu anfitrión.'
      return false
    }
    return this.verify(code)
  }

  /** Se llama al cambiar el código en el servidor (nuevo token) o al salir. */
  forget() {
    this.code = ''
    setAccessCode('')
    try {
      localStorage.removeItem(LS_KEY)
    } catch {
      // ignorar
    }
    this.gateOpen = true
  }
}

export const access = new AccessStore()
