<template>
  <Teleport to="body">
    <Transition name="gs">
      <div v-if="open" class="gs-overlay" @click.self="close">
        <div class="gs-panel" role="dialog" aria-modal="true" aria-label="全局搜索">
          <div class="gs-input-row">
            <AppIcon name="search" :size="16" class="gs-input-icon" />
            <input
              ref="inputEl"
              v-model="query"
              class="gs-input"
              type="text"
              placeholder="搜索页面、操作或对话…"
              @keydown="onKeydown"
            />
            <kbd class="gs-esc">Esc</kbd>
          </div>

          <div class="gs-body">
            <template v-if="groups.length">
              <div v-for="group in groups" :key="group.key" class="gs-group">
                <div class="gs-group-title">{{ group.title }}</div>
                <button
                  v-for="item in group.items"
                  :key="item.id"
                  type="button"
                  class="gs-item"
                  :class="{ active: item.idx === activeIndex }"
                  @mouseenter="activeIndex = item.idx"
                  @click="run(item)"
                >
                  <span class="gs-icon"><AppIcon :name="item.icon" :size="15" /></span>
                  <span class="gs-main">
                    <span class="gs-title">{{ item.title }}</span>
                    <span v-if="item.desc" class="gs-desc">{{ item.desc }}</span>
                  </span>
                  <span class="gs-hint">{{ item.hint }}</span>
                  <AppIcon v-if="item.idx === activeIndex" name="arrow-right" :size="12" class="gs-arrow" />
                </button>
              </div>
            </template>
            <div v-else class="gs-empty">
              <AppIcon name="search" :size="18" />
              <p>没有找到「{{ query.trim() }}」相关结果</p>
              <span>试试搜索「设置」「新建对话」或某个会话标题</span>
            </div>
          </div>

          <div class="gs-footer">
            <span class="gs-foot-group"><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
            <span class="gs-foot-group"><kbd>Enter</kbd> 打开</span>
            <span class="gs-foot-group"><kbd>Esc</kbd> 关闭</span>
            <span class="gs-foot-right">优墨 · 命令面板</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { conv, loadConversations, newConversation, switchConversation } from '../composables/useChatStore'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const router = useRouter()
const inputEl = ref(null)
const query = ref('')
const activeIndex = ref(0)
const petEnabled = ref(null)

const PAGES = [
  { title: '仪表盘', desc: '今日对话、Token 与最近活动', path: '/', icon: 'dashboard', hint: '页面', keywords: 'dashboard 首页 概览 战绩' },
  { title: '唠嗑', desc: '和优墨聊天、切换会话', path: '/chat', icon: 'chat', hint: '页面', keywords: 'chat 聊天 对话 会话' },
  { title: '藏书阁', desc: '知识库、文档分块与检索测试', path: '/kb', icon: 'book', hint: '页面', keywords: 'kb 知识库 文档 rag' },
  { title: 'MCP', desc: 'MCP 服务器与工具', path: '/mcp', icon: 'plug', hint: '页面', keywords: 'mcp 服务器 工具' },
  { title: 'Skill', desc: '技能列表、编辑与脚本', path: '/skills', icon: 'wrench', hint: '页面', keywords: 'skill 技能 脚本' },
  { title: '日志', desc: '实时运行日志与导出', path: '/logs', icon: 'terminal', hint: '页面', keywords: 'log 日志 输出 调试' },
  { title: '设置', desc: '模型、工作区、桌宠与语音', path: '/settings', icon: 'settings', hint: '页面', keywords: 'setting 设置 配置 模型 工作区' },
  { title: '关于', desc: '版本、开源信息与配置目录', path: '/about', icon: 'info', hint: '页面', keywords: 'about 关于 版本 开源' },
]

