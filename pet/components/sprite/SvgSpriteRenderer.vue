<template>
  <svg
    class="svg-sprite"
    :class="animClass"
    viewBox="0 0 120 110"
    width="120"
    height="110"
  >
    <path :d="tailPath" fill="none" stroke="#334155" stroke-width="8" stroke-linecap="round"/>
    <ellipse cx="60" cy="76" rx="34" ry="26" fill="#64748b"/>
    <path d="M36 38 L44 16 L56 34 Z" fill="#64748b"/>
    <path d="M84 38 L76 16 L64 34 Z" fill="#64748b"/>
    <path d="M40 33 L45 21 L51 31 Z" fill="#f9a8d4"/>
    <path d="M80 33 L75 21 L69 31 Z" fill="#f9a8d4"/>
    <circle cx="60" cy="46" r="26" fill="#64748b"/>
    <!-- 表情：开心（眯眼笑） -->
    <template v-if="mood === 'happy'">
      <path d="M46 42 q6 -4 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M62 42 q6 -4 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M52 54 q8 6 16 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
    </template>
    <!-- 表情：不满（斜眼） -->
    <template v-else-if="mood === 'annoyed'">
      <path d="M46 40 l12 4" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M74 40 l-12 4" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <circle cx="51" cy="45" r="3" fill="#1e293b"/>
      <circle cx="69" cy="45" r="3" fill="#1e293b"/>
      <path d="M54 56 q6 -2 12 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
    </template>
    <!-- 表情：头晕（螺旋眼） -->
    <template v-else-if="mood === 'dizzy'">
      <path d="M48 42 q3 -3 6 0 q3 3 6 0" stroke="#1e293b" stroke-width="2" fill="none" stroke-linecap="round" class="spin-eye"/>
      <path d="M64 42 q3 -3 6 0 q3 3 6 0" stroke="#1e293b" stroke-width="2" fill="none" stroke-linecap="round" class="spin-eye"/>
      <path d="M55 55 q5 3 10 0" stroke="#1e293b" stroke-width="2" fill="none" stroke-linecap="round"/>
    </template>
    <!-- 表情：撸猫中（享受）；♥ 已移入 SpriteOverlay -->
    <template v-else-if="mood === 'purring'">
      <path d="M46 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M62 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M53 54 q7 5 14 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
    </template>
    <!-- 默认表情：眨眼 -->
    <template v-else-if="eyesClosed">
      <path d="M46 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M62 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
    </template>
    <template v-else>
      <circle cx="51" cy="43" r="4" fill="#1e293b"/>
      <circle cx="69" cy="43" r="4" fill="#1e293b"/>
      <circle cx="52.5" cy="41.5" r="1.4" fill="#fff"/>
      <circle cx="70.5" cy="41.5" r="1.4" fill="#fff"/>
    </template>
    <path v-if="state === 'talk' && !hasMoodExpr" d="M55 54 q5 6 10 0 q-5 8 -10 0" fill="#be185d"/>
    <path v-else-if="!hasMoodExpr" d="M55 54 q5 4 10 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
    <path d="M30 48 h12 M31 55 l11 -3 M90 48 h-12 M89 55 l-11 -3" stroke="#1e293b" stroke-width="1.6" stroke-linecap="round"/>
  </svg>
</template>

<script setup>
// SVG 渲染器：内联 SVG 无条件视觉回归地迁移原实现。
// 帧时钟内聚于渲染器（内部 rAF + 时间戳，220ms/帧，复现原 setInterval(++, 220) 节奏）。
// 角色本体的 CSS 关键帧动画也内聚于此（避免 scoped 样式跨组件穿透问题，
// 且动画作用于 svg 元素而非持有 translateX(-50%) 的容器，保证水平居中不被覆盖）。
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  state: { type: String, default: 'idle' },
  mood: { type: String, default: '' },
  facingLeft: { type: Boolean, default: false }
})
defineEmits(['complete'])

// ---------- 帧驱动（内部 rAF + 时间戳） ----------
const frameIdx = ref(0)
let rafId = null
let firstT = null
function tick(t) {
  rafId = requestAnimationFrame(tick)
  if (firstT === null) firstT = t
  // 帧号 = 距首次 tick 的累计时长按 220ms 步进，等价于原 setInterval(++, 220)
  frameIdx.value = Math.floor((t - firstT) / 220)
}

const hasMoodExpr = computed(() =>
  props.mood === 'happy' || props.mood === 'annoyed' || props.mood === 'dizzy' || props.mood === 'purring'
)
const animClass = computed(() => [
  props.state,
  { happy: props.mood === 'happy', annoyed: props.mood === 'annoyed', dizzy: props.mood === 'dizzy' }
])
const tailPath = computed(() => {
  // 尾巴轻微摆动
  const w = Math.sin(frameIdx.value * 0.9) * 12
  return `M92 84 q20 ${-8 + w} ${16 + w * 0.4} -26`
})
const eyesClosed = computed(() => {
  if (props.state === 'sleep') return true
  return frameIdx.value % 8 === 6 // 周期眨眼
})

defineExpose({
  play: () => { firstT = null; if (!rafId) rafId = requestAnimationFrame(tick) },
  pause: () => { cancelAnimationFrame(rafId); rafId = null },
  resume: () => { firstT = null; if (!rafId) rafId = requestAnimationFrame(tick) },
  getCurrentFrame: () => frameIdx.value
})

onMounted(() => { rafId = requestAnimationFrame(tick) })
onBeforeUnmount(() => { cancelAnimationFrame(rafId); rafId = null })
</script>

<style scoped>
/* 状态动画（心情类在样式表后定义，故 mood 动画覆盖 state 动画，与原实现一致） */
.svg-sprite.idle   { animation: breathe 2.6s ease-in-out infinite; }
.svg-sprite.walk   { animation: bob .44s infinite; }
.svg-sprite.react  { animation: bounce .3s 2; }
.svg-sprite.remind { animation: wiggle .35s 4; }
.svg-sprite.talk   { animation: bob .3s infinite; }
.svg-sprite.think  { animation: breathe 1.6s ease-in-out infinite; }
.svg-sprite.sleep  { animation: breathe 4s ease-in-out infinite; }
/* drag 无动画（与原实现一致） */
.svg-sprite.happy   { animation: purr .5s ease-in-out infinite; }
.svg-sprite.annoyed { animation: shake .3s 2; }
.svg-sprite.dizzy   { animation: sway .6s ease-in-out infinite; }

@keyframes bob { 0%, 100% { transform: translateY(0) } 50% { transform: translateY(-4px) } }
@keyframes breathe { 0%, 100% { transform: scale(1, 1) } 50% { transform: scale(1.02, .98) } }
@keyframes bounce { 0%, 100% { transform: translateY(0) } 40% { transform: translateY(-10px) } }
@keyframes wiggle { 0%, 100% { transform: rotate(0) } 25% { transform: rotate(-6deg) } 75% { transform: rotate(6deg) } }
@keyframes purr { 0%, 100% { transform: scale(1, 1) } 50% { transform: scale(1.04, .96) } }
@keyframes shake { 0%, 100% { transform: translateX(0) } 25% { transform: translateX(-3px) } 75% { transform: translateX(3px) } }
@keyframes sway { 0%, 100% { transform: rotate(0) } 25% { transform: rotate(-8deg) } 75% { transform: rotate(8deg) } }

.spin-eye { animation: spinEye .6s linear infinite; transform-origin: center; }
@keyframes spinEye { 0% { transform: rotate(0deg) } 100% { transform: rotate(360deg) } }
</style>