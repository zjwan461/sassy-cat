<template>
  <div class="layout" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <!-- 自绘标题栏（替代 Electron 原生标题栏/菜单栏）：品牌、全局搜索入口与窗口控制 -->
    <TitleBar :collapsed="sidebarCollapsed" @open-search="searchOpen = true" />

    <div class="app-body">
      <!-- 左侧导航 -->
      <aside class="sidebar">
        <nav class="nav-menu">
          <div v-for="group in menuGroups" :key="group.title" class="nav-group">
            <div class="nav-group-title">{{ group.title }}</div>
            <router-link
              v-for="item in group.items"
              :key="item.label"
              :to="item.path"
              class="nav-item"
              :class="{ disabled: item.disabled, active: !item.disabled && isMenuActive(item.path) }"
              :title="item.label"
            >
              <AppIcon :name="item.icon" :size="17" class="nav-icon" />
              <span class="nav-label">{{ item.label }}</span>
            </router-link>
          </div>
        </nav>

        <!-- 最近会话快捷区：切 tab 时不用先回聊天页翻列表 -->
        <div v-if="!sidebarCollapsed && recentConvs.length" class="recent-block">
          <div class="recent-title">最近会话</div>
          <button
            v-for="c in recentConvs"
            :key="c.id"
            type="button"
            class="recent-item"
            :class="{ active: c.id === convId }"
            :title="c.title || '未命名对话'"
            @click="openRecent(c.id)"
          >
            <AppIcon name="chat" :size="12" />
            <span class="recent-label">{{ c.title || '未命名对话' }}</span>
          </button>
        </div>

        <div class="rail-foot">
          <div class="rail-status">
            <span class="status-dot" :class="connClass"></span>
            <span class="status-text">{{ connText }}</span>
          </div>
          <span class="rail-version">v{{ appConfig.version }}</span>
          <button
            class="rail-toggle"
            type="button"
            :title="sidebarCollapsed ? '展开侧栏（Ctrl+B）' : '收起侧栏（Ctrl+B）'"
            @click="toggleSidebar"
          >
            <AppIcon :name="sidebarCollapsed ? 'chevron-right' : 'chevron-left'" :size="13" />
          </button>
        </div>
      </aside>

      <!-- 右侧内容区 -->
      <main ref="contentEl" class="content">
        <!-- 不使用 <transition> 包裹路由：窗口不可见/被遮挡时 rAF 会被节流，
             离场过渡可能永远不结束，导致页面卡在旧路由上。
             页面各自的 fadeIn 动画足以承担入场节奏。 -->
        <router-view />
      </main>
    </div>

    <!-- 知识库后台上传悬浮指示（全局渲染：任意 tab 均可见，点击回到详情页展开进度窗） -->
    <div
      v-if="kbUploading"
      class="upload-fab"
      title="点击查看进度"
      @click="revealUploadProgress"
    >
      <span class="upload-spinner"></span>
      <span class="fab-text">
        <span class="fab-label">处理中</span>
        <span class="tabular">{{ kbUploadDone }}/{{ kbUploadTotal }}</span>
        <span class="fab-current">{{ kbUploadCurrent }}</span>
      </span>
    </div>

    <!-- 全局搜索 / 命令面板（Ctrl/Cmd + K） -->
    <GlobalSearch :open="searchOpen" @close="searchOpen = false" />
    <ShortcutHelp :open="shortcutHelpOpen" @close="shortcutHelpOpen = false" />
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, watch, computed, ref, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appConfig } from './appConfig'
import { useAgentSocket } from './composables/useAgentSocket'
import { useChatStore } from './composables/useChatStore'
import { useKbUploadState } from './composables/useKbUploadState'
import { addNotification } from './composables/useNotifications'
import AppIcon from './components/AppIcon.vue'
import TitleBar from './components/TitleBar.vue'
import GlobalSearch from './components/GlobalSearch.vue'
import ShortcutHelp from './components/ShortcutHelp.vue'

