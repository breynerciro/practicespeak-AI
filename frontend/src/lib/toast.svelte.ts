// Store de toasts (rol=status declara la región live, accesible de serie).
class ToastStore {
  message = $state('')
  visible = $state(false)
  private _t: ReturnType<typeof setTimeout> | undefined

  show = (msg: string, ms = 3000) => {
    this.message = msg
    this.visible = true
    clearTimeout(this._t)
    this._t = setTimeout(() => {
      this.visible = false
      this.message = ''
    }, ms)
  }
}

export const toastStore = new ToastStore()
export const toast = (msg: string) => toastStore.show(msg)