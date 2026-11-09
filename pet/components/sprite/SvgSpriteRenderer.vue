<template>
  <svg
    class="cat-sprite"
    :class="[animClass, { hovered, 'is-sleeping': state === 'sleep' }]"
    viewBox="0 0 120 110"
    width="120"
    height="110"
    overflow="visible"
  >
    <defs>
      <!-- 毛色：深墨蓝灰，顶部受光、底部沉下去 -->
      <linearGradient id="cat-fur" x1="0" y1="0" x2="0.35" y2="1">
        <stop offset="0" stop-color="#4B556C" />
        <stop offset="0.55" stop-color="#3A4356" />
        <stop offset="1" stop-color="#2A3141" />
      </linearGradient>
      <radialGradient id="cat-head" cx="0.38" cy="0.28" r="0.85">
        <stop offset="0" stop-color="#515C74" />
        <stop offset="0.62" stop-color="#3B4457" />
        <stop offset="1" stop-color="#2B3242" />
      </radialGradient>
      <linearGradient id="cat-tail" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#3D465A" />
        <stop offset="1" stop-color="#262C3A" />
      </linearGradient>
      <linearGradient id="cat-cream" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#FBF0DA" />
        <stop offset="1" stop-color="#EAD3AC" />
      </linearGradient>
      <linearGradient id="cat-ear" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#F3B5A6" />
        <stop offset="1" stop-color="#D98C7C" />
      </linearGradient>
      <filter id="cat-shadow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2.2" />
      </filter>
    </defs>

    <!-- 地面投影：让猫"落"在桌面上，而不是浮着 -->
    <ellipse class="ground-shadow" cx="60" cy="103" rx="33" ry="5" fill="#000" opacity="0.22" filter="url(#cat-shadow)" />

    <!-- 尾巴：在身体后方，随帧轻摆 -->
    <path
      class="tail"
      :d="tailPath"
      fill="none"
      stroke="url(#cat-tail)"
      stroke-width="8.5"
      stroke-linecap="round"
    />
    <circle class="tail-tip" :cx="tailTip.x" :cy="tailTip.y" r="4.6" fill="#F3E3C4" />

    <!-- 身体 + 四肢 -->
    <g class="body-group">
      <path
        d="M60 58
           C43 58 32 70 31 83
           C30 95 42 100 60 100
           C78 100 90 95 89 83
           C88 70 77 58 60 58 Z"
        fill="url(#cat-fur)"
      />
      <!-- 胸腹浅色绒毛 -->
      <path
        d="M60 66
           C51 66 46 74 46 84
           C46 92 52 96 60 96
           C68 96 74 92 74 84
           C74 74 69 66 60 66 Z"
        fill="url(#cat-cream)"
        opacity="0.95"
      />
      <!-- 后爪 -->
      <ellipse cx="41" cy="97" rx="9" ry="4.6" fill="#2E3545" />
      <ellipse cx="79" cy="97" rx="9" ry="4.6" fill="#2E3545" />
      <!-- 前爪（groom 时右爪会抬起来） -->
      <g class="paw paw-left">
        <ellipse cx="52" cy="94" rx="7" ry="5" fill="#F7EBD4" />
        <path d="M49 94 v2 M52 93.5 v2.6 M55 94 v2" stroke="#D9C39A" stroke-width="1" stroke-linecap="round" />
      </g>
      <g class="paw paw-right">
        <ellipse cx="68" cy="94" rx="7" ry="5" fill="#F7EBD4" />
        <path d="M65 94 v2 M68 93.5 v2.6 M71 94 v2" stroke="#D9C39A" stroke-width="1" stroke-linecap="round" />
      </g>
    </g>

    <!-- 头部 -->
    <g class="head-group">
      <!-- 耳朵 -->
      <g class="ear ear-left">
        <path d="M38 34 L40.5 12 L57 27 Z" fill="url(#cat-fur)" stroke="#232937" stroke-width="1.4" stroke-linejoin="round" />
        <path d="M42 29 L43.6 17.5 L52 27.5 Z" fill="url(#cat-ear)" />
      </g>
      <g class="ear ear-right">
        <path d="M82 34 L79.5 12 L63 27 Z" fill="url(#cat-fur)" stroke="#232937" stroke-width="1.4" stroke-linejoin="round" />
        <path d="M78 29 L76.4 17.5 L68 27.5 Z" fill="url(#cat-ear)" />
      </g>

      <!-- 头型：比正圆更自然一点，两侧带腮毛 -->
      <path
        d="M60 22
           C74 22 84 33 84 47
           C84 61 74 72 60 72
           C46 72 36 61 36 47
           C36 33 46 22 60 22 Z"
        fill="url(#cat-head)"
      />
      <path d="M36 48 l-5 -2 l3.6 5.4 Z M84 48 l5 -2 l-3.6 5.4 Z" fill="#394254" />

      <!-- 额头虎斑 -->
      <path d="M53 27 q3 4 1.5 8 M60 25.5 v8 M67 27 q-3 4 -1.5 8" stroke="#596480" stroke-width="2.4" stroke-linecap="round" opacity="0.75" />

      <!-- 口鼻浅色区 -->
      <ellipse cx="60" cy="57" rx="14" ry="9.2" fill="url(#cat-cream)" opacity="0.97" />
      <path d="M57.4 54.2 h5.2 l-2.6 2.8 Z" fill="#C97C6A" />
      <path d="M60 57 v2" stroke="#8A5A48" stroke-width="1.2" stroke-linecap="round" />

      <!-- 胡须 -->
      <path d="M44 52 l-11 -2 M44 56 l-11 2 M76 52 l11 -2 M76 56 l11 2"
            stroke="#C9D2E2" stroke-width="1.1" stroke-linecap="round" opacity="0.55" />

      <!-- ===== 表情 ===== -->
      <!-- 开心 / 呼噜：眯眼笑 + 腮红 -->
      <template v-if="mood === 'happy' || mood === 'purring'">
        <path d="M45 46 q5 -5 10 0" stroke="#1B2029" stroke-width="3" fill="none" stroke-linecap="round" />
        <path d="M65 46 q5 -5 10 0" stroke="#1B2029" stroke-width="3" fill="none" stroke-linecap="round" />
        <ellipse cx="42" cy="53" rx="4.2" ry="2.4" fill="#E48C86" opacity="0.55" />
        <ellipse cx="78" cy="53" rx="4.2" ry="2.4" fill="#E48C86" opacity="0.55" />
        <path d="M55 58 q5 4.5 10 0" stroke="#6B4030" stroke-width="2.2" fill="none" stroke-linecap="round" />
      </template>

      <!-- 不满：半眯眼 + 压低的耳朵（由 CSS 处理）+ 撇嘴 -->
      <template v-else-if="mood === 'annoyed'">
        <path d="M45 43 l10 2.4" stroke="#1B2029" stroke-width="2.6" stroke-linecap="round" />
        <path d="M75 43 l-10 2.4" stroke="#1B2029" stroke-width="2.6" stroke-linecap="round" />
        <ellipse cx="50" cy="48" rx="3.6" ry="3" fill="#1B2029" />
        <ellipse cx="70" cy="48" rx="3.6" ry="3" fill="#1B2029" />
        <circle cx="51" cy="47" r="1.1" fill="#fff" opacity="0.8" />
        <circle cx="71" cy="47" r="1.1" fill="#fff" opacity="0.8" />
        <path d="M56 60 q4 -2 8 0" stroke="#6B4030" stroke-width="2.2" fill="none" stroke-linecap="round" />
      </template>

      <!-- 头晕：蚊香眼 -->
      <template v-else-if="mood === 'dizzy'">
        <g class="spin-eye" style="transform-origin: 50px 46px">
          <path d="M46 46 a4 4 0 1 1 4 4 a2.4 2.4 0 1 0 2.4 -2.4" stroke="#1B2029" stroke-width="1.8" fill="none" stroke-linecap="round" />
        </g>
        <g class="spin-eye" style="transform-origin: 70px 46px">
          <path d="M66 46 a4 4 0 1 1 4 4 a2.4 2.4 0 1 0 2.4 -2.4" stroke="#1B2029" stroke-width="1.8" fill="none" stroke-linecap="round" />
        </g>
        <path d="M55 60 q5 3 10 0" stroke="#6B4030" stroke-width="2" fill="none" stroke-linecap="round" />
      </template>

      <!-- 睡眠 / 眨眼 -->
      <template v-else-if="eyesClosed">
        <path d="M46 46 q4 4 9 0" stroke="#1B2029" stroke-width="2.8" fill="none" stroke-linecap="round" />
        <path d="M65 46 q4 4 9 0" stroke="#1B2029" stroke-width="2.8" fill="none" stroke-linecap="round" />
        <path d="M56 58 q4 3 8 0" stroke="#6B4030" stroke-width="2.2" fill="none" stroke-linecap="round" />
      </template>

      <!-- 默认：琥珀色大眼睛（瞳孔随 look 动作偏移） -->
      <template v-else>
        <g class="pupils">
          <ellipse cx="50" cy="46" rx="6.4" ry="7" fill="#F6EFE2" />
          <ellipse cx="70" cy="46" rx="6.4" ry="7" fill="#F6EFE2" />
          <circle cx="50.6" cy="46.4" r="4.6" fill="#E9A94F" />
          <circle cx="69.4" cy="46.4" r="4.6" fill="#E9A94F" />
          <ellipse cx="50.6" cy="46.4" rx="2.1" ry="3.2" fill="#161A22" />
          <ellipse cx="69.4" cy="46.4" rx="2.1" ry="3.2" fill="#161A22" />
          <circle cx="48.8" cy="44" r="1.5" fill="#FFFFFF" />
          <circle cx="67.6" cy="44" r="1.5" fill="#FFFFFF" />
          <circle cx="52.4" cy="48.6" r="0.8" fill="#FFFFFF" opacity="0.7" />
          <circle cx="71.2" cy="48.6" r="0.8" fill="#FFFFFF" opacity="0.7" />
        </g>
      </template>

      <!-- 嘴：说话时张开，打哈欠时更大 -->
      <template v-if="state === 'talk' && !hasMoodExpr">
        <ellipse class="talking-mouth" cx="60" cy="60" rx="3.4" ry="3.8" fill="#8E4A42" />
      </template>
      <template v-else-if="action === 'yawn' && !hasMoodExpr">
        <ellipse cx="60" cy="61" rx="5" ry="6" fill="#8E4A42" />
        <ellipse cx="60" cy="63" rx="3" ry="2.4" fill="#E48C86" opacity="0.8" />
      </template>
      <template v-else-if="!hasMoodExpr">
        <path d="M56 58 q4 3.2 8 0" stroke="#6B4030" stroke-width="2.2" fill="none" stroke-linecap="round" />
      </template>

      <!-- 项圈 + 小铃铛（品牌琥珀色） -->
      <path d="M43 66 q17 7 34 0" stroke="#7A4A22" stroke-width="3.2" fill="none" stroke-linecap="round" opacity="0.9" />
      <circle cx="60" cy="72.5" r="3.4" fill="#EFA84C" stroke="#A96A25" stroke-width="1" />
      <path d="M59 72 h2" stroke="#8A5418" stroke-width="1" stroke-linecap="round" />
    </g>
  </svg>