const route = useRoute()
const router = useRouter()
const { state: socketState, connect, send, on, setPort } = useAgentSocket()

// 全局搜索 / 命令面板
const searchOpen = ref(false)
const shortcutHelpOpen = ref(false)
const contentEl = ref(null)

// 侧栏收起 + 最近会话：收起状态持久化到 localStorage
const sidebarCollapsed = ref(localStorage.getItem('sassy.sidebarCollapsed') === '1')
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem('sassy.sidebarCollapsed', sidebarCollapsed.value ? '1' : '0')
}

const { conv, chat, switchConversation } = useChatStore()
const recentConvs = computed(() => (conv.list || []).slice(0, 5))
const convId = computed(() => chat.convId)

function openRecent(id) {
  if (!id) return
  if (chat.convId !== id) switchConversation(id)
  router.push('/chat')
}

// 路由切换后内容区回到顶部：SPA 默认会保留上一个页面的滚动位置，
// 从长页面（设置/知识库）切到新页面时会停在半截。
watch(() => route.fullPath, async () => {
  await nextTick()
  if (contentEl.value) contentEl.value.scrollTop = 0
})
function onGlobalKeydown(e) {
  const mod = e.ctrlKey || e.metaKey
  const target = e.target
  const typing = target instanceof HTMLElement && (
    target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
  )

  if (e.key === 'Escape' && shortcutHelpOpen.value) {
    e.preventDefault()
    shortcutHelpOpen.value = false
    return
  }
  if (mod && !e.shiftKey && !e.altKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    searchOpen.value = !searchOpen.value
  } else if (mod && !e.shiftKey && !e.altKey && (e.key === 'b' || e.key === 'B')) {
    e.preventDefault()
    toggleSidebar()
  } else if (mod && !e.shiftKey && !e.altKey && e.key === '/') {
    e.preventDefault()
    shortcutHelpOpen.value = !shortcutHelpOpen.value
  } else if (!mod && !typing && e.key === '?') {
    e.preventDefault()
    shortcutHelpOpen.value = true
  }
}

function openShortcutHelp() {
  shortcutHelpOpen.value = true
}

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
let offRebuildDone = null

onMounted(() => {
  connect()
  window.addEventListener('keydown', onGlobalKeydown)
  window.addEventListener('sassy:shortcuts', openShortcutHelp)
  offProactiveReminder = on('proactive.reminder', (p) => {
    requestSystemNotify(p, true)
    addNotification({
      title: '提醒事项',
      body: String(p?.text || p?.content || ''),
      kind: 'reminder',
      action: '/chat',
      actionLabel: '去聊天',
    })
  })
  offProactiveMessage = on('proactive.message', (p) => {
    requestSystemNotify(p, false)
    addNotification({
      title: '优墨发来一条消息',
      body: String(p?.text || p?.content || ''),
      kind: 'info',
      action: '/chat',
      actionLabel: '去聊天',
    })
  })
  // 知识库全量重建结束（后台任务）：即使已经离开设置页也能收到结果
  offRebuildDone = on('kb.rebuild.done', (p) => {
    const failed = Number(p?.failed || 0)
    const total = Number(p?.total || 0)
    const done = Number(p?.done || 0)
    const errors = Array.isArray(p?.errors) ? p.errors : []
    addNotification({
      title: failed ? `索引重建完成，${failed} 篇失败` : '索引重建完成',
      body: `共 ${total} 篇文档，成功 ${done} 篇${errors.length ? `；首个错误：${errors[0]}` : ''}`,
      kind: failed ? 'error' : 'success',
      action: '/settings',
      actionLabel: '查看设置',
    })
  })
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
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('sassy:shortcuts', openShortcutHelp)
  offProactiveReminder?.()
  offProactiveMessage?.()
  offRebuildDone?.()
})

