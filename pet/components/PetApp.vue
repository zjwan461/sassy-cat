<template>
  <div class="pet-root" :style="{ '--pet-scale': petScale }">
    <!-- 气泡 / 快捷输入 -->
    <div v-if="bubbleText || inputOpen" ref="bubbleWrapRef" class="bubble-wrap">
      <div
        v-if="bubbleText && !inputOpen"
        class="bubble"
        :class="{ expanded: bubbleExpanded }"
        :data-kind="bubbleKind"
        @mouseenter="onBubbleEnter"
        @mouseleave="onBubbleLeave"
      >
        <div class="bubble-meta">
          <span class="meta-icon">{{ bubbleKind === 'reminder' ? '⏰' : bubbleKind === 'chat' ? '🐱' : '✦' }}</span>
          <span class="meta-text">{{ bubbleKind === 'reminder' ? '提醒' : bubbleKind === 'chat' ? '优墨' : '本喵' }}</span>
          <span v-if="state === 'talk'" class="meta-typing"><i></i><i></i><i></i></span>
          <button class="bubble-close" type="button" title="关闭" @click.stop="hideBubble">×</button>
        </div>
        <div ref="bubbleTextRef" class="bubble-text" :class="{ clamped: !bubbleExpanded }">{{ bubbleText }}</div>
        <div v-if="bubbleActionsVisible" class="bubble-actions">
          <button v-if="!bubbleExpanded && bubbleOverflows" class="bbtn" @click.stop="expandBubble">▾ 展开</button>
          <button v-if="bubbleExpanded" class="bbtn" @click.stop="collapseBubble">▴ 收起</button>
          <button v-if="bubbleTruncated || bubbleExpanded || state === 'talk'" class="bbtn" @click.stop="openFullChat">完整对话 →</button>
        </div>
      </div>
      <div v-if="inputOpen" class="quick-input">
        <textarea
          ref="quickInputRef"
          v-model="quickDraft"
          rows="2"
          placeholder="跟本喵说点什么…"
          @keydown.enter.exact.prevent="sendQuick"
          @keydown.esc="closeInput"
        ></textarea>
        <div class="quick-actions">
          <span class="quick-hint">Enter 发送 · Esc 关闭</span>
          <button class="quick-send" type="button" :disabled="!quickDraft.trim()" @click="sendQuick">发送</button>
        </div>
      </div>
    </div>

    <!-- 桌宠本体：统一渲染入口（SVG / spritesheet 由 PetSprite 按 currentRenderer 切换） -->
    <div
      ref="spriteRef"
      class="pet-sprite"
      :class="{ flip: facingLeft, spritesheet: isSpritesheet, hovered, 'trick-flip': trick === 'flip', 'trick-roll': trick === 'roll' }"
      @mousedown="onMouseDown"
      @click="onClick"
      @dblclick="onDoubleClick"
      @mouseenter="onPetEnter"
      @mouseleave="onPetLeave"
      @contextmenu.prevent="onContextMenu"
      @wheel.prevent="onWheel"
    >
      <PetSprite
        :state="state"
        :mood="mood"
        :facing-left="facingLeft"
        :hovered="hovered"
        :action="idleAction"
        @complete="onAnimComplete"
      />
      <SpriteOverlay :state="state" :mood="mood" :long-pressing="longPressing" :trick="trick" />
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
// 鼠标悬停在猫身上：耳朵竖起、眼睛发亮（渲染器负责具体形变）
const hovered = ref(false)
// idle 时的随机小动作：look | stretch | groom | yawn（纯 CSS 动画，不改变 state）
const idleAction = ref('')
// 表演类动作（与状态机解耦）：目前支持 flip=翻跟斗 / roll=打滚
const trick = ref('')
let trickTimer = null
// 外观：整体缩放 + 勿扰状态（主进程推送，渲染层只做展示）
const petScale = ref(1)
const dndActive = ref(false)
let offAppearance = null
let appearanceTimer = null

