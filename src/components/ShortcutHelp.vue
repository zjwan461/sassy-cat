<template>
  <Teleport to="body">
    <Transition name="sk">
      <div v-if="open" class="sk-overlay" @click.self="close">
        <div class="sk-panel" role="dialog" aria-modal="true" aria-label="快捷键">
          <div class="sk-head">
            <div>
              <div class="sk-title">快捷键</div>
              <div class="sk-sub">常用操作速查</div>
            </div>
            <button class="sk-close" type="button" title="关闭" @click="close">
              <AppIcon name="x" :size="14" />
            </button>
          </div>

          <div class="sk-body">
            <section v-for="group in groups" :key="group.title" class="sk-group">
              <div class="sk-group-title">{{ group.title }}</div>
              <div v-for="row in group.rows" :key="row.label" class="sk-row">
                <span class="sk-label">{{ row.label }}</span>
                <span class="sk-keys">
                  <kbd v-for="k in row.keys" :key="k">{{ k }}</kbd>
                </span>
              </div>
            </section>
          </div>

          <div class="sk-foot">按 <kbd>Esc</kbd> 关闭 · 再次按 <kbd>Ctrl</kbd><kbd>/</kbd> 也可关闭</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import AppIcon from './AppIcon.vue'

defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['close'])

const groups = [
  {
    title: '全局',
    rows: [
      { label: '搜索页面、操作或对话', keys: ['Ctrl', 'K'] },
      { label: '收起 / 展开侧栏', keys: ['Ctrl', 'B'] },
      { label: '打开快捷键帮助', keys: ['Ctrl', '/'] },
      { label: '关闭当前面板', keys: ['Esc'] },
    ],
  },
  {
    title: '聊天',
    rows: [
      { label: '在当前会话中搜索', keys: ['Ctrl', 'F'] },
      { label: '发送消息', keys: ['Enter'] },
      { label: '换行', keys: ['Shift', 'Enter'] },
      { label: '停止生成', keys: ['Esc'] },
    ],
  },
  {
    title: '桌面',
    rows: [
      { label: '快速提问（桌宠）', keys: ['Alt', 'Shift', 'Q'] },
      { label: '点击文件卡片', keys: ['系统默认程序打开'] },
    ],
  },
]

function close() {
  emit('close')
}
</script>

<style scoped>
.sk-overlay {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(4, 7, 12, 0.66);
  backdrop-filter: blur(9px) saturate(120%);
  -webkit-backdrop-filter: blur(9px) saturate(120%);
}

.sk-panel {
  width: min(540px, calc(100vw - 48px));
  max-height: min(640px, 82vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, #121721 0%, #0D1118 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  box-shadow: 0 30px 80px -20px rgba(0, 0, 0, 0.85), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.sk-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 15px 16px 12px;
  border-bottom: 1px solid var(--line-1);
}

.sk-title {
  color: var(--text-1);
  font-size: 14px;
  font-weight: 700;
}

.sk-sub {
  margin-top: 3px;
  color: var(--text-4);
  font-size: 10.5px;
}

.sk-close {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-3);
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: 6px;
  cursor: pointer;
}

.sk-close:hover { color: var(--text-1); background: rgba(255, 255, 255, 0.05); }

.sk-body {
  overflow-y: auto;
  padding: 6px 16px 10px;
}

.sk-group + .sk-group { margin-top: 6px; }

.sk-group-title {
  padding: 12px 0 5px;
  color: var(--text-4);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.sk-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.sk-row:last-child { border-bottom: none; }

.sk-label {
  color: var(--text-2);
  font-size: 12.5px;
}

.sk-keys {
  display: inline-flex;
  gap: 4px;
  flex-shrink: 0;
}

kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 21px;
  padding: 0 6px;
  color: var(--text-3);
  font-family: inherit;
  font-size: 10.5px;
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid var(--line-2);
  border-bottom-color: rgba(255, 255, 255, 0.16);
  border-radius: 5px;
}

.sk-foot {
  padding: 9px 16px;
  color: var(--text-4);
  font-size: 10.5px;
  border-top: 1px solid var(--line-1);
  background: rgba(0, 0, 0, 0.18);
}

.sk-foot kbd { margin: 0 3px; }

.sk-enter-active,
.sk-leave-active { transition: opacity 0.15s ease; }
.sk-enter-active .sk-panel,
.sk-leave-active .sk-panel { transition: transform 0.15s ease, opacity 0.15s ease; }
.sk-enter-from,
.sk-leave-to { opacity: 0; }
.sk-enter-from .sk-panel,
.sk-leave-to .sk-panel { opacity: 0; transform: translateY(-6px) scale(0.99); }
</style>
