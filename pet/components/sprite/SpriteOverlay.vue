<template>
  <!-- 运行时 overlay：? / z z z / 喵~ / ♥
       这些元素不属于角色本体动画，独立于渲染器（SVG 与 spritesheet 共用），
       spritesheet 模式下不丢失。坐标继承原 SVG 内文字位置（120x110 视口，1:1 映射为 px）。 -->
  <div class="sprite-overlay" aria-hidden="true">
    <span v-if="state === 'think'" class="ov ov-q">?</span>
    <span v-if="state === 'sleep'" class="ov ov-z">z z z</span>
    <span v-if="longPressing && mood !== 'purring'" class="ov ov-meow">喵~</span>
    <span v-if="mood === 'purring'" class="ov ov-heart">♥</span>
  </div>
</template>

<script setup>
defineProps({
  state: { type: String, default: 'idle' },
  mood: { type: String, default: '' },
  longPressing: { type: Boolean, default: false }
})
</script>

<style scoped>
.sprite-overlay { position: absolute; inset: 0; pointer-events: none; font-weight: 700; line-height: 1; }
.ov { position: absolute; animation: floatq 1.2s ease-in-out infinite; }
.ov-q   { left: 90px; top: 0;    font-size: 16px; color: #a5b4fc; }
.ov-z   { left: 86px; top: 4px;  font-size: 13px; color: #94a3b8; }
.ov-meow{ left: 50px; top: -2px; font-size: 10px; color: #fbbf24; }
.ov-heart { left: 88px; top: 16px; font-size: 10px; color: #f472b6; animation: floatHeart 1.4s ease-in-out infinite; }
@keyframes floatq { 0%, 100% { opacity: .5 } 50% { opacity: 1 } }
@keyframes floatHeart { 0%, 100% { opacity: .4; transform: translateY(0) } 50% { opacity: 1; transform: translateY(-4px) } }
</style>