function applyAppearance(data) {
  if (!data) return
  if (Number.isFinite(Number(data.size))) {
    petScale.value = Math.min(1.3, Math.max(0.75, Number(data.size)))
  }
  dndActive.value = !!data.dndActive
  if (dndActive.value && bubbleKind.value !== 'local') {
    typewriteStop()
    hideBubble()
  }
}
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
let pressStartedAt = 0
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
  // 任何"活跃状态"都重置休眠倒计时；sleep 自身不再重置，避免自我续期
  if (s !== 'sleep') resetSleepTimer()
  if (holdMs) {
    clearTimeout(timers.hold)
    timers.hold = setTimeout(() => {
      if (state.value === s) setState('idle')
    }, holdMs)
  }
}

// ---------- idle 行为调度 ----------
// 桌宠长期停在 idle 会显得"死"。这里用两个独立节奏让它活起来：
//   · 每 8~18s 随机做一个小动作（张望 / 伸懒腰 / 舔爪 / 打哈欠）
//   · 每 35~70s 在桌面上小步走一段（窗口由主进程按屏幕边界钳制）
//   · 120s 没有任何互动就睡着，鼠标靠近或点击会把它叫醒
const IDLE_ACTIONS = ['look', 'stretch', 'groom', 'yawn']
const SLEEP_AFTER_MS = 120000
let idleTimer = null
let wanderTimer = null
let sleepTimer = null
let actionTimer = null
let wandering = false

function clearIdleAction() {
  clearTimeout(actionTimer)
  actionTimer = null
  idleAction.value = ''
}

function scheduleIdleAction() {
  clearTimeout(idleTimer)
  const wait = 8000 + Math.random() * 10000
  idleTimer = setTimeout(() => {
    if (state.value === 'idle' && !hovered.value && !bubbleText.value && !inputOpen.value && !dragging) {
      // 偶尔不满足于小动作，直接翻个跟斗或打个滚
      if (Math.random() < 0.12) {
        performTrick(Math.random() < 0.5 ? 'flip' : 'roll')
      } else {
        const action = IDLE_ACTIONS[Math.floor(Math.random() * IDLE_ACTIONS.length)]
        idleAction.value = action
        clearTimeout(actionTimer)
        actionTimer = setTimeout(() => {
          if (idleAction.value === action) idleAction.value = ''
        }, 1900)
      }
    }
    scheduleIdleAction()
  }, wait)
}

function resetSleepTimer() {
  clearTimeout(sleepTimer)
  sleepTimer = setTimeout(() => {
    if (state.value === 'idle' && !hovered.value && !bubbleText.value && !inputOpen.value && !dragging) {
      clearIdleAction()
      setState('sleep')
    }
  }, SLEEP_AFTER_MS)
}

function wake() {
  if (state.value === 'sleep') setState('idle')
  resetSleepTimer()
}

// ---------- 表演动作：翻跟斗 ----------
// 与状态机解耦：不改 state（避免表情/气泡状态被打断），只在容器上叠加一段
// 旋转+腾空的 CSS 动画；spritesheet 渲染器也能一起翻。
function performTrick(name = 'flip') {
  if (state.value === 'drag' || dragging) return
  wake()
  clearIdleAction()
  clearTimeout(trickTimer)
  // 先清空再下一拍赋值：连续触发时能重启动画，而不是因为 class 没变被浏览器忽略
  trick.value = ''
  setTimeout(() => {
    trick.value = name
    trickTimer = setTimeout(() => { trick.value = '' }, 1150)
  }, 16)
  if (Math.random() < 0.6) {
    showBubble(name === 'roll' ? '看本喵打个滚！ 🎪' : '看本喵翻个跟斗！ 🤸', 2200)
  }
}

function onPetEnter() {
  hovered.value = true
  wake()
}
function onPetLeave() {
  hovered.value = false
}

