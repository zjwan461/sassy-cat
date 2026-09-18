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
          <button v-if="bubbleTruncated || bubbleExpanded || state === 'talk'" class="bbtn" @click.stop="openFullChat">💬 完整对话</button>
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
      :class="[state, { flip: facingLeft, happy: mood === 'happy', annoyed: mood === 'annoyed', dizzy: mood === 'dizzy' }]"
      @mousedown="onMouseDown"
      @click="onClick"
      @contextmenu.prevent="onContextMenu"
      @wheel.prevent="onWheel"
    >
      <svg viewBox="0 0 120 110" width="120" height="110">
        <path :d="tailPath" fill="none" stroke="#334155" stroke-width="8" stroke-linecap="round"/>
        <ellipse cx="60" cy="76" rx="34" ry="26" fill="#64748b"/>
        <path d="M36 38 L44 16 L56 34 Z" fill="#64748b"/>
        <path d="M84 38 L76 16 L64 34 Z" fill="#64748b"/>
        <path d="M40 33 L45 21 L51 31 Z" fill="#f9a8d4"/>
        <path d="M80 33 L75 21 L69 31 Z" fill="#f9a8d4"/>
        <circle cx="60" cy="46" r="26" fill="#64748b"/>
        <!-- 表情：开心（眯眼笑） -->
        <template v-if="mood === 'happy'">
          <path d="M46 42 q6 -4 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <path d="M62 42 q6 -4 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <path d="M52 54 q8 6 16 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
        </template>
        <!-- 表情：不满（斜眼） -->
        <template v-else-if="mood === 'annoyed'">
          <path d="M46 40 l12 4" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <path d="M74 40 l-12 4" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <circle cx="51" cy="45" r="3" fill="#1e293b"/>
          <circle cx="69" cy="45" r="3" fill="#1e293b"/>
          <path d="M54 56 q6 -2 12 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
        </template>
        <!-- 表情：头晕（螺旋眼） -->
        <template v-else-if="mood === 'dizzy'">
          <path d="M48 42 q3 -3 6 0 q3 3 6 0" stroke="#1e293b" stroke-width="2" fill="none" stroke-linecap="round" class="spin-eye"/>
          <path d="M64 42 q3 -3 6 0 q3 3 6 0" stroke="#1e293b" stroke-width="2" fill="none" stroke-linecap="round" class="spin-eye"/>
          <path d="M55 55 q5 3 10 0" stroke="#1e293b" stroke-width="2" fill="none" stroke-linecap="round"/>
        </template>
        <!-- 表情：撸猫中（享受） -->
        <template v-else-if="mood === 'purring'">
          <path d="M46 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <path d="M62 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <path d="M53 54 q7 5 14 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
          <text x="88" y="30" font-size="10" fill="#f472b6" class="float-heart">♥</text>
        </template>
        <!-- 默认表情 -->
        <template v-else-if="eyesClosed">
          <path d="M46 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
          <path d="M62 44 q6 5 12 0" stroke="#1e293b" stroke-width="3" fill="none" stroke-linecap="round"/>
        </template>
        <template v-else>
          <circle cx="51" cy="43" r="4" fill="#1e293b"/>
          <circle cx="69" cy="43" r="4" fill="#1e293b"/>
          <circle cx="52.5" cy="41.5" r="1.4" fill="#fff"/>
          <circle cx="70.5" cy="41.5" r="1.4" fill="#fff"/>
        </template>
        <path v-if="state === 'talk' && mood !== 'happy' && mood !== 'annoyed' && mood !== 'dizzy' && mood !== 'purring'" d="M55 54 q5 6 10 0 q-5 8 -10 0" fill="#be185d"/>
        <path v-else-if="mood !== 'happy' && mood !== 'annoyed' && mood !== 'dizzy' && mood !== 'purring'" d="M55 54 q5 4 10 0" stroke="#1e293b" stroke-width="2.4" fill="none" stroke-linecap="round"/>
        <path d="M30 48 h12 M31 55 l11 -3 M90 48 h-12 M89 55 l-11 -3" stroke="#1e293b" stroke-width="1.6" stroke-linecap="round"/>
        <text v-if="state === 'think'" x="90" y="16" font-size="16" fill="#a5b4fc" class="float-q">?</text>
        <text v-if="state === 'sleep'" x="86" y="18" font-size="13" fill="#94a3b8" class="float-q">z z z</text>
        <!-- 长按撸猫提示 -->
        <text v-if="longPressing && mood !== 'purring'" x="50" y="12" font-size="10" fill="#fbbf24" class="float-q">喵~</text>
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
const mood = ref('') // happy|annoyed|dizzy|purring
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
const longPressing = ref(false)
const clickCount = ref(0)
// 主窗口是否处于前台激活（由主进程推送 / 挂载时查询）：
// 激活时桌宠不再用气泡复述聊天内容，避免与主窗口重复、干扰正常使用
const mainActive = ref(false)

