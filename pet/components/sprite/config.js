// 渲染器选择（响应式）：可运行时切换 / 错误降级，无需重启或重新构建
import { ref } from 'vue'

export const RENDERER_SVG = 'svg'
export const RENDERER_SPRITESHEET = 'spritesheet'

// 默认值来自构建期环境变量（VITE_SPRITE_RENDERER，可选值 svg | spritesheet）；
// 未设置时默认 svg，保证零视觉回归与随时可回退。
export const currentRenderer = ref(import.meta.env.VITE_SPRITE_RENDERER || RENDERER_SVG)