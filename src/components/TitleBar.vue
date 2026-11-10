<template>
  <header class="titlebar" :class="{ 'is-mac': isMac, collapsed }" @dblclick="onDoubleClick">
    <div class="tb-brand">
      <div class="tb-logo">
        <img :src="logoUrl" alt="优墨" />
      </div>
      <div class="tb-brand-text">
        <span class="tb-name">{{ appConfig.name }}</span>
        <span class="tb-sub">AI 桌宠</span>
      </div>
    </div>

    <div class="tb-space"></div>

    <button class="tb-search" type="button" title="搜索页面、操作或对话" aria-label="搜索页面、操作或对话" @click="$emit('open-search')" @dblclick.stop>
      <AppIcon name="search" :size="14" />
      <span class="tb-search-text">搜索页面、操作或对话…</span>
      <kbd class="tb-kbd">{{ isMac ? '⌘ K' : 'Ctrl K' }}</kbd>
    </button>

    <NotificationCenter class="tb-bell" />

    <div v-if="!isMac" class="tb-controls" @dblclick.stop>
      <button class="tb-btn" type="button" title="最小化" aria-label="最小化" @click="minimize">
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M2 5.5h6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
        </svg>
      </button>
      <button class="tb-btn" type="button" :title="maximized ? '还原' : '最大化'" :aria-label="maximized ? '还原' : '最大化'" @click="toggleMaximize">
        <svg v-if="!maximized" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <rect x="2.2" y="2.2" width="5.6" height="5.6" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.2" />
        </svg>
        <svg v-else width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <rect x="1.8" y="3.4" width="4.8" height="4.8" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.1" />
          <path d="M3.6 3.4V2.4a0.8 0.8 0 0 1 .8-.8h3.2a0.8 0.8 0 0 1 .8 .8v3.2a0.8 0.8 0 0 1-.8 .8H6.6" fill="none" stroke="currentColor" stroke-width="1.1" />
        </svg>
      </button>
      <button class="tb-btn tb-close" type="button" title="关闭到托盘" aria-label="关闭" @click="close">
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M2.6 2.6l4.8 4.8M7.4 2.6L2.6 7.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
        </svg>
      </button>
    </div>
  </header>
</template>

<script setup>
// 自绘标题栏：替代 Electron 原生标题栏/菜单栏。
// 整条是拖拽区；搜索框与窗口按钮单独 no-drag。
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { appConfig } from '../appConfig'
import AppIcon from './AppIcon.vue'
import NotificationCenter from './NotificationCenter.vue'
import logoUrl from '../../assets/icon.png'

defineEmits(['open-search'])
defineProps({
  collapsed: { type: Boolean, default: false },
})

const api = window.electronAPI
const isMac = api?.platform === 'darwin'
const maximized = ref(false)
let offMaximized = null

function minimize() {
  api?.minimizeWindow?.()
}

async function toggleMaximize() {
  const state = await api?.toggleMaximizeWindow?.()
  if (typeof state === 'boolean') maximized.value = state
}

function close() {
  api?.closeWindow?.()
}

function onDoubleClick(e) {
  // 双击标题栏最大化/还原（mac 交给系统红绿灯的默认行为）
  if (isMac) return
  if (e.target.closest('button, input, kbd')) return
  toggleMaximize()
}

onMounted(async () => {
  try {
    maximized.value = (await api?.isWindowMaximized?.()) || false
  } catch { /* 浏览器调试环境没有窗口 API */ }
  if (api?.onWindowMaximized) {
    offMaximized = api.onWindowMaximized((value) => { maximized.value = !!value })
  }
})

onBeforeUnmount(() => {
  if (typeof offMaximized === 'function') offMaximized()
})
</script>

<style scoped>
.titlebar {
  position: relative;
  z-index: 60;
  flex-shrink: 0;
  height: var(--titlebar-h, 48px);
  display: flex;
  align-items: center;
  gap: 12px;
  padding-right: 0;
  background: linear-gradient(180deg, #0E121A 0%, #0B0E14 100%);
  border-bottom: 1px solid var(--line-1);
  -webkit-app-region: drag;
  user-select: none;
}

/* 顶部一条极细高光，避免整条纯色显得板 */
.titlebar::after {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.07), transparent);
  pointer-events: none;
}

.tb-brand {
  width: var(--sidebar-w);
  height: 100%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 14px;
  border-right: 1px solid var(--line-1);
}

.tb-logo {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: linear-gradient(150deg, #FBF0DA 0%, #E9D2A6 100%);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.12),
    0 4px 12px -5px rgba(239, 168, 76, 0.55),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.tb-logo img {
  width: 17px;
  height: 17px;
  object-fit: contain;
}

.tb-brand-text {
  display: flex;
  align-items: baseline;
  gap: 7px;
  min-width: 0;
}

/* 侧栏收起时标题栏只留品牌图标，宽度与 64px 侧栏对齐 */
.titlebar.collapsed .tb-brand {
  justify-content: center;
  padding: 0;
}

.titlebar.collapsed .tb-brand-text {
  display: none;
}

.tb-name {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-1);
  white-space: nowrap;
}

.tb-sub {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-4);
  white-space: nowrap;
}

.tb-space {
  flex: 1;
  min-width: 12px;
}

.tb-search {
  -webkit-app-region: no-drag;
  width: min(340px, 32vw);
  height: 30px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 7px 0 10px;
  color: var(--text-4);
  background: rgba(255, 255, 255, 0.028);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-family: inherit;
  transition: border-color var(--dur-fast), background var(--dur-fast), color var(--dur-fast);
}

.tb-search:hover {
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--amber-a35);
}

.tb-search-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
  font-size: 11.5px;
}

.tb-kbd {
  flex-shrink: 0;
  padding: 2px 6px;
  font-family: inherit;
  font-size: 10px;
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid var(--line-2);
  border-radius: 5px;
}

.tb-controls {
  -webkit-app-region: no-drag;
  display: flex;
  align-items: stretch;
  height: 100%;
  margin-left: 6px;
}

.tb-btn {
  width: 46px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-3);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast);
}

.tb-btn:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.065);
}

.tb-close:hover {
  color: #FFF;
  background: #D93B3B;
}

/* macOS：给原生红绿灯留位置，隐藏自绘按钮 */
.titlebar.is-mac {
  padding-left: 76px;
}

.titlebar.is-mac .tb-brand {
  width: calc(var(--sidebar-w) - 76px);
  border-right: none;
}

.titlebar.is-mac.collapsed {
  padding-left: 76px;
}

.titlebar.is-mac.collapsed .tb-brand {
  width: auto;
}

@media (max-width: 900px) {
  .tb-sub,
  .tb-search-text {
    display: none;
  }
  .tb-search {
    width: auto;
    padding: 0 9px;
  }
}
</style>
