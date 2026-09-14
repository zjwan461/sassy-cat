<template>
  <div class="layout">
    <!-- 左侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo"><img :src="logoUrl" alt="logo" /></div>
        <div class="app-name">{{ appConfig.name }}</div>
      </div>

      <div class="sidebar-divider"></div>

      <nav class="nav-menu">
        <router-link
          v-for="item in menuItems"
          :key="item.label"
          :to="item.path"
          class="nav-item"
          :class="{ disabled: item.disabled, active: !item.disabled && isMenuActive(item.path) }"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>
    <!-- 右侧内容区 -->
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appConfig } from './appConfig'
import { useAgentSocket } from './composables/useAgentSocket'
import logoUrl from '../assets/icon.png'

const route = useRoute()
const router = useRouter()
const { state: socketState, connect, setPort } = useAgentSocket()

// 菜单高亮：/kb 及其子路径（/kb/:kbId）均视为选中"知识库"
function isMenuActive(path) {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(path + '/')
}

// ---------- 启动 loading 消除 ----------
// 就绪判定：WebSocket 首次连通（Agent/WS 服务已就绪）即淡出移除全屏 loading；
// 非 Electron 环境（浏览器直开调试）无后端服务，挂载即移除；
// 另设保险超时，防止异常情况下 loading 永久驻留。
let loadingRemoved = false
let loadingTimer = null

function dismissBootLoading() {
  if (loadingRemoved) return
  loadingRemoved = true
  clearTimeout(loadingTimer)
  const el = document.getElementById('boot-loading')
  if (!el) return
  el.classList.add('boot-hidden')
  // 淡出动画结束后从 DOM 移除
  setTimeout(() => el.remove(), 500)
}

// 首次连通后不再重复触发
const stopWatch = watch(socketState, (s) => {
  if (s.status === 'open') {
    stopWatch()
    // 稍作延迟让 Dashboard 完成首帧数据拉取，衔接更顺滑
    setTimeout(dismissBootLoading, 200)
  }
})

onMounted(() => {
  connect()
  if (window.electronAPI) {
    window.electronAPI.getAgentInfo().then((info) => {
      if (info && info.port) setPort(info.port)
    })
    window.electronAPI.onAgentReady((info) => { if (info && info.port) setPort(info.port) })
    window.electronAPI.onNavigateChat(() => router.push('/chat'))
  } else {
    // 非 Electron 环境无 Agent 服务可等，直接进入界面
    dismissBootLoading()
  }
  // 保险：最长 20s 后强制移除 loading（如 WS 始终无法连通的故障场景）
  loadingTimer = setTimeout(dismissBootLoading, 20000)
})

onBeforeUnmount(() => {
  clearTimeout(loadingTimer)
  stopWatch()
})

const menuItems = [
  { path: '/', label: '系统监控', icon: '📊', disabled: false },
  { path: '/chat', label: 'AI 聊天', icon: '💬', disabled: false },
  { path: '/kb', label: '知识库', icon: '📚', disabled: false },
  { path: '/logs', label: '日志', icon: '📋', disabled: false },
  { path: '/settings', label: '设置', icon: '🐟', disabled: false },
  { path: '/about', label: '关于', icon: 'ℹ️', disabled: false }
]
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  background: #0f172a;
  overflow: hidden;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: 168px;
  min-width: 168px;
  background: #1e293b;
  border-right: 1px solid #334155;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 16px;
}

.logo {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 10px;
}
.app-name {
  font-size: 16px;
  font-weight: 700;
  color: #f1f5f9;
}

.sidebar-divider {
  height: 1px;
  background: #334155;
  margin: 0 12px 10px;
}
/* ===== 菜单 ===== */
.nav-menu {
  flex: 1;
  padding: 0 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  color: #94a3b8;
  text-decoration: none;
  font-size: 14px;
  transition: all 0.2s;
}

.nav-item:hover:not(.disabled):not(.active) {
  background: #273449;
  color: #e2e8f0;
}

.nav-item.active {
  background: #4f46e5;
  color: #ffffff;
  font-weight: 500;
}

.nav-item.disabled {
  opacity: 0.45;
  cursor: not-allowed;
  pointer-events: none;
}

.nav-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}
/* ===== 内容区 ===== */
/* ===== 内容区 ===== */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
}

.content::-webkit-scrollbar {
  width: 8px;
}

.content::-webkit-scrollbar-track {
  background: transparent;
}

.content::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 4px;
}
</style>
