import { defineStore } from 'pinia'
import type { LogEntry } from '@/models/types'

// 前端日志上限：长时间任务会产生数百条日志，无上限会持续占用内存
const MAX_LOGS = 500

export const useLogStore = defineStore('log', {
  state: () => ({
    logs: [] as LogEntry[],
  }),
  actions: {
    addLog(log: LogEntry) {
      this.logs.unshift(log)
      if (this.logs.length > MAX_LOGS) {
        this.logs.length = MAX_LOGS
      }
    },
    clearLogs() {
      this.logs = []
    },
  },
})