// ---------- 自主走动 ----------
// 只做水平小步移动：窗口位移交给主进程（渲染层 screenX 会随窗口漂移，不能自己算），
// 主进程负责按当前显示器工作区钳制，返回 moved=false 说明到边了，立即停下。
let wanderStepTimer = null
async function maybeWander() {
  if (wandering) return
  if (state.value !== 'idle' || hovered.value || bubbleText.value || inputOpen.value || dragging) return
  if (!window.petAPI || typeof window.petAPI.moveBy !== 'function') return
  wandering = true
  const dir = Math.random() < 0.5 ? -1 : 1
  facingLeft.value = dir < 0
  setState('walk')
  const steps = 16
  for (let i = 0; i < steps; i++) {
    let res = null
    try {
      res = await window.petAPI.moveBy({ dx: dir * 3, dy: 0 })
    } catch { /* 移动失败就停在原地，不影响其它逻辑 */ }
    if (!res || res.moved === false) break
    await new Promise((r) => { wanderStepTimer = setTimeout(r, 62) })
    if (state.value !== 'walk' || dragging || hovered.value) break
  }
  clearTimeout(wanderStepTimer)
  if (state.value === 'walk') setState('idle')
  wandering = false
}

function scheduleWander() {
  clearTimeout(wanderTimer)
  const wait = 35000 + Math.random() * 35000
  wanderTimer = setTimeout(() => {
    maybeWander()
    scheduleWander()
  }, wait)
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
    // 撸得够久（≥1s）就奖励一个跟斗
    if (pressStartedAt && Date.now() - pressStartedAt >= 1000) {
      performTrick('flip')
    }
  }
  pressStartedAt = 0
}

