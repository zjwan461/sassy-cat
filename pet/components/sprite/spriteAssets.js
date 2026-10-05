// 资源模块：以 Vite 模块资源引入 spritesheet
// dev（localhost:5173/pet/pet.html）与 prod（loadFile dist/pet/pet.html）
// 的 URL 均由 Vite 产出（带 hash、相对 base './' 正确解析），双环境均可用。
import spriteConfig from '../../assets/sprites/cat/config.json'

// query:'?url' 使 glob 返回 URL 字符串而非内联内容；eager 在模块初始化时完成注册。
// 形如：{ '../../assets/sprites/cat/idle.png': '/assets/idle.abc123.png', ... }
const spriteUrls = import.meta.glob('../../assets/sprites/cat/*.png', {
  query: '?url',
  import: 'default',
  eager: true
})

export { spriteConfig }

// 取帧图 URL；缺失时回退到 fallback（默认 idle），仍缺失则返回 undefined
export function getSpriteUrl(name, fallback = 'idle') {
  const key = `../../assets/sprites/cat/${name}.png`
  const url = spriteUrls[key]
  if (url) return url
  const fbKey = `../../assets/sprites/cat/${fallback}.png`
  if (spriteUrls[fbKey]) {
    // 仅在非 idle 自身缺失时告警，避免噪音
    if (name !== fallback) console.warn(`[pet-sprite] 缺少 spritesheet「${name}」，已回退「${fallback}」`)
    return spriteUrls[fbKey]
  }
  console.warn(`[pet-sprite] 缺少 spritesheet「${name}」且无「${fallback}」可回退`)
  return undefined
}

// 供测试 / 调试：返回已注册的全部资源键
export function listSpriteKeys() {
  return Object.keys(spriteUrls)
}