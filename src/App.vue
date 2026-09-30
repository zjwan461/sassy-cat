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

    <!-- 知识库后台上传悬浮指示（全局渲染：任意 tab 均可见，点击回到详情页展开进度窗） -->
    <div
      v-if="kbUploading"
      class="upload-fab"
      title="点击查看进度"
      @click="revealUploadProgress"
    >
      <span class="upload-spinner sm"></span>
      <span class="fab-text">处理中 {{ kbUploadDone }}/{{ kbUploadTotal }} · {{ kbUploadCurrent }}</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appConfig } from './appConfig'
import { useAgentSocket } from './composables/useAgentSocket'
import { useKbUploadState } from './composables/useKbUploadState'
import logoUrl from '../assets/icon.png'

const route = useRoute()
const router = useRouter()
const { state: socketState, connect, send, on, setPort } = useAgentSocket()

// 知识库上传状态（模块级单例，与详情页共享）
const {
  uploading: kbUploading,
  uploadTotal: kbUploadTotal,
  uploadDone: kbUploadDone,
  uploadCurrent: kbUploadCurrent,
  maskVisible: kbUploadMask,
  uploadKbId: kbUploadKbId,
} = useKbUploadState()

function revealUploadProgress() {
  kbUploadMask.value = true
  const target = `/kb/${kbUploadKbId || ''}`
  if (route.path !== target) router.push(target)
}

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

// 桌宠不可见（设置关闭 / 临时隐藏）时的提醒兜底：
// 主窗口常驻 WS 连接，订阅 proactive.* 事件请求系统通知；
// 是否真正弹出由主进程按桌宠窗口实际可见性裁决（可见则抑制，避免与气泡双重打扰）
function requestSystemNotify(payload, isReminder) {
  if (!window.electronAPI?.showNotification) return
  const text = String(payload?.text || payload?.content || '')
  if (!text) return
  window.electronAPI.showNotification({
    title: isReminder ? '⏰ 提醒事项' : '🐱 优墨',
    body: text.replace(/^⏰\s*/, ''),
  }).catch(() => { /* 通知失败不影响主流程 */ })
}

let offProactiveReminder = null
let offProactiveMessage = null

onMounted(() => {
  connect()
  offProactiveReminder = on('proactive.reminder', (p) => requestSystemNotify(p, true))
  offProactiveMessage = on('proactive.message', (p) => requestSystemNotify(p, false))
  if (window.electronAPI) {
    window.electronAPI.getAgentInfo().then((info) => {
      if (info && info.port) setPort(info.port)
    })
    window.electronAPI.onAgentReady((info) => { if (info && info.port) setPort(info.port) })
    window.electronAPI.onNavigateChat(() => router.push('/chat'))
    // OS 级活动信号上行（与桌宠端同款逻辑）：
    // 保证桌宠关闭后 Python 侧闲置检测依然能收到 user_activity，不会误判闲置
    window.electronAPI.onActivityPing((data) => {
      send('client.event', { name: 'user_activity', event: data.event })
    })
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
  offProactiveReminder?.()
  offProactiveMessage?.()
})

const menuItems = [
  { path: '/', label: '本喵战绩', icon: '😼', disabled: false },
  { path: '/chat', label: '唠嗑', icon: '💬', disabled: false },
  { path: '/kb', label: '藏书阁', icon: '📚', disabled: false },
  { path: '/skills', label: 'Skill', icon: '🛠️', disabled: false },
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

/* ===== 知识库后台上传悬浮指示 ===== */
.upload-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 999;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #1e293b;
  border: 1px solid #4f46e5;
  border-radius: 999px;
  padding: 10px 16px;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: fab-in 0.25s ease;
}
.upload-fab:hover { border-color: #818cf8; }
@keyframes fab-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}
.upload-spinner.sm {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  border: 2px solid rgba(129, 140, 248, 0.25);
  border-top-color: #818cf8;
  border-radius: 50%;
  animation: fab-spin 0.9s linear infinite;
}
@keyframes fab-spin { to { transform: rotate(360deg); } }
.fab-text {
  font-size: 12px;
  color: #cbd5e1;
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
