<template>
  <div ref="boxRef" class="css-sprite" :style="boxStyle"></div>
</template>

<script setup>
// Spritesheet 渲染器：CSS background-position 逐帧（GPU 合成、零 JS 每帧绘制、原生高分屏）
// 帧推进：内部 rAF + performance.now() 时间戳，按动画 fps 计算帧号（无累积漂移）。
// 翻转不在此处处理，统一由 PetApp 的 .flip 容器负责（唯一出口）。
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { spriteConfig, getSpriteUrl } from './spriteAssets'
import { resolveAnimation } from './useSpriteAnim'

const props = defineProps({
  state: { type: String, required: true },
  mood: { type: String, default: '' },
  facingLeft: { type: Boolean, default: false }
})
const emit = defineEmits(['complete'])

const boxRef = ref(null)
const fw = spriteConfig.frameWidth
const fh = spriteConfig.frameHeight

// 唯一动画名：由矩阵解析，渲染器不做拼接/回退猜测
const animationName = computed(() => resolveAnimation(props.state, props.mood))
const animConfig = computed(() =>
  spriteConfig.animations[animationName.value] || { frames: 1, fps: 4, loop: true }
)
const url = computed(() => getSpriteUrl(animationName.value))

const boxStyle = computed(() => ({
  width: `${fw}px`,
  height: `${fh}px`,
  backgroundImage: url.value ? `url("${url.value}")` : 'none',
  backgroundRepeat: 'no-repeat'
}))

// ---------- rAF + 时间戳 帧推进 ----------
let rafId = null
let startAt = 0        // 当前动画开始时间
let currentFrame = 0
let playing = true
let completedFlag = false

function applyPosition() {
  const el = boxRef.value
  if (!el) return
  el.style.backgroundPosition = `${-(currentFrame * fw)}px 0`
}
function tick() {
  rafId = requestAnimationFrame(tick)
  if (!playing) return
  const anim = animConfig.value
  const elapsed = (performance.now() - startAt) / 1000
  const raw = Math.floor(elapsed * anim.fps)
  if (!anim.loop && raw >= anim.frames) {
    // 非循环播完：冻结在最后一帧并通知上层
    currentFrame = anim.frames - 1
    applyPosition()
    if (!completedFlag) { completedFlag = true; emit('complete') }
    return
  }
  currentFrame = raw % anim.frames
  applyPosition()
}
function restart() {
  startAt = performance.now()
  currentFrame = 0
  completedFlag = false
  playing = true
  applyPosition()
}

// 动画变化时重启（矩阵保证值稳定；同名切换不触发）
watch(animationName, restart)

defineExpose({
  play: () => { playing = true; if (!rafId) rafId = requestAnimationFrame(tick) },
  pause: () => { playing = false },
  resume: () => { playing = true },
  getCurrentFrame: () => currentFrame
})

onMounted(() => { restart(); rafId = requestAnimationFrame(tick) })
onBeforeUnmount(() => { cancelAnimationFrame(rafId); rafId = null })
</script>

<style scoped>
/* background-position 由 GPU 合成；background-size 保持原始尺寸即可保证高分屏锐利 */
.css-sprite { position: relative; image-rendering: auto; }
</style>