// 文件路径: frontend/src/stores/snackbar.ts (新文件)
import { defineStore } from 'pinia';
export const useSnackbarStore = defineStore('snackbar', {
    state: () => ({
        message: '',
        color: '',
        timeout: 3000,
        visible: false,
    }),
    actions: {
        show(options) {
            this.message = options.message;
            this.color = options.color || 'info';
            this.timeout = options.timeout || 3000;
            this.visible = true;
        },
        hide() {
            this.visible = false;
        },
    },
});
