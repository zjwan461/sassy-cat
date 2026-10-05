<template>
  <!-- 统一入口：按响应式 currentRenderer 动态选择渲染器 -->
  <component
    :is="rendererComponent"
    ref="renderer"
    :state="state"
    :mood="mood"
    :facing-left="facingLeft"
    @complete="$emit('complete')"
  />
</template>

<script setup>
import { computed, ref } from 'vue'
import SvgSpriteRenderer from './SvgSpriteRenderer.vue'
import SpritesheetRenderer from './SpritesheetRenderer.vue'
import { currentRenderer, RENDERER_SPRITESHEET } from './config'

defineProps({
  state: { type: String, default: 'idle' },
  mood: { type: String, default: '' },
  facingLeft: { type: Boolean, default: false }
})
defineEmits(['complete'])

const rendererComponent = computed(() =>
  currentRenderer.value === RENDERER_SPRITESHEET ? SpritesheetRenderer : SvgSpriteRenderer
)
const renderer = ref(null)

// 播放控制透传（状态切换一律走 props，不走命令式）
defineExpose({
  play: () => renderer.value?.play(),
  pause: () => renderer.value?.pause(),
  resume: () => renderer.value?.resume(),
  getCurrentFrame: () => renderer.value?.getCurrentFrame?.()
})
</script>