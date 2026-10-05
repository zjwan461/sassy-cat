// 桌宠渲染器接口契约（v2：声明式 props + 事件）
// 说明：本项目为纯 JS（Vite + Vue3），此处仅作文档化类型定义，无运行时产物。
// 渲染器是「受控组件」：只声明式消费 PetApp 的状态，不接收命令式状态调用。

export type PetState = 'idle' | 'walk' | 'drag' | 'react' | 'think' | 'talk' | 'sleep' | 'remind'

export type PetMood = '' | 'happy' | 'annoyed' | 'dizzy' | 'purring'

// 渲染器对外契约：受控组件，仅消费状态 props
export interface SpriteRendererProps {
  state: PetState
  mood: PetMood
  facingLeft: boolean
}

// 渲染器事件：
//   complete: 非循环动画（react 等）播放完成，由上层决定下一状态
export type SpriteRendererEmits = {
  complete: []
}

// 可选命令式接口（仅播放控制；状态切换一律走 props，不走命令式）
export interface SpriteRendererInstance {
  play(): void
  pause(): void
  resume(): void
  getCurrentFrame(): number
}