function onClick(e) {
  if (dragMoved) return
  // 双击的第一下也会派发 click；这里按 detail 忽略，交给 onDoubleClick 处理
  if (e && e.detail > 1) return
  wake()
  clearIdleAction()
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

function onDoubleClick() {
  // 双击 = 打开主窗口聊天：比"点五次晕倒"更符合直觉的快捷入口
  clearTimeout(clickTimer)
  clickCount.value = 0
  clearIdleAction()
  if (window.petAPI) window.petAPI.showChat()
}

function onWheel(e) {
  // 滚轮：向上摸头（开心），向下戳（不满）
  if (state.value === 'drag') return
  wake()
  clearIdleAction()
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
    { label: '🐾 散散步', action: 'walk' },
    { label: '🤸 翻个跟斗', action: 'flip' },
    { label: '🎪 打个滚', action: 'roll' },
    { label: state.value === 'sleep' ? '☀️ 叫醒它' : '😴 打个盹', action: 'sleep' },
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
  else if (action === 'walk') { maybeWander() }
  else if (action === 'flip') { performTrick('flip') }
  else if (action === 'roll') { performTrick('roll') }
  else if (action === 'sleep') {
    if (state.value === 'sleep') wake()
    else { clearIdleAction(); setState('sleep') }
  }
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
  // 勿扰时段只拦截提醒/聊天类气泡；用户主动交互（local）仍然响应
  if (dndActive.value && kind !== 'local') return
  // 记录气泡来源：chat（聊天内容，主窗口前台时不展示）| reminder（提醒，始终展示）| local（桌宠本地互动）
  bubbleKind.value = kind
  wake()
  clearIdleAction()
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
const bubbleKind = ref('local')
function typewriteStart() {
  // 勿扰时段：聊天/提醒内容不进入打字机，避免绕过 showBubble 守卫
  if (dndActive.value && bubbleKind.value !== 'local') {
    streamBuf = ''
    streamTarget = ''
    return
  }
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
  if (bubbleKind.value !== 'chat') return
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
  wake()
  clearIdleAction()
  wandering = false
  // 长按检测（撸猫）
  longPressing.value = false
  pressStartedAt = Date.now()
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
  const downAt = Date.now()
  let lastX = startX, lastY = startY
  const moveHandler = (me) => {
    lastX = me.screenX
    lastY = me.screenY
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
    // 甩出去的一下（拖了 ≥70px 且动作较快）落地后翻个跟斗，像被扔出去又稳稳落地
    const distance = Math.hypot(lastX - startX, lastY - startY)
    if (dragMoved && distance >= 70 && Date.now() - downAt <= 1600) {
      performTrick('flip')
    }
    setTimeout(() => { dragMoved = false }, 50)
  }
  document.addEventListener('mousemove', moveHandler)
  document.addEventListener('mouseup', upHandler)
}

// ---------- 鼠标穿透控制 ----------
let hoverInside = true
function onDocMouseMove(e) {
  const el = spriteRef.value
  if (!el) return
  const pad = 14
  const r = el.getBoundingClientRect()
  const petInside = e.clientX >= r.left - pad && e.clientX <= r.right + pad &&
                    e.clientY >= r.top - pad && e.clientY <= r.bottom + pad
  let inside = petInside
  // 气泡区域同样需要命中（悬停暂停倒计时、展开后可滚动/点按钮）
  if (!inside) {
    const bw = bubbleWrapRef.value
    if (bw && (bubbleText.value || inputOpen.value)) {
      const b = bw.getBoundingClientRect()
      inside = e.clientX >= b.left && e.clientX <= b.right &&
               e.clientY >= b.top && e.clientY <= b.bottom
    }
  }
  // 悬停态：只在进出边界时切换，避免每帧触发 wake/清理动作
  if (petInside !== hovered.value) {
    hovered.value = petInside
    if (petInside) {
      wake()
      clearIdleAction()
    }
  }
  if (!window.petAPI) return
  // 拖动过程中强制保持可交互，避免光标短暂移出宠物/气泡范围时切回穿透导致丢失 mouseup
  const need = inside || inputOpen.value || dragging
  if (need !== hoverInside) {
    hoverInside = need
    window.petAPI.setInteractive(need)
  }
}

// ---------- 生命周期 ----------
// 调试/截图入口：pet.html?state=sleep&mood=happy&action=stretch&hovered=1
// 仅读取 URL 参数，不改变生产行为（正常启动没有这些参数）
function applyDebugParams() {
  try {
    const qp = new URLSearchParams(window.location.search)
    if (qp.get('state')) state.value = qp.get('state')
    if (qp.get('mood')) mood.value = qp.get('mood')
    if (qp.get('action')) idleAction.value = qp.get('action')
    if (qp.get('hovered') === '1') hovered.value = true
    if (qp.get('trick')) trick.value = qp.get('trick')
    if (qp.get('bubble')) showBubble(qp.get('bubble'), 600000, qp.get('kind') || 'chat')
    if (qp.get('input') === '1') openInput()
  } catch { /* 忽略非法参数 */ }
}

onMounted(async () => {
  setState('idle')
  // 外观：尺寸 / 勿扰状态由主进程配置决定
  try {
    applyAppearance(await window.petAPI?.getAppearance?.())
  } catch { /* 浏览器预览环境没有外观 API */ }
  if (window.petAPI?.onAppearance) offAppearance = window.petAPI.onAppearance(applyAppearance)
  // 勿扰时段会随时间自然进入/退出，定时刷新一次主进程计算出的状态
  appearanceTimer = setInterval(async () => {
    try {
      applyAppearance(await window.petAPI?.getAppearance?.())
    } catch { /* 忽略刷新失败 */ }
  }, 60000)
  document.addEventListener('mousemove', onDocMouseMove)
  scheduleIdleAction()
  scheduleWander()
  resetSleepTimer()
  applyDebugParams()

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
    if (state.value !== 'talk') { setState('talk'); typewriteStart(); bubbleKind.value = 'chat' }
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
    if (state.value !== 'talk') { setState('talk'); typewriteStart(); bubbleKind.value = 'reminder' }
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
  if (typeof offAppearance === 'function') offAppearance()
  clearInterval(appearanceTimer)
  if (dragging) { dragging = false; window.petAPI && window.petAPI.dragEnd() }
  Object.values(timers).forEach((t) => { clearInterval(t); clearTimeout(t) })
  clearTimeout(bubbleTimer)
  clearTimeout(idleTimer)
  clearTimeout(wanderTimer)
  clearTimeout(sleepTimer)
  clearTimeout(actionTimer)
  clearTimeout(wanderStepTimer)
  clearTimeout(trickTimer)
  typewriteStop()
  document.removeEventListener('mousemove', onDocMouseMove)
})
</script>

<style scoped>
.pet-root { position: relative; width: 100vw; height: 100vh; background: transparent; }
.pet-sprite {
  position: absolute; bottom: 4px; left: 50%;
  transform: translateX(-50%) scale(var(--pet-scale, 1));
  transform-origin: 50% 88%;
  cursor: grab;
  transition: transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1), filter 0.22s ease;
  filter: drop-shadow(0 6px 12px rgba(0, 0, 0, 0.28));
}
.pet-sprite.hovered {
  transform: translateX(-50%) scale(calc(var(--pet-scale, 1) * 1.025));
  filter: drop-shadow(0 9px 18px rgba(0, 0, 0, 0.34));
}
.pet-sprite.drag { cursor: grabbing; }
.pet-sprite.flip { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)); }
.pet-sprite.flip.hovered { transform: translateX(-50%) scaleX(-1) scale(calc(var(--pet-scale, 1) * 1.025)); }

