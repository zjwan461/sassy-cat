// 桌宠 sprite 迁移：矩阵/配置一致性轻量校验
// 用法：node tests/tmp_pet_sprite_check.mjs
// 校验点（对齐 plans/pet-sprite-migration-plan.md 第 7.1 节）：
//   1) 动画矩阵引用的每个 animationName 都存在于 config.json.animations（否则渲染器会回退 idle）
//   2) 矩阵 drag 行映射到 idle 相关（无独立 drag 资源）
//   3) 预加载白名单（ALWAYS/LAZY）均在 config.json 中存在
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')

const animSrc = readFileSync(resolve(root, 'pet/components/sprite/useSpriteAnim.js'), 'utf8')
const preloadSrc = readFileSync(resolve(root, 'pet/components/sprite/useSpritePreload.js'), 'utf8')
const config = JSON.parse(readFileSync(resolve(root, 'pet/assets/sprites/cat/config.json'), 'utf8'))


const animKeys = new Set(Object.keys(config.animations))

// 仅提取「冒号 + 单引号值」形态的 animationName（避免被空串键 '' 打乱引号配对）
const valueRe = /:\s*'([^']*)'/g
const pickValues = (text) => [...text.matchAll(valueRe)].map((m) => m[1]).filter(Boolean)

// MATRIX 代码块
const matrixBlock = animSrc.slice(animSrc.indexOf('const MATRIX'), animSrc.indexOf('export function resolveAnimation'))
const referenced = new Set(pickValues(matrixBlock))

const errors = []
for (const name of referenced) {
  if (!animKeys.has(name)) errors.push(`矩阵引用的动画「${name}」不在 config.json.animations 中`)
}

// drag 行必须全部映射到 idle* 资源（无独立 drag 帧）
const dragLine = matrixBlock.split('\n').find((l) => l.trim().startsWith('drag:'))
if (!dragLine) errors.push('未找到矩阵 drag 行')
else {
  for (const v of pickValues(dragLine)) {
    if (!v.startsWith('idle')) errors.push(`drag 行映射到非 idle 资源「${v}」`)
  }
}

// 预加载白名单覆盖校验（ALWAYS / LAZY 数组内的键名）
const preloadBlock = preloadSrc.slice(preloadSrc.indexOf('const ALWAYS'), preloadSrc.indexOf('let preloaded'))
const listNames = pickValues(preloadBlock.replace(/[a-z]+:\s*'[^']*',/g, ''))
for (const n of listNames) {
  if (!animKeys.has(n)) errors.push(`预加载白名单包含未定义动画「${n}」`)
}
const fw = config.frameWidth
const report = []
for (const name of animKeys) {
  report.push(`  ${name} (${config.animations[name].frames} 帧)`)
}

console.log(`config.animations 共 ${animKeys.size} 项：\n${report.join('\n')}`)
console.log(`矩阵引用动画名：${[...referenced].join(', ')}`)

if (errors.length) {
  console.error('\n❌ 校验失败：')
  errors.forEach((e) => console.error('  - ' + e))
  process.exit(1)
}
console.log(`\n✅ 校验通过：矩阵/预加载/配置三者一致（frameWidth=${fw}）`)