<template>
  <div class="pet-root">
    <!-- 气泡 / 快捷输入 -->
    <div v-if="bubbleText || inputOpen" ref="bubbleWrapRef" class="bubble-wrap">
      <div
        v-if="bubbleText && !inputOpen"
        class="bubble"
        :class="{ expanded: bubbleExpanded }"
        @mouseenter="onBubbleEnter"
        @mouseleave="onBubbleLeave"
      >
        <div ref="bubbleTextRef" class="bubble-text" :class="{ clamped: !bubbleExpanded }">{{ bubbleText }}</div>
        <div v-if="bubbleActionsVisible" class="bubble-actions">
          <button v-if="!bubbleExpanded && bubbleOverflows" class="bbtn" @click.stop="expandBubble">▾ 展开</button>
          <button v-if="bubbleExpanded" class="bbtn" @click.stop="collapseBubble">▴ 收起</button>
          <button v-if="bubbleTruncated || bubbleExpanded" class="bbtn" @click.stop="openFullChat">💬 完整对话</button>
          <button v-if="bubbleExpanded" class="bbtn bbtn-x" title="关闭" @click.stop="hideBubble">✕</button>
        </div>
      </div>
      <div v-if="inputOpen" class="quick-input">
        <input
          ref="quickInputRef"
          v-model="quickDraft"
          placeholder="跟本喵说点什么…"
          @keydown.enter.prevent="sendQuick"
          @keydown.esc="closeInput"
        />
      </div>
    </div>

    <!-- 桌宠本体：程序生成 SVG + CSS 关键帧（一期占位，接口兼容后续 spritesheet 替换） -->
    <div
      ref="spriteRef"
      class="pet-sprite"
      :class="[state, { flip: facingLeft }]"
      @mousedown="onMouseDown"
      @click="onClick"
      @dblclick="onDblClick"
      @contextmenu.prevent="onContextMenu"
    >
      <svg viewBox="0 0 120 110" width="120" height="110">
        <path :d="tailPath" fill="none" stroke="#334155" stroke-width="8" stroke-linecap="round"/>
        <ellipse cx="60" cy="76" rx="34" ry="26" fill="#64748b"/>
        <path d="M36 38 L44 16 L56 34 Z" fill="#64748b"/>
        <path d="M84 38 L76 16 L64 34 Z" fill="#64748b"/>
        <path d="M40 33 L45 21 L51 31 Z" fill="#f9a8d4"/>
        <path d="M80 33 L75 21 L69 31 Z" fill="#f9a8d4"/>
        <circle cx="60" cy="46" r="26" fill="#64748b"/>
        <template v-if="eyesClosed">
          <path d="M46 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <path d="M62 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
        </template>
        <template v-else>
          <circle cx="51" cy="43" r="4" fill="#1e293b"/>
          <circle cx="69" cy="43" r="4" fill="#1e293b"/>
          <circle cx="52.5" cy="41.5" r="1.4" fill="#fff"/>
          <circle cx="70.5" cy="41.5" r="1.4" fill="#fff"/>
        </template>
        <path v-if="state === 'talk'" d="M55 54 q5 6 10 0 q-5 8 -10 0" fill="#be185d"/>
        <path v-else d="M55 54 q5 4 10 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
        <path d="M30 48 h12 M31 55 l11 -3 M90 48 h-12 M89 55 l-11 -3" stroke="#1e293b" stroke-width="1.6" stroke-linecap="round"/>
        <text v-if="state === 'think'" x="90" y="16" font-size="16" fill="#a5b4fc" class="float-q">?</text>
        <text v-if="state === 'sleep'" x="86" y="18" font-size="13" fill="#94a3b8" class="float-q">z z z</text>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useAgentSocket, setClient } from '../../src/composables/useAgentSocket'

const { state: sock, connect, send, on, setPort } = useAgentSocket()
setClient('pet')

