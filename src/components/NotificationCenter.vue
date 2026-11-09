<template>
  <div ref="rootEl" class="nc-wrap">
    <button
      class="nc-bell"
      type="button"
      :title="unreadCount ? `通知中心（${unreadCount} 条未读）` : '通知中心'"
      aria-label="通知中心"
      @click.stop="toggle"
    >
      <AppIcon name="bell" :size="15" />
      <span v-if="unreadCount" class="nc-badge">{{ unreadBadge }}</span>
    </button>

    <Transition name="nc-pop">
      <div v-if="panelOpen" class="nc-panel" @click.stop>
        <div class="nc-head">
          <div class="nc-head-title">
            <span>通知</span>
            <span v-if="items.length" class="nc-count">{{ items.length }}</span>
          </div>
          <button v-if="items.length" class="nc-clear" type="button" @click="clearNotifications">清除全部</button>
        </div>

        <div v-if="!items.length" class="nc-empty">
          <span class="nc-empty-icon"><AppIcon name="bell" :size="18" /></span>
          <p>暂时没有通知</p>
          <span>提醒、索引重建和文档入库结果会出现在这里</span>
        </div>

        <div v-else class="nc-list">
          <button
            v-for="n in items"
            :key="n.id"
            type="button"
            class="nc-item"
            :class="{ unread: !n.read }"
            @click="openItem(n)"
          >
            <span class="nc-icon" :class="'k-' + n.kind">
              <AppIcon :name="iconFor(n.kind)" :size="14" />
            </span>
            <span class="nc-main">
              <span class="nc-title">{{ n.title }}</span>
              <span v-if="n.body" class="nc-body" :title="n.body">{{ n.body }}</span>
              <span class="nc-time">{{ timeText(n.ts) }}</span>
            </span>
            <span v-if="n.action" class="nc-action">{{ n.actionLabel || '查看' }}</span>
          </button>
        </div>

        <div v-if="items.length" class="nc-foot">
          <span>仅保留本次运行的最近 80 条通知</span>
          <button type="button" class="nc-foot-btn" @click="close">收起</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import {
  clearNotifications, items, panelOpen, removeNotification, togglePanel, unreadBadge, unreadCount,
} from '../composables/useNotifications'

const router = useRouter()
const rootEl = ref(null)

const ICONS = { reminder: 'bell', success: 'check', error: 'alert', info: 'info' }
function iconFor(kind) {
  return ICONS[kind] || 'info'
}

function toggle() {
  togglePanel()
}

function close() {
  togglePanel(false)
}

function openItem(n) {
  if (n.action) router.push(n.action)
  removeNotification(n.id)
  close()
}

function timeText(ts) {
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function onDocMouseDown(e) {
  if (!panelOpen.value) return
  if (rootEl.value && !rootEl.value.contains(e.target)) close()
}

function onDocKeydown(e) {
  if (e.key === 'Escape' && panelOpen.value) close()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocMouseDown)
  document.addEventListener('keydown', onDocKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
  document.removeEventListener('keydown', onDocKeydown)
})
</script>

<style scoped>
.nc-wrap {
  position: relative;
  -webkit-app-region: no-drag;
  display: flex;
  align-items: center;
}

.nc-bell {
  position: relative;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-3);
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast);
}

.nc-bell:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.06);
}

.nc-badge {
  position: absolute;
  top: 3px;
  right: 1px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #2A1A07;
  font-size: 9px;
  font-weight: 700;
  background: var(--amber-400);
  border-radius: 999px;
  box-shadow: 0 0 0 2px #0B0E14;
}

.nc-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 200;
  width: 356px;
  max-height: min(460px, 72vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, #121721 0%, #0D1118 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  box-shadow: 0 24px 60px -18px rgba(0, 0, 0, 0.85), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.nc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 13px;
  border-bottom: 1px solid var(--line-1);
}

.nc-head-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-1);
  font-size: 12.5px;
  font-weight: 600;
}

.nc-count {
  padding: 1px 6px;
  color: var(--text-3);
  font-size: 10px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 999px;
}

.nc-clear {
  padding: 0;
  color: var(--text-4);
  font-size: 11px;
  background: none;
  border: none;
  cursor: pointer;
}

.nc-clear:hover { color: var(--amber-300); }

.nc-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 5px;
}

.nc-item {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 9px;
  text-align: left;
  font-family: inherit;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
}

.nc-item:hover {
  background: rgba(255, 255, 255, 0.035);
  border-color: var(--line-1);
}

.nc-item.unread { background: rgba(239, 168, 76, 0.045); }

.nc-icon {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.05);
}

.nc-icon.k-reminder { color: var(--amber-300); background: var(--amber-a12); }
.nc-icon.k-success { color: #8FD3B6; background: rgba(143, 211, 182, 0.1); }
.nc-icon.k-error { color: var(--coral-400); background: var(--coral-a12); }

.nc-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nc-title {
  color: var(--text-1);
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nc-body {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-3);
  font-size: 11px;
  line-height: 1.5;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.nc-time {
  color: var(--text-4);
  font-size: 10px;
}

.nc-action {
  flex-shrink: 0;
  align-self: center;
  color: var(--amber-300);
  font-size: 10.5px;
}

.nc-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 38px 20px 42px;
  color: var(--text-4);
  text-align: center;
}

.nc-empty-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.04);
  border-radius: 10px;
}

.nc-empty p {
  margin: 4px 0 0;
  color: var(--text-2);
  font-size: 12.5px;
}

.nc-empty span { font-size: 10.5px; }

.nc-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  border-top: 1px solid var(--line-1);
  color: var(--text-4);
  font-size: 10px;
}

.nc-foot-btn {
  padding: 0;
  color: var(--text-3);
  font-size: 10px;
  background: none;
  border: none;
  cursor: pointer;
}

.nc-foot-btn:hover { color: var(--text-1); }

.nc-pop-enter-active,
.nc-pop-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}

.nc-pop-enter-from,
.nc-pop-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}
</style>
