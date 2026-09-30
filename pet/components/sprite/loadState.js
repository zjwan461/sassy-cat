// 资源加载 / 降级状态（响应式）
import { ref } from 'vue'
import { currentRenderer, RENDERER_SVG } from './config'

// 记录降级原因，供 UI / 日志展示
export const loadState = ref({ status: 'ok', reason: '' })

// 预加载 / 帧加载失败时降级到 SVG 渲染器
// 因 currentRenderer 是响应式 ref，组件会自动重渲染为 SVG
export function fallbackToSvg(reason) {
  loadState.value = { status: 'degraded', reason: String(reason || '') }
  currentRenderer.value = RENDERER_SVG
}