const PET_BASE_H = 150, PET_BASE_W = 220
const EXPANDED_H = 220, BUBBLE_W = 300
// 气泡几何：bubble-wrap 距窗口底边 118px，窗口高度 = 118 + 气泡实测高度 + 8 顶部留白
const BUBBLE_BOTTOM = 118, BUBBLE_TOP_PAD = 8
// 气泡文本硬上限：超出截断并引导去主窗口看完整对话
const BUBBLE_MAX_CHARS = 600
const QUICK_PHRASES = [
  '哼，找本喵干嘛😾', '摸头要付费的！', '喵呜～（其实很开心）',
  '有事启奏，无事退朝。', '本喵今天心情不错，准你撸一下。'
]

const state = ref('idle') // idle|walk|drag|react|think|talk|sleep|remind
const bubbleText = ref('')
const bubbleExpanded = ref(false)
const bubbleOverflows = ref(false)
const bubbleTruncated = ref(false)
const bubbleHovered = ref(false)
const inputOpen = ref(false)
const quickDraft = ref('')
const facingLeft = ref(false)
const frameIdx = ref(0)
const spriteRef = ref(null)
const quickInputRef = ref(null)
const bubbleWrapRef = ref(null)
const bubbleTextRef = ref(null)

const bubbleActionsVisible = computed(() =>
  !!bubbleText.value && (bubbleOverflows.value || bubbleTruncated.value || bubbleExpanded.value)
)

let timers = {}
let dragging = false

// ---------- 帧驱动 ----------
const eyesClosed = computed(() => {
  if (state.value === 'sleep') return true
  return frameIdx.value % 8 === 6 // 周期眨眼
})
const tailPath = computed(() => {
  const w = Math.sin(frameIdx.value * 0.9) * 12
  return `M92 84 q20 ${-8 + w} ${16 + w * 0.4} -26`
})

// ---------- 状态机 ----------
function setState(s, holdMs = 0) {
  state.value = s
  if (holdMs) {
    clearTimeout(timers.hold)
    timers.hold = setTimeout(() => {
      if (state.value === s) { setState('idle'); scheduleNext() }
    }, holdMs)
  }
}

function walkAround() {
  if (state.value === 'drag' || !window.petAPI) { setState('idle'); return }
  setState('walk')
  const total = Math.round((Math.random() - 0.5) * 240)
  facingLeft.value = total < 0
  const step = total / 12
  let moved = 0
  clearInterval(timers.walk)
  timers.walk = setInterval(() => {
    window.petAPI.moveDelta(step, 0)
    if (++moved >= 12) {
      clearInterval(timers.walk)
      setState('idle')
      scheduleNext()
    }
  }, 45)
}

function scheduleNext() {
  clearTimeout(timers.next)
  timers.next = setTimeout(() => {
    if (state.value === 'idle') { Math.random() < 0.4 ? walkAround() : scheduleNext() }
  }, 4000 + Math.random() * 8000)
}

// ---------- 交互 ----------
function onClick() {
  if (dragMoved) return
  setState('react', 1000)
  if (Math.random() < 0.4) showBubble(QUICK_PHRASES[Math.floor(Math.random() * QUICK_PHRASES.length)], 2600)
}

function onDblClick() { window.petAPI && window.petAPI.showChat() }

function onContextMenu() {
  window.petAPI && window.petAPI.popupMenu([
    { label: '💬 打开聊天', action: 'chat' },
    { label: inputOpen.value ? '收起输入框' : '⌨️ 快速提问', action: 'input' },
    { label: '🙈 隐藏桌宠', action: 'hide' }
  ])
}

// 全局快捷键触发：切换快速输入框
function onQuickAskHotkey() {
  if (inputOpen.value) closeInput(); else openInput()
}

function onMenuAction({ action }) {
  if (action === 'chat') window.petAPI.showChat()
  else if (action === 'input') inputOpen.value ? closeInput() : openInput()
  else if (action === 'hide') window.petAPI.hideSelf()
}

