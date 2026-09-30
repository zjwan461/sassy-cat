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

    <!-- 桌宠本体：统一渲染入口（SVG / spritesheet 由 PetSprite 按 currentRenderer 切换） -->
    <div
      ref="spriteRef"
      class="pet-sprite"
      :class="{ flip: facingLeft, spritesheet: isSpritesheet }"
      @mousedown="onMouseDown"
      @click="onClick"
      @contextmenu.prevent="onContextMenu"
      @wheel.prevent="onWheel"
    >
      <PetSprite
        :state="state"
        :mood="mood"
        :facing-left="facingLeft"
        @complete="onAnimComplete"
      />
      <SpriteOverlay :state="state" :mood="mood" :long-pressing="longPressing" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useAgentSocket, setClient } from '../../src/composables/useAgentSocket'
import PetSprite from './sprite/PetSprite.vue'
import SpriteOverlay from './sprite/SpriteOverlay.vue'
import { currentRenderer, RENDERER_SPRITESHEET } from './sprite/config'
import { fallbackToSvg } from './sprite/loadState'
import { useSpritePreload } from './sprite/useSpritePreload'

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

// ---------- 渲染器选择 ----------
// spritesheet 模式下关闭派生动效类（帧内已含动作，避免帧动画 + CSS 动画双重叠加）
const isSpritesheet = computed(() => currentRenderer.value === RENDERER_SPRITESHEET)

// 非循环动画（react 等）播放完成的契约回调：
// 状态回退兜底已由 setState(holdMs) 的定时器负责，此处仅保留事件接线位
function onAnimComplete() {}

// ---------- 状态机 ----------
function setState(s, holdMs = 0) {
  state.value = s
  if (holdMs) {
    clearTimeout(timers.hold)
    timers.hold = setTimeout(() => {
      if (state.value === s) setState('idle')
    }, holdMs)
  }
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
  if (state.value === 'talk' || state.value === 'think') setState('idle')
}

// ---------- 拖动（窗口位移由主进程按系统光标驱动） ----------
// 关键：渲染层 MouseEvent.screenX 会随被拖动的窗口一起变化。若据此计算增量再移动窗口，
// 二者互相耦合——窗口移到新位置后，同一物理位置的光标会算出被反向抵消的增量，
// 表现为拖动抖动、甚至反向移动（主窗口流式输出时气泡频繁 resize 会放大该现象）。
// 因此这里只做「是否开始拖动」的判定与状态切换，实际位移交给主进程轮询系统光标完成。
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
  // 拖动判定
  dragging = true
  dragMoved = false
  const startX = e.screenX, startY = e.screenY
  const moveHandler = (me) => {
    // 3px 死区：过滤点击时的细微抖动，避免把单击误判成拖动
    if (Math.abs(me.screenX - startX) + Math.abs(me.screenY - startY) < 3) return
    // 拖动时取消长按
    clearTimeout(longPressTimer)
    longPressing.value = false
    if (!dragMoved) {
      dragMoved = true
      window.petAPI.dragStart()
    }
    if (state.value !== 'drag') setState('drag')
  }
  const upHandler = () => {
    document.removeEventListener('mousemove', moveHandler)
    document.removeEventListener('mouseup', upHandler)
    clearTimeout(longPressTimer)
    dragging = false
    if (dragMoved) window.petAPI.dragEnd()
    // 调用 onMouseUp 统一处理撸猫结束逻辑
    onMouseUp()
    if (dragMoved && state.value === 'drag') setState('idle')
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
  // 拖动过程中强制保持可交互，避免光标短暂移出宠物/气泡范围时切回穿透导致丢失 mouseup
  const need = inside || inputOpen.value || dragging
  if (need !== hoverInside) {
    hoverInside = need
    window.petAPI.setInteractive(need)
  }
}

// ---------- 生命周期 ----------
onMounted(async () => {
  setState('idle')
  document.addEventListener('mousemove', onDocMouseMove)

  // 预加载分级：仅在 spritesheet 渲染器下预载位图（SVG 模式无需）；
  // 任一资源加载失败 -> 自动降级回 SVG（响应式，组件自动重渲染）
  if (currentRenderer.value === RENDERER_SPRITESHEET) {
    try { await useSpritePreload().preload() }
    catch (err) { fallbackToSvg('spritesheet preload failed: ' + (err && err.message)) }
  }
  // 空闲时加载 P1 低频资源（失败忽略，不影响主流程）
  const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 1200))
  idle(() => { useSpritePreload().preloadLazy().catch(() => {}) })

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
  // 轮次事件已改为广播给所有聊天客户端：桌宠只响应“当前激活会话”（sock.sessionId），
  // 忽略切走后仍在后台进行的其他会话，避免气泡显示非当前对话的内容
  on('chat.started', (p) => {
    if (p.sessionId && p.sessionId !== sock.sessionId) return
    if (mainActive.value) return
    setState('think'); if (inputOpen.value) closeInput()
  })
  on('chat.delta', (p) => {
    if (p.sessionId && p.sessionId !== sock.sessionId) return
    if (mainActive.value) return
    if (state.value !== 'talk') { setState('talk'); typewriteStart(); bubbleKind = 'chat' }
    streamTarget += p.text
  })
  on('chat.completed', (p) => {
    if (p.sessionId && p.sessionId !== sock.sessionId) return
    if (mainActive.value) { typewriteStop(); streamBuf = ''; streamTarget = ''; setState('idle'); return }
    if (p.text && p.text.length >= streamTarget.length) streamTarget = p.text
    setTimeout(() => {
      typewriteStop()
      // 1.4s 缓冲期内主窗口可能已被激活：此时放弃气泡展示
      if (mainActive.value) { streamBuf = ''; streamTarget = ''; setState('idle'); return }
      if (streamTarget) {
        // 阅读时长随文本长度自适应（90ms/字，9s ~ 25s），超长截断由 showBubble 内部处理
        const ms = Math.min(25000, Math.max(9000, streamTarget.length * 90))
        showBubble(streamTarget, ms, 'chat')
      }
      setState('idle')
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
      setState('idle')
    }, 1400)
  })
  on('chat.error', (p) => {
    if (p.sessionId && p.sessionId !== sock.sessionId) return
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
    else if (p.action === 'idle' && !dragging) setState('idle')
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
  if (dragging) { dragging = false; window.petAPI && window.petAPI.dragEnd() }
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
.pet-sprite.flip { transform: translateX(-50%) scaleX(-1); }
/* 说明：状态/心情的 CSS 关键帧动画与 overlay 动效已内聚到对应渲染器组件
   （见 sprite/SvgSpriteRenderer.vue、sprite/SpriteOverlay.vue），
   避免 scoped 样式跨组件穿透问题，并使动画作用于 svg 元素而非持有
   translateX(-50%) 的容器（防止水平居中 transform 被动画覆盖）。 */
/* spritesheet 模式下禁用派生 CSS 动画（帧内已含动作）——防御性兜底 */
.pet-sprite.spritesheet svg,
.pet-sprite.spritesheet .css-sprite { animation: none !important; }

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