</template>

<script setup>
// 品牌猫 SVG：深墨毛色 + 琥珀眼 + 月光色胸腹，配合「墨夜·琥珀」主界面。
// 帧时钟仍内聚在渲染器内（220ms/帧），用于眨眼与尾巴摆动；
// 状态/心情动画走 CSS 类，避免与 SVG 形状计算耦合。
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  state: { type: String, default: 'idle' },
  mood: { type: String, default: '' },
  facingLeft: { type: Boolean, default: false },
  hovered: { type: Boolean, default: false },
  action: { type: String, default: '' },
})
defineEmits(['complete'])

const frameIdx = ref(0)
let rafId = null
let firstT = null
function tick(t) {
  rafId = requestAnimationFrame(tick)
  if (firstT === null) firstT = t
  frameIdx.value = Math.floor((t - firstT) / 220)
}

const hasMoodExpr = computed(() =>
  props.mood === 'happy' || props.mood === 'annoyed' || props.mood === 'dizzy' || props.mood === 'purring'
)
const animClass = computed(() => [
  props.state,
  props.action,
  {
    happy: props.mood === 'happy',
    annoyed: props.mood === 'annoyed',
    dizzy: props.mood === 'dizzy',
    purring: props.mood === 'purring',
  },
])

// 尾巴：基点在身体右后侧，末端随帧摆动；睡眠时几乎不动
const tailSway = computed(() => {
  const speed = props.state === 'sleep' ? 0.18 : props.hovered ? 1.35 : 0.9
  const amount = props.state === 'sleep' ? 3 : props.state === 'drag' ? 6 : 10
  return Math.sin(frameIdx.value * speed) * amount
})
const tailTip = computed(() => ({ x: 101 + tailSway.value * 0.65, y: 56 - tailSway.value * 0.35 }))
const tailPath = computed(() => {
  const s = tailSway.value
  return `M87 86 C99 88 ${104 + s * 0.5} ${76 - s * 0.25} ${101 + s * 0.65} ${56 - s * 0.35}`
})