const bubbleActionsVisible = computed(() => {
  if (!bubbleText.value) return false
  if (bubbleOverflows.value || bubbleTruncated.value || bubbleExpanded.value) return true
  // AI 流式输出期间直接显示操作按钮，无需等 overflow 检测
  if (state.value === 'talk') return true
  return false
})

let timers = {}
let dragging = false
let longPressTimer = null
let moodTimer = null
let clickTimer = null

// ---------- 帧驱动 ----------
const eyesClosed = computed(() => {
  if (state.value === 'sleep') return true
  return frameIdx.value % 8 === 6 // 周期眨眼
})
const tailPath = computed(() => {
  // 尾巴轻微摆动
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
  // 获取当前位置和屏幕尺寸，限制移动范围
  window.petAPI.getPosition().then((pos) => {
    if (!pos) { setState('idle'); return }
    const screenW = window.screen.width
    const petW = 120 // SVG 宽度
    const margin = 20 // 安全边距
    // 计算可移动范围
    const maxLeft = -(pos.x - margin) // 向左最多走到 margin
    const maxRight = screenW - pos.x - petW - margin // 向右最多走到 screenW - margin
    // 随机目标距离，限制在安全范围内
    const maxDist = Math.min(240, Math.max(60, Math.min(Math.abs(maxLeft), Math.abs(maxRight))))
    const total = Math.round((Math.random() - 0.5) * 2 * maxDist)
    // 确保不越界
    const clampedTotal = Math.max(maxLeft, Math.min(maxRight, total))
    if (Math.abs(clampedTotal) < 10) { setState('idle'); scheduleNext(); return }
    facingLeft.value = clampedTotal < 0
    const step = clampedTotal / 12
    let moved = 0
    setState('walk')
    clearInterval(timers.walk)
    timers.walk = setInterval(() => {
      window.petAPI.moveDelta(step, 0)
      if (++moved >= 12) {
        clearInterval(timers.walk)
        setState('idle')
        scheduleNext()
      }
    }, 45)
  }).catch(() => { setState('idle') })
}

function scheduleNext() {
  clearTimeout(timers.next)
  timers.next = setTimeout(() => {
    if (state.value === 'idle') { Math.random() < 0.4 ? walkAround() : scheduleNext() }
  }, 4000 + Math.random() * 8000)
}

// ---------- 交互 ----------
function setMood(m, durationMs = 0) {
  clearTimeout(moodTimer)
  mood.value = m
  if (durationMs > 0) {
    moodTimer = setTimeout(() => {
      if (mood.value === m) mood.value = ''
    }, durationMs)
  }
}

function onMouseUp() {
  clearTimeout(longPressTimer)
  if (longPressing.value) {
    longPressing.value = false
    if (mood.value === 'purring') {
      setMood('happy', 2000)
      showBubble('好舒服喵～ 下次还要！ 😽', 2500)
    }
  }
}

function onClick() {
  if (dragMoved) return
  // 连击检测
  clickCount.value++
  clearTimeout(clickTimer)
  clickTimer = setTimeout(() => {
    if (clickCount.value >= 5) {
      // 连点5次以上：头晕
      setMood('dizzy', 3000)
      setState('react', 1200)
      showBubble('别戳了别戳了！本喵要晕了… 😵', 3000)
    } else if (clickCount.value >= 3) {
      // 连点3次：不满
      setMood('annoyed', 2500)
      setState('react', 1000)
      showBubble('喂！你当本喵是解压玩具吗？ 😾', 2500)
    } else {
      setState('react', 1000)
      if (Math.random() < 0.7) showBubble(QUICK_PHRASES[Math.floor(Math.random() * QUICK_PHRASES.length)], 2600)
    }
    clickCount.value = 0
  }, 400)
}

function onWheel(e) {
  // 滚轮：向上摸头（开心），向下戳（不满）
  if (state.value === 'drag') return
  if (e.deltaY < 0) {
    // 向上滚动：摸头
    setMood('happy', 1500)
    setState('react', 800)
    const phrases = ['喵～ 摸头好舒服！', '嘿嘿，再摸摸嘛～', '本喵允许你摸头！']
    showBubble(phrases[Math.floor(Math.random() * phrases.length)], 2000)
  } else {
    // 向下滚动：戳/推
    setMood('annoyed', 1500)
    setState('react', 600)
    const phrases = ['别推本喵！', '哼！讨厌！', '你干嘛！ 😾']
    showBubble(phrases[Math.floor(Math.random() * phrases.length)], 2000)
  }
}

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
// 记录上一次应用的窗口尺寸：尺寸未变化时跳过 IPC resize，
// 避免打字机高频调用导致窗口反复调整产生抖动
let lastAppliedSize = { h: 0, w: 0 }
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
  if (h === lastAppliedSize.h && w === lastAppliedSize.w) return
  lastAppliedSize = { h, w }
  window.petAPI.resize({ height: h, width: w })
}
async function runSync() {
  syncPending = false
  await nextTick()
  measureOverflow()
  // 溢出检测结果会切换操作按钮行的显隐，需再等一次渲染后再量高度，
  // 否则窗口高度少算按钮行，气泡顶部会被裁掉
  await nextTick()
  syncWindow()
}
// 注意：这里必须用 setTimeout 而不是 requestAnimationFrame——
// 桌宠窗口被其他窗口遮挡时 Electron 会暂停 rAF，导致窗口永不 resize、气泡被裁到窗口外不可见
function scheduleSync() {
  if (syncPending) return
  syncPending = true
  setTimeout(runSync, 0)
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

function showBubble(text, ms = 5000, kind = 'local') {
  // 记录气泡来源：chat（聊天内容，主窗口前台时不展示）| reminder（提醒，始终展示）| local（桌宠本地互动）
  bubbleKind = kind
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
// 当前展示内容的来源：chat | reminder | local（见 showBubble / onMainWindowStateChanged）
let bubbleKind = 'local'
function typewriteStart() {
  streamBuf = ''; streamTarget = ''
  clearInterval(typer)
  typer = setInterval(() => {
    if (streamBuf.length < streamTarget.length) {
      streamBuf = streamTarget.slice(0, Math.min(streamBuf.length + 2, BUBBLE_MAX_CHARS))
      bubbleText.value = streamBuf
      // 打字机期间持续同步窗口高度，保证气泡始终完整可见；
      // syncWindow 内部已做尺寸去重，未变化时不发起 resize，不会抖动
      scheduleSync()
    }
  }, 40)
}
function typewriteStop() {
  clearInterval(typer); typer = null
  // 打字结束后统一调整一次窗口尺寸
  scheduleSync()
}

// ---------- 主窗口激活联动 ----------
// 主窗口进入前台后，桌宠不再用气泡复述聊天内容（提醒 / 问候 / 本地互动气泡不受影响）。
// 过渡瞬间若正展示聊天气泡或处于思考动画，则立即收起并回到 idle。
function onMainWindowStateChanged(active) {
  const was = mainActive.value
  mainActive.value = !!active
  if (!mainActive.value || was) return
  if (bubbleKind !== 'chat') return
  typewriteStop()
  streamBuf = ''; streamTarget = ''
  if (bubbleText.value) hideBubble()
  if (state.value === 'talk' || state.value === 'think') { setState('idle'); scheduleNext() }
}

// ---------- 拖动（增量移动，主进程节流） ----------
let dragMoved = false
function onMouseDown(e) {
  if (e.button !== 0 || !window.petAPI) return
  // 长按检测（撸猫）
  longPressing.value = false
  clearTimeout(longPressTimer)
  longPressTimer = setTimeout(() => {
    if (!dragging && !dragMoved) {
      longPressing.value = true
      setMood('purring', 0) // 持续直到松手
      showBubble('呼噜噜… 再摸摸嘛～ 😻', 3000)
    }
  }, 600)
  // 拖动逻辑
  dragging = true
  dragMoved = false
  let lastX = e.screenX, lastY = e.screenY
  const moveHandler = (me) => {
    const ddx = me.screenX - lastX, ddy = me.screenY - lastY
    lastX = me.screenX; lastY = me.screenY
    if (Math.abs(ddx) + Math.abs(ddy) > 0) {
      dragMoved = true
      // 拖动时取消长按
      clearTimeout(longPressTimer)
      longPressing.value = false
      if (state.value !== 'drag') setState('drag')
      window.petAPI.moveDelta(ddx, ddy)
    }
  }
  const upHandler = () => {
    document.removeEventListener('mousemove', moveHandler)
    document.removeEventListener('mouseup', upHandler)
    clearTimeout(longPressTimer)
    dragging = false
    // 调用 onMouseUp 统一处理撸猫结束逻辑
    onMouseUp()
    if (dragMoved && state.value === 'drag') {
      setState('idle'); scheduleNext()
    }
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
    // 主窗口激活状态：挂载时查询一次，之后由主进程 push 更新
    window.petAPI.getMainWindowActive().then((v) => { mainActive.value = !!v })
    window.petAPI.onMainWindowState((data) => onMainWindowStateChanged(data && data.active))
  }
  connect()

  // 聊天内容：主窗口前台激活时直接忽略（内容已在主窗口展示），不改变桌宠状态也不弹气泡
  on('chat.started', () => {
    if (mainActive.value) return
    setState('think'); if (inputOpen.value) closeInput()
  })
  on('chat.delta', (p) => {
    if (mainActive.value) return
    if (state.value !== 'talk') { setState('talk'); typewriteStart(); bubbleKind = 'chat' }
    streamTarget += p.text
  })
  on('chat.completed', (p) => {
    if (mainActive.value) { typewriteStop(); streamBuf = ''; streamTarget = ''; setState('idle'); return }
    if (p.text && p.text.length >= streamTarget.length) streamTarget = p.text
    setTimeout(() => {
      typewriteStop()
      // 1.4s 缓冲期内主窗口可能已被激活：此时放弃气泡展示
      if (mainActive.value) { streamBuf = ''; streamTarget = ''; setState('idle'); scheduleNext(); return }
      if (streamTarget) {
        // 阅读时长随文本长度自适应（90ms/字，9s ~ 25s），超长截断由 showBubble 内部处理
        const ms = Math.min(25000, Math.max(9000, streamTarget.length * 90))
        showBubble(streamTarget, ms, 'chat')
      }
      setState('idle'); scheduleNext()
    }, 1400)
  })
  // ---------- 每日首次加载打招呼（服务端触发，属于主动问候，主窗口前台时也照常展示） ----------
  on('greeting.delta', (p) => {
    if (state.value !== 'talk') { setState('talk'); typewriteStart(); bubbleKind = 'reminder' }
    streamTarget += p.text
  })
  on('greeting.completed', (p) => {
    if (p.text && p.text.length >= streamTarget.length) streamTarget = p.text
    setTimeout(() => {
      typewriteStop()
      if (streamTarget) {
        // 招呼语文案较短，按 140ms/字放缓阅读节奏（9s ~ 25s）
        const ms = Math.min(25000, Math.max(9000, streamTarget.length * 140))
        showBubble(streamTarget, ms, 'reminder')
      }
      setState('idle'); scheduleNext()
    }, 1400)
  })
  on('chat.error', () => {
    typewriteStop()
    setState('idle')
    if (mainActive.value) return // 主窗口前台时错误已在主窗口呈现，桌宠不再提示
    showBubble('呜…出了点小状况 😿', 4000, 'chat')
  })
  on('pet.command', (p) => {
    if (p.action === 'think') setState('think')
    else if (p.action === 'remind') { setState('remind', p.durationMs || 8000); if (p.text) showBubble(p.text, p.durationMs || 8000, 'reminder') }
    else if (p.action === 'wave') setState('react', 1200)
    else if (p.action === 'sleep') setState('sleep')
    else if (p.action === 'idle' && !dragging) { setState('idle'); scheduleNext() }
  })
  // 提醒类消息：无论主窗口是否前台，均照常提示
  on('proactive.message', (p) => { setState('remind', 8000); showBubble(p.text, 8000, 'reminder') })
  on('proactive.reminder', (p) => {
    const ms = p.durationMs || 8000
    setState('remind', ms)
    showBubble(p.text, ms, 'reminder')
  })
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
.pet-sprite.happy svg { animation: purr .5s ease-in-out infinite; }
.pet-sprite.annoyed svg { animation: shake .3s 2; }
.pet-sprite.dizzy svg { animation: sway .6s ease-in-out infinite; }
@keyframes bob { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-4px) } }
@keyframes breathe { 0%,100% { transform: scale(1,1) } 50% { transform: scale(1.02,.98) } }
@keyframes bounce { 0%,100% { transform: translateY(0) } 40% { transform: translateY(-10px) } }
@keyframes wiggle { 0%,100% { transform: rotate(0) } 25% { transform: rotate(-6deg) } 75% { transform: rotate(6deg) } }
@keyframes purr { 0%,100% { transform: scale(1,1) } 50% { transform: scale(1.04,.96) } }
@keyframes shake { 0%,100% { transform: translateX(0) } 25% { transform: translateX(-3px) } 75% { transform: translateX(3px) } }
@keyframes sway { 0%,100% { transform: rotate(0) } 25% { transform: rotate(-8deg) } 75% { transform: rotate(8deg) } }
.float-q { animation: floatq 1.2s ease-in-out infinite; }
@keyframes floatq { 0%,100% { opacity: .5 } 50% { opacity: 1 } }
.float-heart { animation: floatHeart 1.4s ease-in-out infinite; }
@keyframes floatHeart { 0%,100% { opacity: .4; transform: translateY(0) } 50% { opacity: 1; transform: translateY(-4px) } }
.spin-eye { animation: spinEye 0.6s linear infinite; transform-origin: center; }
@keyframes spinEye { 0% { transform: rotate(0deg) } 100% { transform: rotate(360deg) } }

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
