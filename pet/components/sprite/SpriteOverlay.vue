<template>
  <!-- 运行时 overlay：? / z z z / ！/ 喵~ / ♥
       这些元素不属于角色本体动画，独立于渲染器（SVG 与 spritesheet 共用），
       坐标按 120×110 的角色视口 1:1 映射。 -->
  <div class="sprite-overlay" aria-hidden="true">
    <!-- 思考：一个小气泡 + ? -->
    <div v-if="state === 'think'" class="ov-think">
      <span class="think-bubble">?</span>
      <i class="dot dot-1"></i><i class="dot dot-2"></i>
    </div>

    <!-- 睡觉：大小渐变的 Z z z -->
    <div v-if="state === 'sleep'" class="ov-sleep">
      <span class="z z-1">Z</span>
      <span class="z z-2">z</span>
      <span class="z z-3">z</span>
    </div>

    <!-- 提醒：琥珀色感叹号 -->
    <div v-if="state === 'remind'" class="ov-remind">!</div>

    <!-- 翻跟斗：落地时的小星星 -->
    <div v-if="trick === 'flip'" class="ov-sparkles">
      <span class="spark s-1">✦</span>
      <span class="spark s-2">✧</span>
      <span class="spark s-3">✦</span>
    </div>

    <!-- 长按撸猫 -->
    <div v-if="longPressing && mood !== 'purring'" class="ov-meow">喵~</div>

    <!-- 呼噜：三颗心往上飘 -->
    <div v-if="mood === 'purring'" class="ov-hearts">
      <span class="heart h-1">♥</span>
      <span class="heart h-2">♥</span>
      <span class="heart h-3">♥</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  state: { type: String, default: 'idle' },
  mood: { type: String, default: '' },
  longPressing: { type: Boolean, default: false },
  trick: { type: String, default: '' },
})
</script>

<style scoped>
.sprite-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  font-weight: 700;
  line-height: 1;
  font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
}

/* ---- 思考 ---- */
.ov-think { position: absolute; right: 9px; top: 2px; }
.think-bubble {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(16, 19, 26, 0.82);
  border: 1px solid rgba(239, 168, 76, 0.45);
  color: #F3BE73;
  font-size: 13px;
  box-shadow: 0 4px 12px -4px rgba(0, 0, 0, 0.7);
  animation: think-float 1.6s ease-in-out infinite;
}
.ov-think .dot {
  position: absolute;
  right: 20px;
  bottom: -5px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(239, 168, 76, 0.55);
}
.ov-think .dot-2 { right: 15px; bottom: -10px; width: 3px; height: 3px; opacity: 0.6; }

/* ---- 睡觉 ---- */
.ov-sleep { position: absolute; right: 8px; top: 6px; display: flex; flex-direction: column; align-items: flex-end; }
.z {
  color: #EAD3AC;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  animation: z-float 2.6s ease-in-out infinite;
}
.z-1 { font-size: 15px; }
.z-2 { font-size: 12px; opacity: 0.75; animation-delay: 0.45s; margin-right: 5px; }
.z-3 { font-size: 10px; opacity: 0.5; animation-delay: 0.9s; margin-right: 9px; }

/* ---- 提醒 ---- */
.ov-remind {
  position: absolute;
  right: 10px;
  top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(160deg, #F3BE73, #E08F33);
  color: #2A1A07;
  font-size: 13px;
  box-shadow: 0 4px 12px -4px rgba(239, 168, 76, 0.8);
  animation: remind-pop 0.9s ease-in-out infinite;
}

/* ---- 喵~ ---- */
.ov-meow {
  position: absolute;
  left: 46px;
  top: -4px;
  font-size: 11px;
  color: #F3BE73;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
  animation: meow-float 1.1s ease-in-out infinite;
}

/* ---- 翻跟斗星星 ---- */
.ov-sparkles { position: absolute; inset: 0; }
.spark {
  position: absolute;
  color: #F3BE73;
  text-shadow: 0 0 8px rgba(239, 168, 76, 0.65);
  animation: spark-pop 1s ease-out forwards;
}
.s-1 { left: 14px; top: 46px; font-size: 15px; }
.s-2 { right: 10px; top: 34px; font-size: 12px; animation-delay: 0.12s; }
.s-3 { right: 22px; bottom: 18px; font-size: 10px; animation-delay: 0.22s; }

@keyframes spark-pop {
  0% { opacity: 0; transform: scale(0.4) translateY(6px); }
  35% { opacity: 1; transform: scale(1.15) translateY(0); }
  100% { opacity: 0; transform: scale(0.8) translateY(-8px); }
}

/* ---- 爱心 ---- */.ov-hearts { position: absolute; right: 6px; top: 8px; }
.heart {
  position: absolute;
  right: 0;
  color: #EF8A9B;
  text-shadow: 0 0 6px rgba(239, 138, 155, 0.5);
  animation: heart-float 1.8s ease-in-out infinite;
}
.h-1 { font-size: 12px; }
.h-2 { font-size: 9px; right: 12px; top: 6px; animation-delay: 0.35s; opacity: 0.85; }
.h-3 { font-size: 8px; right: 20px; top: 12px; animation-delay: 0.7s; opacity: 0.7; }

@keyframes think-float { 0%, 100% { transform: translateY(0); opacity: 0.75; } 50% { transform: translateY(-3px); opacity: 1; } }
@keyframes z-float { 0% { transform: translateY(2px); opacity: 0; } 30% { opacity: 1; } 100% { transform: translateY(-9px); opacity: 0; } }
@keyframes remind-pop { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.12); } }
@keyframes meow-float { 0%, 100% { transform: translateY(0); opacity: 0.7; } 50% { transform: translateY(-3px); opacity: 1; } }
@keyframes heart-float { 0%, 100% { transform: translateY(0) scale(1); opacity: 0.45; } 50% { transform: translateY(-6px) scale(1.1); opacity: 1; } }

@media (prefers-reduced-motion: reduce) {
  .think-bubble, .z, .ov-remind, .ov-meow, .heart { animation: none !important; }
}
</style>
