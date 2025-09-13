import { defineStore } from 'pinia';
import type { LogEntry } from '@/models/types';

export const useLogStore = defineStore('log', {
  state: () => ({
    logs: [] as LogEntry[],
  }),
  actions: {
    addLog(log: LogEntry) {
      this.logs.unshift(log);
    },
    clearLogs() {
      this.logs = [];
    },
  },
});
