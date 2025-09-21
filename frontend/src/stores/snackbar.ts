// 文件路径: frontend/src/stores/snackbar.ts
import { defineStore } from 'pinia'

interface SnackbarState {
  message: string
  color: string
  timeout: number
  visible: boolean
}

export const useSnackbarStore = defineStore('snackbar', {
  state: (): SnackbarState => ({
    message: '',
    color: '',
    timeout: 3000,
    visible: false,
  }),
  actions: {
    show(options: { message: string; color?: string; timeout?: number }) {
      this.message = options.message
      this.color = options.color || 'info'
      this.timeout = options.timeout || 3000
      this.visible = true
    },
    hide() {
      this.visible = false
    },
  },
})
