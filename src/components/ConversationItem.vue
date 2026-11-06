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
          <span v-if="item.pinned" class="conv-pin-mark" title="已置顶"></span>
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
        >
          <AppIcon name="pin" :size="12" />
        </button>
        <button class="conv-action-btn" title="重命名" @click.stop="$emit('rename-start')">
          <AppIcon name="edit" :size="12" />
        </button>
        <button class="conv-action-btn del" title="删除" @click.stop="$emit('delete')">
          <AppIcon name="trash" :size="12" />
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

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
.conv-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out);
}

.conv-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

.conv-item.active {
  background: linear-gradient(90deg, rgba(239, 168, 76, 0.14), rgba(239, 168, 76, 0.02));
  box-shadow: inset 0 0 0 1px rgba(239, 168, 76, 0.13);
}

.conv-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  width: 2px;
  height: 14px;
  border-radius: 0 2px 2px 0;
  background: var(--amber-grad);
  transform: translateY(-50%);
  box-shadow: 0 0 8px rgba(239, 168, 76, 0.6);
}

.conv-item-main {
  flex: 1;
  min-width: 0;
}

.conv-title-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

/* 置顶用一个小圆点标记，比 📌 安静得多 */
.conv-pin-mark {
  width: 4px;
  height: 4px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--amber-400);
  box-shadow: 0 0 0 2px var(--amber-a12);
}

.conv-title {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color var(--dur-fast);
}

.conv-item:hover .conv-title {
  color: var(--text-1);
}

.conv-item.active .conv-title {
  color: var(--amber-200);
  font-weight: 500;
}

.conv-time {
  margin-top: 1px;
  font-size: 10px;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}

.conv-actions {
  display: none;
  flex-shrink: 0;
  gap: 1px;
}

.conv-item:hover .conv-actions {
  display: flex;
}

/* 置顶项常驻操作区：无需先 hover 才能发现 */
.conv-item.pinned .conv-actions {
  display: flex;
}

.conv-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--text-4);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}

.conv-action-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-1);
}

.conv-action-btn.pin.pinned {
  color: var(--amber-400);
}

.conv-action-btn.del:hover {
  color: var(--coral-400);
}

.conv-rename-input {
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  font-size: 12.5px;
  color: var(--text-1);
  background: var(--ink-1000);
  border: 1px solid var(--amber-a55);
  border-radius: var(--r-xs);
  outline: none;
  box-shadow: 0 0 0 2px var(--amber-a12);
}

/* 窄屏折叠侧栏：只留一个占位方块 */
@media (max-width: 900px) {
  .conv-item-main,
  .conv-actions {
    display: none !important;
  }
  .conv-item {
    justify-content: center;
    padding: 8px 0;
  }
  .conv-item::before {
    content: '';
    width: 14px;
    height: 14px;
    border-radius: 4px;
    background: var(--line-3);
  }
  .conv-item.active {
    box-shadow: none;
  }
  .conv-item.active::before {
    position: static;
    width: 14px;
    height: 14px;
    border-radius: 4px;
    background: var(--amber-grad);
    transform: none;
    box-shadow: none;
  }
}
</style>