/* 表演：翻跟斗 / 打滚（整只猫，尺寸随 --pet-scale 缩放） */
.pet-sprite.trick-flip { animation: pet-somersault 1.05s cubic-bezier(0.3, 0.7, 0.4, 1); }
.pet-sprite.flip.trick-flip { animation: pet-somersault-flipped 1.05s cubic-bezier(0.3, 0.7, 0.4, 1); }
.pet-sprite.trick-roll { animation: pet-roll 1.15s cubic-bezier(0.3, 0.7, 0.4, 1); }
.pet-sprite.flip.trick-roll { animation: pet-roll-flipped 1.15s cubic-bezier(0.3, 0.7, 0.4, 1); }

@keyframes pet-somersault {
  0%   { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(0) rotate(0deg); }
  45%  { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(-30px) rotate(180deg); }
  90%  { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(2px) rotate(360deg); }
  100% { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(0) rotate(360deg); }
}

@keyframes pet-somersault-flipped {
  0%   { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(0) rotate(0deg); }
  45%  { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(-30px) rotate(-180deg); }
  90%  { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(2px) rotate(-360deg); }
  100% { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(0) rotate(-360deg); }
}

@keyframes pet-roll {
  0%   { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(0) rotate(0deg); }
  45%  { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(-10px) rotate(200deg); }
  75%  { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(0) rotate(360deg); }
  100% { transform: translateX(-50%) scale(var(--pet-scale, 1)) translateY(0) rotate(360deg); }
}