const ACTIONS = computed(() => [
  {
    title: '新建对话',
    desc: '开一段新的聊天',
    icon: 'plus',
    hint: '操作',
    keywords: 'new chat 新建 会话 对话',
    run: () => {
      newConversation()
      router.push('/chat')
    },
  },
  {
    title: petEnabled.value === false ? '显示桌宠' : '隐藏桌宠',
    desc: petEnabled.value === false ? '把优墨放回桌面' : '暂时收起桌面上的猫',
    icon: 'bot',
    hint: '操作',
    keywords: 'pet 桌宠 显示 隐藏 猫',
    run: async () => {
      const api = window.electronAPI
      if (!api?.setConfig) return
      const next = petEnabled.value === false
      const res = await api.setConfig('pet.enabled', next)
      if (res?.success) petEnabled.value = next
    },
  },
  {
    title: '快捷键帮助',
    desc: '查看全部键盘快捷键',
    icon: 'key',
    hint: '操作',
    keywords: 'keyboard shortcut 快捷键 help 帮助',
    run: () => window.dispatchEvent(new Event('sassy:shortcuts')),
  },
  {
    title: '重启 Agent 服务',
    desc: 'Python 后端重连，适用于改完配置后',
    icon: 'refresh',
    hint: '操作',
    keywords: 'restart 重启 服务 agent 后端',
    run: () => window.electronAPI?.restartAgent?.(),
  },
  {
    title: '导出运行日志',
    desc: '保存为 .log 文件',
    icon: 'download',
    hint: '操作',
    keywords: 'export log 导出 日志',
    run: async () => {
      const api = window.electronAPI
      if (!api?.exportLogs) return
      const logs = await api.getLogs()
      await api.exportLogs(logs)
    },
  },
])

function matches(text, q) {
  return String(text || '').toLowerCase().includes(q)
}

const groups = computed(() => {
  const q = query.value.trim().toLowerCase()
  let idx = 0

  const pageItems = PAGES
    .filter((p) => !q || matches(p.title, q) || matches(p.desc, q) || matches(p.keywords, q))
    .map((p) => ({
      id: `page:${p.path}`,
      title: p.title,
      desc: p.desc,
      icon: p.icon,
      hint: p.hint,
      idx: idx++,
      run: () => router.push(p.path),
    }))

  const actionItems = ACTIONS.value
    .filter((a) => !q || matches(a.title, q) || matches(a.desc, q) || matches(a.keywords, q))
    .map((a) => ({
      id: `action:${a.title}`,
      title: a.title,
      desc: a.desc,
      icon: a.icon,
      hint: a.hint,
      idx: idx++,
      run: a.run,
    }))

  const convItems = (conv.list || [])
    .filter((c) => !q || matches(c.title, q))
    .slice(0, 8)
    .map((c) => ({
      id: `conv:${c.id}`,
      title: c.title || '未命名对话',
      desc: '打开这段对话',
      icon: 'chat',
      hint: '对话',
      idx: idx++,
      run: () => {
        switchConversation(c.id)
        router.push('/chat')
      },
    }))

  return [
    { key: 'page', title: '页面', items: pageItems },
    { key: 'action', title: '操作', items: actionItems },
    { key: 'conv', title: '最近对话', items: convItems },
  ].filter((g) => g.items.length)
})

const flat = computed(() => groups.value.flatMap((g) => g.items))

function close() {
  emit('close')
}

function run(item) {
  if (!item) return
  close()
  nextTick(() => {
    try {
      item.run()
    } catch (e) {
      console.warn('[search] action failed:', e)
    }
  })
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
    return
  }
  if (!flat.value.length) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % flat.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + flat.value.length) % flat.value.length
  } else if (e.key === 'Enter') {
    e.preventDefault()
    run(flat.value[activeIndex.value])
  }
}

watch(query, () => { activeIndex.value = 0 })

watch(activeIndex, () => {
  nextTick(() => {
    const el = document.querySelector('.gs-item.active')
    if (el) el.scrollIntoView({ block: 'nearest' })
  })
})