const eyesClosed = computed(() => {
  if (props.state === 'sleep') return true
  // 眨眼：每 ~2.2s 闭一次，持续一帧
  return frameIdx.value % 10 === 8
})

defineExpose({
  play: () => { firstT = null; if (!rafId) rafId = requestAnimationFrame(tick) },
  pause: () => { cancelAnimationFrame(rafId); rafId = null },
  resume: () => { firstT = null; if (!rafId) rafId = requestAnimationFrame(tick) },
  getCurrentFrame: () => frameIdx.value,
})

onMounted(() => { rafId = requestAnimationFrame(tick) })
onBeforeUnmount(() => { cancelAnimationFrame(rafId); rafId = null })
</script>

<style scoped>
/* ===== 状态动画 ===== */
.cat-sprite {
  transition: transform 0.25s cubic-bezier(0.22, 0.61, 0.36, 1);
  transform-origin: 50% 88%;
}
.cat-sprite.idle   { animation: cat-breathe 2.8s ease-in-out infinite; }
.cat-sprite.walk   { animation: cat-bob 0.42s infinite; }
.cat-sprite.react  { animation: cat-bounce 0.32s 2; }
.cat-sprite.remind { animation: cat-wiggle 0.38s 4; }
.cat-sprite.talk   { animation: cat-bob 0.3s infinite; }
.cat-sprite.think  { animation: cat-breathe 1.7s ease-in-out infinite; }
.cat-sprite.sleep  { animation: cat-sleep 4.4s ease-in-out infinite; }
.cat-sprite.happy,
.cat-sprite.purring { animation: cat-purr 0.5s ease-in-out infinite; }
.cat-sprite.annoyed { animation: cat-shake 0.3s 2; }
.cat-sprite.dizzy   { animation: cat-sway 0.62s ease-in-out infinite; }

