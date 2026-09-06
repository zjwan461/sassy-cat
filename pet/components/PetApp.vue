<template>
  <div class="pet-root">
    <!-- 气泡 / 快捷输入 -->
    <div v-if="bubbleText || inputOpen" class="bubble-wrap">
      <div v-if="bubbleText && !inputOpen" class="bubble" @click="openInput">
        {{ bubbleText }}
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

const PET_BASE_H = 150, EXPANDED_H = 220
const QUICK_PHRASES = [
  '哼，找本喵干嘛😾', '摸头要付费的！', '喵呜～（其实很开心）',
  '有事启奏，无事退朝。', '本喵今天心情不错，准你撸一下。'
]

const state = ref('idle') // idle|walk|drag|react|think|talk|sleep|remind
const bubbleText = ref('')
const inputOpen = ref(false)
const quickDraft = ref('')
const facingLeft = ref(false)
const frameIdx = ref(0)
const spriteRef = ref(null)
const quickInputRef = ref(null)

let timers = {}
let bubbleTimer = null
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

function onMenuAction({ action }) {
  if (action === 'chat') window.petAPI.showChat()
  else if (action === 'input') inputOpen.value ? closeInput() : openInput()
  else if (action === 'hide') window.petAPI.hideSelf()
}

async function openInput() {
  inputOpen.value = true
  bubbleText.value = ''
  window.petAPI && window.petAPI.resize(EXPANDED_H)
  await nextTick()
  quickInputRef.value && quickInputRef.value.focus()
}

function closeInput() {
  inputOpen.value = false
  quickDraft.value = ''
  window.petAPI && window.petAPI.resize(PET_BASE_H)
}

function sendQuick() {
  const text = quickDraft.value.trim()
  if (!text) return
  quickDraft.value = ''
  send('chat.send', { sessionId: sock.sessionId, content: text })
  setState('think')
}

// ---------- 气泡打字机 ----------
let streamBuf = ''
let streamTarget = ''
let typer = null
function typewriteStart() {
  streamBuf = ''; streamTarget = ''
  clearInterval(typer)
  typer = setInterval(() => {
    if (streamBuf.length < streamTarget.length) {
      streamBuf = streamTarget.slice(0, streamBuf.length + 2)
      bubbleText.value = streamBuf
    }
  }, 40)
}
function typewriteStop() { clearInterval(typer); typer = null }

function showBubble(text, ms = 5000) {
  bubbleText.value = text
  clearTimeout(bubbleTimer)
  bubbleTimer = setTimeout(() => { bubbleText.value = '' }, ms)
}

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
  const r = el.getBoundingClientRect()
  const pad = 14
  const inside = e.clientX >= r.left - pad && e.clientX <= r.right + pad &&
                 e.clientY >= r.top - pad && e.clientY <= r.bottom + pad
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
      const text = streamTarget.length > 80 ? streamTarget.slice(0, 80) + '…' : streamTarget
      if (text) showBubble(text, 9000)
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

.bubble-wrap { position: absolute; bottom: 120px; left: 50%; transform: translateX(-50%); width: 212px; z-index: 10; }
.bubble {
  background: #fff; color: #1e293b; border-radius: 12px; padding: 9px 13px;
  font-size: 13px; line-height: 1.5; position: relative; cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,.25); word-break: break-word;
  max-height: 140px; overflow: hidden;
}
.bubble::after {
  content: ''; position: absolute; bottom: -7px; left: 50%; transform: translateX(-50%);
  border: 7px solid transparent; border-top-color: #fff; border-bottom: none;
}
.quick-input input {
  width: 100%; box-sizing: border-box; background: #1e293b; color: #e2e8f0;
  border: 1px solid #6366f1; border-radius: 10px; padding: 8px 10px; font-size: 13px; outline: none;
}
</style>
