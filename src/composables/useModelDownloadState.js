import { ref } from 'vue'

// 模块级单例状态：ES Module 只初始化一次，
// 切换 tab 导致 Settings 组件卸载/重新挂载时，下载进度与结果提示不会丢失
// （下载请求由模块级 Promise 持续等待，不随组件卸载而中断）。
const downloading = ref(false)
const result = ref(null) // { ok: boolean, text: string } | null

export function useModelDownloadState() {
  return { downloading, result }
}