/* 悬停：轻轻放大 + 抬头感（由内联 transform 覆写呼吸动画不合适，
   这里用 scale 变量叠加在动画之外，靠 filter/亮度体现"注意到你"） */
.cat-sprite.hovered { filter: brightness(1.06) drop-shadow(0 0 6px rgba(239, 168, 76, 0.28)); }
.cat-sprite.hovered .tail { filter: drop-shadow(0 0 2px rgba(239, 168, 76, 0.25)); }

/* 耳朵以"耳根"为轴旋转，而不是按包围盒中心：
   否则压耳/竖耳时耳根会离开头顶，看起来像耳朵掉了 */
.ear { transition: transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1); }
.ear-left  { transform-origin: 46px 34px; }
.ear-right { transform-origin: 74px 34px; }
.cat-sprite.hovered .ear-left  { transform: rotate(-5deg) translateY(-1px); }
.cat-sprite.hovered .ear-right { transform: rotate(5deg) translateY(-1px); }
.cat-sprite.annoyed .ear-left  { transform: rotate(-20deg) translateY(1px); }
.cat-sprite.annoyed .ear-right { transform: rotate(20deg) translateY(1px); }
.cat-sprite.sleep .ear-left    { transform: rotate(-12deg) translateY(2px); }
.cat-sprite.sleep .ear-right   { transform: rotate(12deg) translateY(2px); }

/* ===== 微动作（idle 时随机触发） ===== */
.cat-sprite.stretch { animation: cat-stretch 1.5s ease-in-out; }
.cat-sprite.groom   { animation: cat-groom 1.6s ease-in-out; }
.cat-sprite.look    { animation: cat-look 1.8s ease-in-out; }
.cat-sprite.yawn    { animation: cat-yawn 1.8s ease-in-out; }

