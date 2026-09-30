<template>
  <!-- 单条会话（侧栏「置顶」分组与历史列表共用同一行渲染，行为完全一致） -->
  <div class="conv-item" :class="{ active, pinned: item.pinned }" @click="$emit('select')">
    <template v-if="editing">
      <input
        ref="inputEl"
        :value="editingTitle"
        class="conv-rename-input"
        @input="$emit('update:editingTitle', $event.target.value)"
        @keydown.enter.prevent="$emit('rename-commit')"
        @keydown.esc="$emit('rename-cancel')"
        @blur="$emit('rename-commit')"
        @click.stop
      />
    </template>
    <template v-else>
      <div class="conv-item-main">
        <div class="conv-title-row">
          <span v-if="item.pinned" class="conv-pin-mark" title="已置顶">📌</span>
          <div class="conv-title">{{ item.title || '新对话' }}</div>
        </div>
        <div class="conv-time">{{ relTime(item.updatedAt) }}</div>
      </div>
      <div class="conv-actions">
        <button
          class="conv-action-btn pin"
          :class="{ pinned: item.pinned }"
          :title="item.pinned ? '取消置顶' : '置顶'"
          @click.stop="$emit('pin-toggle')"
        >📌</button>
        <button class="conv-action-btn" title="重命名" @click.stop="$emit('rename-start')">✎</button>
        <button class="conv-action-btn del" title="删除" @click.stop="$emit('delete')">🗑</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  item: { type: Object, required: true },
  active: { type: Boolean, default: false },
  editing: { type: Boolean, default: false },
  editingTitle: { type: String, default: '' },
})

defineEmits(['select', 'rename-start', 'rename-commit', 'rename-cancel', 'delete', 'pin-toggle', 'update:editingTitle'])

// 进入重命名态自动聚焦光标（每行各自持有 input 引用，不必由父组件按数组下标取）
const inputEl = ref(null)
watch(
  () => props.editing,
  (v) => {
    if (v) nextTick(() => inputEl.value?.focus())
  }
)

// 相对时间：与置顶状态无关，仅展示用
function relTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - ts
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d} 天前`
  return new Date(ts).toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.conv-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 8px; cursor: pointer; transition: background 0.15s; }
.conv-item:hover { background: #273449; }
.conv-item.active { background: #4f46e533; outline: 1px solid #6366f1; }
.conv-item-main { flex: 1; min-width: 0; }
.conv-title-row { display: flex; align-items: center; gap: 3px; min-width: 0; }
.conv-pin-mark { flex-shrink: 0; font-size: 10px; line-height: 1; }
.conv-title { font-size: 12.5px; color: #e2e8f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-time { font-size: 10px; color: #64748b; margin-top: 1px; }
.conv-actions { display: none; flex-shrink: 0; gap: 2px; }
.conv-item:hover .conv-actions { display: flex; }
/* 置顶项常驻操作区：📌 高亮，"取消置顶"无需先 hover 才能发现 */
.conv-item.pinned .conv-actions { display: flex; }
.conv-action-btn { border: none; background: transparent; color: #94a3b8; cursor: pointer; font-size: 12px; padding: 4px; border-radius: 4px; }
.conv-action-btn:hover { background: #334155; color: #e2e8f0; }
.conv-action-btn.pin { font-size: 11px; filter: grayscale(1); opacity: 0.75; }
.conv-action-btn.pin:hover { filter: none; opacity: 1; }
.conv-action-btn.pin.pinned { filter: none; opacity: 1; }
.conv-action-btn.del:hover { color: #f87171; }
.conv-rename-input { flex: 1; min-width: 0; background: #0f172a; border: 1px solid #6366f1; border-radius: 6px; color: #e2e8f0; padding: 4px 8px; font-size: 13px; font-family: inherit; }
.conv-rename-input:focus { outline: none; }
/* 窄屏折叠侧栏：只留图标 */
@media (max-width: 900px) {
  .conv-item-main, .conv-actions { display: none !important; }
  .conv-item::before { content: '💬'; font-size: 14px; }
  .conv-item.pinned::before { content: '📌'; }
}
</style>