// 导航按「日常 / 扩展 / 系统」分组：比一条长列表更容易被扫读，
// 也让"日常三件套"在视觉上自然成为主路径
const menuGroups = [
  {
    title: '日常',
    items: [
      { path: '/', label: '本喵战绩', icon: 'dashboard', disabled: false },
      { path: '/chat', label: '唠嗑', icon: 'chat', disabled: false },
      { path: '/kb', label: '藏书阁', icon: 'book', disabled: false },
    ],
  },
  {
    title: '扩展',
    items: [
      { path: '/mcp', label: 'MCP', icon: 'plug', disabled: false },
      { path: '/skills', label: 'Skill', icon: 'wrench', disabled: false },
    ],
  },
  {
    title: '系统',
    items: [
      { path: '/logs', label: '日志', icon: 'list', disabled: false },
      { path: '/settings', label: '设置', icon: 'settings', disabled: false },
      { path: '/about', label: '关于', icon: 'info', disabled: false },
    ],
  },
]

const connClass = computed(() => socketState.status === 'open' ? 'on' : socketState.status === 'closed' ? 'off' : 'warn')
const connText = computed(() => ({
  open: '服务在线',
  connecting: '正在连接',
  reconnecting: '正在重连',
  closed: '服务离线',
}[socketState.status] || '服务离线'))
</script>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  position: relative;
  /* 环境光：左上一点暖、右上一点冷，让纯黑底不显得"死" */
  background:
    radial-gradient(1100px 620px at 8% -12%, rgba(239, 168, 76, 0.055), transparent 62%),
    radial-gradient(900px 560px at 102% -6%, rgba(143, 182, 232, 0.045), transparent 58%),
    var(--ink-950);
}

/* 标题栏之下的主体：侧栏 + 内容，二者共同撑满剩余高度 */
.app-body {
  flex: 1;
  min-height: 0;
  display: flex;
  position: relative;
  z-index: 1;
}

/* ===== 侧栏收起 ===== */
.layout.sidebar-collapsed {
  --sidebar-w: 64px;
}

.sidebar-collapsed .nav-label,
.sidebar-collapsed .nav-group-title,
.sidebar-collapsed .recent-block,
.sidebar-collapsed .rail-version,
.sidebar-collapsed .status-text {
  display: none;
}

.sidebar-collapsed .nav-item {
  justify-content: center;
  padding: 0;
}

.sidebar-collapsed .nav-item.active::before {
  left: 0;
}

.sidebar-collapsed .rail-foot {
  flex-direction: column;
  gap: 8px;
  padding: 10px 0;
}

/* ===== 最近会话 ===== */
.recent-block {
  flex-shrink: 0;
  max-height: 190px;
  overflow-y: auto;
  padding: 6px 10px 8px;
  border-top: 1px solid var(--line-1);
}

.recent-title {
  padding: 4px 8px 6px;
  color: var(--text-4);
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  user-select: none;
}

.recent-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 8px;
  color: var(--text-3);
  font-family: inherit;
  font-size: 11.5px;
  text-align: left;
  background: transparent;
  border: none;
  border-radius: var(--r-xs);
  cursor: pointer;
}

.recent-item:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.04);
}

.recent-item.active {
  color: var(--amber-200);
  background: rgba(239, 168, 76, 0.09);
}

.recent-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail-toggle {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-4);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-xs);
  cursor: pointer;
}

.rail-toggle:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--line-2);
}

/* 颗粒噪点：极低透明度，经屏幕后几乎看不见，但能消除大面积渐变的"塑料感" */
.layout::after {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.028;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

/* ===== 侧边栏 ===== */
.sidebar {
  position: relative;
  z-index: 1;
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #0D1017 0%, #0A0C11 100%);
  border-right: 1px solid var(--line-1);
}

/* ===== 菜单 ===== */
.nav-menu {
  flex: 1;
  min-height: 0;
  padding: 6px 10px 12px;
  overflow-y: auto;
}

.nav-group + .nav-group {
  margin-top: 6px;
}

.nav-group-title {
  padding: 14px 10px 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-4);
  user-select: none;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px;
  margin-bottom: 2px;
  border-radius: var(--r-sm);
  color: var(--text-2);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition: color var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out);
}