async function openInput() {
  inputOpen.value = true
  hideBubble()
  await nextTick()
  syncWindow()
  // 快捷键唤起时鼠标未必在窗口上方，需主动退出穿透以保证输入框可点击
  if (window.petAPI) {
    hoverInside = true
    window.petAPI.setInteractive(true)
  }
  quickInputRef.value && quickInputRef.value.focus()
}

function closeInput() {
  inputOpen.value = false
  quickDraft.value = ''
  syncWindow()
}

function sendQuick() {
  const text = quickDraft.value.trim()
  if (!text) return
  quickDraft.value = ''
  send('chat.send', { sessionId: sock.sessionId, content: text })
  setState('think')
}

// ---------- 气泡窗口自适应 ----------
// 气泡内容变化时，把桌宠窗口向上/向两侧扩到刚好容纳气泡（主进程负责底边锚定与屏幕钳制）
let syncPending = false
function syncWindow() {
  if (!window.petAPI) return
  let h = PET_BASE_H, w = PET_BASE_W
  if (inputOpen.value) {
    h = EXPANDED_H; w = BUBBLE_W
  } else if (bubbleText.value) {
    const bh = bubbleWrapRef.value ? bubbleWrapRef.value.offsetHeight : 48
    h = Math.max(PET_BASE_H, BUBBLE_BOTTOM + bh + BUBBLE_TOP_PAD)
    w = BUBBLE_W
  }
  window.petAPI.resize({ height: h, width: w })
}
function scheduleSync() {
  if (syncPending) return
  syncPending = true
  requestAnimationFrame(async () => {
    syncPending = false
    await nextTick()
    measureOverflow()
    syncWindow()
  })
}
function measureOverflow() {
  const el = bubbleTextRef.value
  if (!el) { bubbleOverflows.value = false; return }
  bubbleOverflows.value = el.scrollHeight > el.clientHeight + 2
}

// ---------- 气泡显示/自动隐藏（悬停与阅读模式暂停倒计时） ----------
let bubbleTimer = null
let bubbleHideAt = 0
function startBubbleTimer() {
  clearTimeout(bubbleTimer)
  const d = bubbleHideAt - Date.now()
  if (d <= 0) { hideBubble(); return }
  bubbleTimer = setTimeout(hideBubble, d)
}
function pauseBubbleTimer() { clearTimeout(bubbleTimer); bubbleTimer = null }
function resumeBubbleTimer(minMs = 2500) {
  if (!bubbleText.value) return
  if (bubbleHideAt <= Date.now()) bubbleHideAt = Date.now() + minMs
  startBubbleTimer()
}
function hideBubble() {
  clearTimeout(bubbleTimer); bubbleTimer = null
  bubbleText.value = ''
  bubbleExpanded.value = false
  bubbleOverflows.value = false
  bubbleTruncated.value = false
  scheduleSync()
}

function showBubble(text, ms = 5000) {
  let t = String(text || '')
  bubbleTruncated.value = t.length > BUBBLE_MAX_CHARS
  if (bubbleTruncated.value) t = t.slice(0, BUBBLE_MAX_CHARS) + '…'
  bubbleText.value = t
  bubbleExpanded.value = false
  clearTimeout(bubbleTimer)
  bubbleHideAt = Date.now() + ms
  startBubbleTimer()
  scheduleSync()
}

function onBubbleEnter() { bubbleHovered.value = true; pauseBubbleTimer() }
function onBubbleLeave() {
  bubbleHovered.value = false
  if (!bubbleExpanded.value) resumeBubbleTimer()
}
function expandBubble() { bubbleExpanded.value = true; pauseBubbleTimer(); scheduleSync() }
function collapseBubble() { bubbleExpanded.value = false; resumeBubbleTimer(4000); scheduleSync() }
function openFullChat() { window.petAPI && window.petAPI.showChat() }

