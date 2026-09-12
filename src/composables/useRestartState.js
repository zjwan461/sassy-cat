import { ref } from 'vue'

// 模块级单例状态：ES Module 只初始化一次，
// 切换 tab 导致 Settings 组件卸载/重新挂载时，重启进度与提示不会丢失。
const restarting = ref(false)
const restartDone = ref(false)
const toast = ref('')

export function useRestartState() {
  return { restarting, restartDone, toast }
}
