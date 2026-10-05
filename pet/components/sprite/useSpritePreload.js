// 预加载分级：P0 白名单首屏即载，P1 空闲按需载
import { spriteConfig, getSpriteUrl } from './spriteAssets'

// P0 必载：基础态 + idle 心情变体（首屏与高频交互命中）
const ALWAYS = [
  'idle', 'idle_happy', 'idle_annoyed', 'idle_dizzy', 'idle_purring',
  'walk', 'react', 'talk', 'think', 'sleep'
]
// P1 按需：低频
const LAZY = ['walk_happy', 'remind']

let preloaded = false

export function useSpritePreload() {
  // 预载：通过 new Image() 命中浏览器缓存，避免 background-image 首帧闪烁
  const preload = async (names = ALWAYS) => {
    const urls = names.map((n) => getSpriteUrl(n)).filter(Boolean)
    await Promise.all(urls.map((u) => new Promise((res, rej) => {
      const img = new Image()
      img.onload = () => res(u)
      img.onerror = () => rej(new Error(`spritesheet 加载失败: ${u}`))
      img.src = u
    })))
    preloaded = true
    return urls
  }

  // 空闲时调用（如 requestIdleCallback）加载 P1
  const preloadLazy = () => preload(LAZY)

  return { preload, preloadLazy, ALWAYS, LAZY, isPreloaded: () => preloaded }
}

export { spriteConfig }