// ---------- 气泡打字机 ----------
let streamBuf = ''
let streamTarget = ''
let typer = null
function typewriteStart() {
  streamBuf = ''; streamTarget = ''
  clearInterval(typer)
  typer = setInterval(() => {
    if (streamBuf.length < streamTarget.length) {
      streamBuf = streamTarget.slice(0, Math.min(streamBuf.length + 2, BUBBLE_MAX_CHARS))
      bubbleText.value = streamBuf
      scheduleSync()
    }
  }, 40)
}
function typewriteStop() { clearInterval(typer); typer = null }

// ---------- 拖动（增量移动，主进程节流） ----------
let dragMoved = false
function onMouseDown(e) {
  if (e.button !== 0 || !window.petAPI) return
  dragging = true
  dragMoved = false
  let lastX = e.screenX, lastY = e.screenY
  const moveHandler = (me) => {
    const ddx = me.screenX - lastX, ddy = me.screenY - lastY
    lastX = me.screenX; lastY = me.screenY
    if (Math.abs(ddx) + Math.abs(ddy) > 0) {
      dragMoved = true
      if (state.value !== 'drag') setState('drag')
      window.petAPI.moveDelta(ddx, ddy)
    }
  }
  const upHandler = () => {
    document.removeEventListener('mousemove', moveHandler)
    document.removeEventListener('mouseup', upHandler)
    dragging = false
    if (dragMoved && state.value === 'drag') { setState('idle'); scheduleNext() }
    setTimeout(() => { dragMoved = false }, 50)
  }
  document.addEventListener('mousemove', moveHandler)
  document.addEventListener('mouseup', upHandler)
}

// ---------- 鼠标穿透控制 ----------
let hoverInside = true
function onDocMouseMove(e) {
  if (!window.petAPI) return
  const el = spriteRef.value
  if (!el) return
  const pad = 14
  const r = el.getBoundingClientRect()
  let inside = e.clientX >= r.left - pad && e.clientX <= r.right + pad &&
               e.clientY >= r.top - pad && e.clientY <= r.bottom + pad
  // 气泡区域同样需要命中（悬停暂停倒计时、展开后可滚动/点按钮）
  if (!inside) {
    const bw = bubbleWrapRef.value
    if (bw && (bubbleText.value || inputOpen.value)) {
      const b = bw.getBoundingClientRect()
      inside = e.clientX >= b.left && e.clientX <= b.right &&
               e.clientY >= b.top && e.clientY <= b.bottom
    }
  }
  const need = inside || inputOpen.value
  if (need !== hoverInside) {
    hoverInside = need
    window.petAPI.setInteractive(need)
  }
}

// ---------- 生命周期 ----------
onMounted(() => {
  timers.tick = setInterval(() => { frameIdx.value++ }, 220)
  setState('idle')
  scheduleNext()
  document.addEventListener('mousemove', onDocMouseMove)

  if (window.petAPI) {
    window.petAPI.onActivityPing((data) => {
      send('client.event', { name: 'user_activity', event: data.event })
    })
    window.petAPI.onAgentReady((info) => { if (info && info.port) setPort(info.port) })
    window.petAPI.onMenuAction(onMenuAction)
    window.petAPI.onQuickAsk(onQuickAskHotkey)
    window.petAPI.getPosition().then((pos) => { if (pos) facingLeft.value = false })
  }
  connect()

  on('chat.started', () => { setState('think'); if (inputOpen.value) closeInput() })
  on('chat.delta', (p) => {
    if (state.value !== 'talk') { setState('talk'); typewriteStart() }
    streamTarget += p.text
  })
  on('chat.completed', (p) => {
    if (p.text && p.text.length >= streamTarget.length) streamTarget = p.text
    setTimeout(() => {
      typewriteStop()
      if (streamTarget) {
        // 阅读时长随文本长度自适应（90ms/字，9s ~ 25s），超长截断由 showBubble 内部处理
        const ms = Math.min(25000, Math.max(9000, streamTarget.length * 90))
        showBubble(streamTarget, ms)
      }
      setState('idle'); scheduleNext()
    }, 1400)
  })
  on('chat.error', () => { typewriteStop(); setState('idle'); showBubble('呜…出了点小状况 😿', 4000) })
  on('pet.command', (p) => {
    if (p.action === 'think') setState('think')
    else if (p.action === 'remind') { setState('remind', p.durationMs || 8000); if (p.text) showBubble(p.text, p.durationMs || 8000) }
    else if (p.action === 'wave') setState('react', 1200)
    else if (p.action === 'sleep') setState('sleep')
    else if (p.action === 'idle' && !dragging) { setState('idle'); scheduleNext() }
  })
  on('proactive.message', (p) => { setState('remind', 8000); showBubble(p.text, 8000) })
})