watch(() => props.open, async (open) => {
  if (!open) return
  query.value = ''
  activeIndex.value = 0
  loadConversations()
  try {
    const cfg = await window.electronAPI?.getConfig?.()
    if (cfg?.success) petEnabled.value = cfg.config.pet?.enabled !== false
  } catch { /* 浏览器调试环境无配置 API */ }
  await nextTick()
  inputEl.value?.focus()
})
</script>

<style scoped>
.gs-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 7vh;
  background: rgba(4, 7, 12, 0.62);
  backdrop-filter: blur(9px) saturate(120%);
  -webkit-backdrop-filter: blur(9px) saturate(120%);
}

.gs-panel {
  width: min(640px, calc(100vw - 48px));
  max-height: min(700px, 88vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, #121721 0%, #0D1118 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  box-shadow:
    0 30px 80px -20px rgba(0, 0, 0, 0.85),
    0 0 0 1px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.gs-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 14px;
  border-bottom: 1px solid var(--line-1);
}

.gs-input-icon {
  flex-shrink: 0;
  color: var(--text-4);
}

.gs-input {
  flex: 1;
  min-width: 0;
  height: 24px;
  padding: 0;
  color: var(--text-1);
  font-size: 13.5px;
  font-family: inherit;
  background: transparent;
  border: none;
  outline: none;
}

.gs-input::placeholder {
  color: var(--text-4);
}

.gs-esc {
  flex-shrink: 0;
  padding: 2px 6px;
  color: var(--text-3);
  font-family: inherit;
  font-size: 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line-2);
  border-radius: 5px;
}

.gs-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 8px 8px;
}

.gs-group + .gs-group {
  margin-top: 2px;
}

.gs-group-title {
  padding: 8px 8px 4px;
  color: var(--text-4);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  user-select: none;
}

.gs-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  color: var(--text-2);
  text-align: left;
  font-family: inherit;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
}

.gs-item.active {
  color: var(--text-1);
  background: linear-gradient(90deg, rgba(239, 168, 76, 0.13), rgba(239, 168, 76, 0.045));
  border-color: rgba(239, 168, 76, 0.22);
}

.gs-icon {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.04);
  border-radius: 7px;
}

.gs-item.active .gs-icon {
  color: var(--amber-300);
  background: rgba(239, 168, 76, 0.12);
}

.gs-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.gs-title {
  font-size: 12.8px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gs-desc {
  color: var(--text-4);
  font-size: 10.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gs-hint {
  flex-shrink: 0;
  color: var(--text-4);
  font-size: 10.5px;
}

.gs-arrow {
  flex-shrink: 0;
  color: var(--amber-300);
}

.gs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 46px 20px 50px;
  color: var(--text-4);
  text-align: center;
}

.gs-empty p {
  margin: 4px 0 0;
  color: var(--text-2);
  font-size: 13px;
}

.gs-empty span {
  font-size: 11px;
}

.gs-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 14px;
  border-top: 1px solid var(--line-1);
  background: rgba(0, 0, 0, 0.18);
  color: var(--text-4);
  font-size: 10.5px;
}

.gs-foot-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gs-foot-group kbd {
  padding: 1px 5px;
  color: var(--text-3);
  font-family: inherit;
  font-size: 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line-2);
  border-radius: 4px;
}

.gs-foot-right {
  margin-left: auto;
  letter-spacing: 0.05em;
}

.gs-enter-active,
.gs-leave-active {
  transition: opacity 0.16s ease;
}

.gs-enter-active .gs-panel,
.gs-leave-active .gs-panel {
  transition: transform 0.16s cubic-bezier(0.22, 0.61, 0.36, 1), opacity 0.16s ease;
}

.gs-enter-from,
.gs-leave-to {
  opacity: 0;
}

.gs-enter-from .gs-panel,
.gs-leave-to .gs-panel {
  transform: translateY(-8px) scale(0.985);
  opacity: 0;
}

@media (max-width: 640px) {
  .gs-overlay { padding-top: 8vh; }
  .gs-footer { gap: 10px; }
  .gs-foot-right { display: none; }
}
</style>