.cat-sprite.groom .paw-right { animation: paw-groom 1.6s ease-in-out; transform-origin: 68px 94px; }
.cat-sprite.stretch .paw-left,
.cat-sprite.stretch .paw-right { animation: paw-stretch 1.5s ease-in-out; }

.cat-sprite.look .pupils { animation: look-around 1.8s ease-in-out; }
.cat-sprite.yawn .talking-mouth { animation: yawn-mouth 1.8s ease-in-out; }

/* 说话时嘴部轻动 */
.cat-sprite.talk .talking-mouth { animation: talk-mouth 0.36s ease-in-out infinite; }

/* 拖拽：四肢自然下垂 */
.cat-sprite.drag .paw-left  { animation: dangle 0.9s ease-in-out infinite; }
.cat-sprite.drag .paw-right { animation: dangle 0.9s ease-in-out infinite reverse; }
.cat-sprite.drag .tail      { animation: tail-dangle 1s ease-in-out infinite; transform-origin: 87px 86px; }

.spin-eye { animation: spin-eye 0.7s linear infinite; }

@keyframes cat-breathe { 0%, 100% { transform: scale(1, 1); } 50% { transform: scale(1.015, 0.985); } }
@keyframes cat-sleep   { 0%, 100% { transform: scale(1, 1) translateY(0); } 50% { transform: scale(1.02, 0.975) translateY(1px); } }
@keyframes cat-bob     { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3.5px); } }
@keyframes cat-bounce  { 0%, 100% { transform: translateY(0); } 40% { transform: translateY(-9px); } }
@keyframes cat-wiggle  { 0%, 100% { transform: rotate(0); } 25% { transform: rotate(-5deg); } 75% { transform: rotate(5deg); } }
@keyframes cat-purr    { 0%, 100% { transform: scale(1, 1); } 50% { transform: scale(1.035, 0.97); } }
@keyframes cat-shake   { 0%, 100% { transform: translateX(0); } 25% { transform: translateX(-3px); } 75% { transform: translateX(3px); } }
@keyframes cat-sway    { 0%, 100% { transform: rotate(0); } 25% { transform: rotate(-7deg); } 75% { transform: rotate(7deg); } }

@keyframes cat-stretch { 0%, 100% { transform: scale(1, 1); } 30% { transform: scale(1.08, 0.9) translateY(2px); } 65% { transform: scale(0.97, 1.03); } }
@keyframes cat-groom   { 0%, 100% { transform: rotate(0); } 25% { transform: rotate(-6deg) translateY(-1px); } 60% { transform: rotate(4deg); } }
@keyframes cat-look    { 0%, 100% { transform: rotate(0); } 30% { transform: rotate(-4deg); } 70% { transform: rotate(4deg); } }
@keyframes cat-yawn    { 0%, 100% { transform: scale(1, 1); } 40% { transform: scale(1.03, 1.04) translateY(-1px); } }
@keyframes paw-groom   { 0%, 100% { transform: translate(0, 0); } 30%, 70% { transform: translate(-2px, -12px) rotate(-16deg); } }
@keyframes paw-stretch { 0%, 100% { transform: translateX(0); } 40% { transform: translateX(-4px); } }
@keyframes dangle      { 0%, 100% { transform: translateY(0) rotate(0); } 50% { transform: translateY(2.5px) rotate(-4deg); } }
@keyframes tail-dangle { 0%, 100% { transform: rotate(0); } 50% { transform: rotate(-6deg); } }
@keyframes look-around { 0%, 100% { transform: translateX(0); } 25% { transform: translateX(-2.2px); } 60% { transform: translateX(2.2px); } }
@keyframes talk-mouth  { 0%, 100% { ry: 3.8px; } 50% { ry: 2.2px; } }
@keyframes yawn-mouth  { 0%, 100% { rx: 3.4px; ry: 3.8px; } 45% { rx: 5px; ry: 6px; } }
@keyframes spin-eye    { 0% { transform: rotate(0); } 100% { transform: rotate(360deg); } }

/* 系统降低动效时：只保留呼吸，关闭位移类动画 */
@media (prefers-reduced-motion: reduce) {
  .cat-sprite, .cat-sprite * { animation: none !important; }
  .cat-sprite { transition: none; }
}
</style>