onBeforeUnmount(() => {
  Object.values(timers).forEach((t) => { clearInterval(t); clearTimeout(t) })
  clearTimeout(bubbleTimer)
  typewriteStop()
  document.removeEventListener('mousemove', onDocMouseMove)
})
</script>

<style scoped>
.pet-root { position: relative; width: 100vw; height: 100vh; background: transparent; }
.pet-sprite {
  position: absolute; bottom: 4px; left: 50%; transform: translateX(-50%);
  cursor: grab; filter: drop-shadow(0 4px 8px rgba(0,0,0,.35));
}
.pet-sprite.drag { cursor: grabbing; }
.pet-sprite.walk svg { animation: bob .44s infinite; }
.pet-sprite.idle svg { animation: breathe 2.6s ease-in-out infinite; }
.pet-sprite.react svg { animation: bounce .3s 2; }
.pet-sprite.remind svg { animation: wiggle .35s 4; }
.pet-sprite.talk svg { animation: bob .3s infinite; }
.pet-sprite.think svg { animation: breathe 1.6s ease-in-out infinite; }
.pet-sprite.sleep svg { animation: breathe 4s ease-in-out infinite; }
.pet-sprite.flip { transform: translateX(-50%) scaleX(-1); }
@keyframes bob { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-4px) } }
@keyframes breathe { 0%,100% { transform: scale(1,1) } 50% { transform: scale(1.02,.98) } }
@keyframes bounce { 0%,100% { transform: translateY(0) } 40% { transform: translateY(-10px) } }
@keyframes wiggle { 0%,100% { transform: rotate(0) } 25% { transform: rotate(-6deg) } 75% { transform: rotate(6deg) } }
.float-q { animation: floatq 1.2s ease-in-out infinite; }
@keyframes floatq { 0%,100% { opacity: .5 } 50% { opacity: 1 } }

.bubble-wrap { position: absolute; bottom: 118px; left: 50%; transform: translateX(-50%); width: 280px; z-index: 10; }
.bubble {
  background: #fff; color: #1e293b; border-radius: 12px; padding: 9px 13px;
  font-size: 13px; line-height: 1.5; position: relative;
  box-shadow: 0 4px 16px rgba(0,0,0,.25); word-break: break-word;
}
.bubble::after {
  content: ''; position: absolute; bottom: -7px; left: 50%; transform: translateX(-50%);
  border: 7px solid transparent; border-top-color: #fff; border-bottom: none;
}
.bubble-text.clamped {
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.bubble.expanded .bubble-text { max-height: 200px; overflow-y: auto; }
.bubble.expanded .bubble-text::-webkit-scrollbar { width: 4px; }
.bubble.expanded .bubble-text::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 2px; }
.bubble-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 6px; }
.bbtn {
  border: none; background: #eef2ff; color: #4338ca; font-size: 11px;
  border-radius: 6px; padding: 2px 8px; cursor: pointer; line-height: 1.6;
}
.bbtn:hover { background: #e0e7ff; }
.bbtn-x { background: #fee2e2; color: #b91c1c; }
.bbtn-x:hover { background: #fecaca; }
.quick-input input {
  width: 100%; box-sizing: border-box; background: #1e293b; color: #e2e8f0;
  border: 1px solid #6366f1; border-radius: 10px; padding: 8px 10px; font-size: 13px; outline: none;
}
</style>