@keyframes pet-roll-flipped {
  0%   { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(0) rotate(0deg); }
  45%  { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(-10px) rotate(-200deg); }
  75%  { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(0) rotate(-360deg); }
  100% { transform: translateX(-50%) scaleX(-1) scale(var(--pet-scale, 1)) translateY(0) rotate(-360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .pet-sprite.trick-flip,
  .pet-sprite.trick-roll { animation: none; }
}
/* 说明：状态/心情的 CSS 关键帧动画与 overlay 动效已内聚到对应渲染器组件
   （见 sprite/SvgSpriteRenderer.vue、sprite/SpriteOverlay.vue），
   避免 scoped 样式跨组件穿透问题，并使动画作用于 svg 元素而非持有
   translateX(-50%) 的容器（防止水平居中 transform 被动画覆盖）。 */
/* spritesheet 模式下禁用派生 CSS 动画（帧内已含动作）——防御性兜底 */
.pet-sprite.spritesheet svg,
.pet-sprite.spritesheet .css-sprite { animation: none !important; }

/* 气泡：不用纯白，改成与主窗口品牌瓦片同源的「月光纸」——
   在任意桌面壁纸上都有清晰边界，又不会像系统提示框那样刺眼 */
.bubble-wrap { position: absolute; bottom: 118px; left: 50%; transform: translateX(-50%); width: 280px; z-index: 10; }
.bubble {
  background: linear-gradient(170deg, #FDF6E8 0%, #F7EAD2 100%);
  color: #2C2113; border-radius: 14px; padding: 8px 12px 10px;
  font-size: 13px; line-height: 1.6; position: relative;
  border: 1px solid rgba(239, 168, 76, 0.35);
  box-shadow: 0 10px 30px -10px rgba(0, 0, 0, .55), 0 2px 6px rgba(0, 0, 0, .18);
  word-break: break-word;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei UI', 'PingFang SC', sans-serif;
}
/* 来源色条：聊天=琥珀，提醒=金色，本地互动=中性 */
.bubble[data-kind="chat"] { border-left: 3px solid rgba(239, 168, 76, 0.75); }
.bubble[data-kind="reminder"] { border-left: 3px solid #D9A93F; }
.bubble[data-kind="local"] { border-left: 3px solid rgba(150, 120, 80, 0.35); }

.bubble-meta {
  display: flex; align-items: center; gap: 5px;
  height: 16px; margin-bottom: 3px;
  font-size: 10.5px; font-weight: 600; letter-spacing: .02em;
  color: rgba(122, 88, 40, 0.85);
  user-select: none;
}
.meta-icon { font-size: 11px; line-height: 1; }
.meta-text { white-space: nowrap; }
.meta-typing { display: inline-flex; align-items: center; gap: 2px; margin-left: 2px; }
.meta-typing i {
  width: 3px; height: 3px; border-radius: 50%;
  background: rgba(150, 105, 45, 0.7);
  animation: typing-dot 1s ease-in-out infinite;
}
.meta-typing i:nth-child(2) { animation-delay: .15s; }
.meta-typing i:nth-child(3) { animation-delay: .3s; }
@keyframes typing-dot { 0%, 100% { opacity: .25; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-1px); } }

.bubble-close {
  margin-left: auto;
  width: 18px; height: 18px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border: none; border-radius: 50%;
  background: transparent; color: rgba(122, 88, 40, 0.55);
  font-size: 15px; line-height: 1; cursor: pointer;
  opacity: .55; transition: opacity .15s, background .15s, color .15s;
}
.bubble:hover .bubble-close { opacity: 1; }
.bubble-close:hover { background: rgba(180, 120, 40, 0.14); color: #7A4A22; }

.bubble::after {
  content: ''; position: absolute; bottom: -7px; left: 50%; transform: translateX(-50%);
  border: 7px solid transparent; border-top-color: #F7EAD2; border-bottom: none;
}
.bubble-text.clamped {
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.bubble.expanded .bubble-text { max-height: 200px; overflow-y: auto; }
.bubble.expanded .bubble-text::-webkit-scrollbar { width: 4px; }
.bubble.expanded .bubble-text::-webkit-scrollbar-thumb { background: rgba(44, 33, 19, .22); border-radius: 2px; }
.bubble-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 8px; }
.bbtn {
  border: 1px solid rgba(180, 105, 28, .22);
  background: rgba(239, 168, 76, .16); color: #8A4E12; font-size: 11px;
  border-radius: 999px; padding: 2px 9px; cursor: pointer; line-height: 1.6;
  transition: background .15s, border-color .15s;
}
.bbtn:hover { background: rgba(239, 168, 76, .3); border-color: rgba(180, 105, 28, .4); }

/* ===== 快捷输入 ===== */
.quick-input {
  background: linear-gradient(170deg, #12161F 0%, #0E1118 100%);
  border: 1px solid rgba(239, 168, 76, 0.45);
  border-radius: 12px;
  padding: 9px 10px 8px;
  box-shadow: 0 0 0 3px rgba(239, 168, 76, .10), 0 14px 34px -12px rgba(0, 0, 0, .75);
}
.quick-input textarea {
  width: 100%; box-sizing: border-box;
  background: transparent; color: #EBE9E4;
  border: none; outline: none; resize: none;
  padding: 0; font-size: 13px; line-height: 1.55;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei UI', 'PingFang SC', sans-serif;
}
.quick-input textarea::placeholder { color: #5E6675; }
.quick-actions {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 6px; padding-top: 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
}
.quick-hint { font-size: 10px; color: #5E6675; user-select: none; }
.quick-send {
  height: 24px; padding: 0 12px;
  border: none; border-radius: 999px;
  background: linear-gradient(135deg, #F3BE73, #E08F33);
  color: #2A1A07; font-size: 11.5px; font-weight: 700;
  cursor: pointer; transition: filter .15s, opacity .15s;
}
.quick-send:hover:not(:disabled) { filter: brightness(1.06); }
.quick-send:disabled { opacity: .35; cursor: not-allowed; }
</style>