.nav-item .nav-icon {
  color: var(--text-3);
  transition: color var(--dur-fast) var(--ease-out), transform var(--dur) var(--ease-spring);
}

.nav-item:hover:not(.disabled):not(.active) {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-1);
}

.nav-item:hover:not(.disabled) .nav-icon {
  color: var(--amber-300);
  transform: translateY(-0.5px);
}

/* 选中态：不是一整块高饱和色，而是「被点亮」——
   暖色薄底 + 左侧琥珀指示条 + 图标发光 */
.nav-item.active {
  color: var(--amber-200);
  background: linear-gradient(90deg, rgba(239, 168, 76, 0.16), rgba(239, 168, 76, 0.03));
  box-shadow: inset 0 0 0 1px rgba(239, 168, 76, 0.14);
}

.nav-item.active .nav-icon {
  color: var(--amber-400);
  filter: drop-shadow(0 0 6px rgba(239, 168, 76, 0.45));
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 50%;
  width: 2px;
  height: 18px;
  border-radius: 0 2px 2px 0;
  background: var(--amber-grad);
  transform: translateY(-50%);
  box-shadow: 0 0 10px rgba(239, 168, 76, 0.7);
}

.nav-item.disabled {
  opacity: 0.35;
  cursor: not-allowed;
  pointer-events: none;
}

/* ===== 侧栏底部：服务状态 ===== */
.rail-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px 14px;
  border-top: 1px solid var(--line-1);
}

.rail-status {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background var(--dur), box-shadow var(--dur);
}

.status-dot.on {
  background: var(--jade-400);
  box-shadow: 0 0 0 3px rgba(126, 203, 161, 0.13);
}

.status-dot.warn {
  background: var(--amber-400);
  box-shadow: 0 0 0 3px var(--amber-a12);
  animation: breathe 1.8s ease-in-out infinite;
}

.status-dot.off {
  background: var(--coral-400);
  box-shadow: 0 0 0 3px var(--coral-a12);
}

.status-text {
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-version {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-4);
}

/* ===== 内容区 ===== */
.content {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 26px 32px 30px;
}

/* ===== 知识库后台上传悬浮指示 ===== */
.upload-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 999;
  display: flex;
  align-items: center;
  gap: 9px;
  max-width: 380px;
  padding: 9px 14px 9px 12px;
  border-radius: var(--r-full);
  background: rgba(16, 19, 26, 0.92);
  backdrop-filter: blur(14px);
  border: 1px solid var(--amber-a35);
  box-shadow: var(--shadow-3), 0 0 0 4px rgba(239, 168, 76, 0.05);
  cursor: pointer;
  animation: fab-in var(--dur) var(--ease-spring);
  transition: border-color var(--dur), transform var(--dur) var(--ease-out);
}

.upload-fab:hover {
  border-color: var(--amber-a55);
  transform: translateY(-1px);
}

@keyframes fab-in {
  from { opacity: 0; transform: translateY(10px) scale(0.97); }
  to { opacity: 1; transform: none; }
}

.upload-spinner {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  border: 2px solid var(--amber-a20);
  border-top-color: var(--amber-400);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

.fab-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-2);
  min-width: 0;
}

.fab-label {
  color: var(--amber-300);
  font-weight: 600;
}

.fab-current {
  max-width: 190px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-3);
}

/* 窄屏：侧栏收成图标轨道，给内容让出空间 */
@media (max-width: 980px) {
  .sidebar {
    width: 62px;
    min-width: 62px;
  }
  .brand {
    justify-content: center;
    padding: 16px 0 12px;
  }
  .brand-text,
  .nav-group-title,
  .nav-label,
  .rail-status .status-text,
  .rail-version {
    display: none;
  }
  .nav-menu {
    padding: 0 8px 12px;
  }
  .nav-item {
    justify-content: center;
    padding: 0;
  }
  .nav-item.active::before {
    left: -8px;
  }
  .rail-foot {
    justify-content: center;
  }
  .content {
    padding: 20px 18px 24px;
  }
}
</style>
