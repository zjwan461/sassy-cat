<template>
  <div class="setup-container">
    <header class="setup-header">
      <div class="setup-mark"><AppIcon name="shield" :size="22" /></div>
      <div class="setup-head-text">
        <div class="eyebrow">首次启动</div>
        <h1>环境检查与配置</h1>
      </div>
    </header>

    <div class="status-panel">
      <span v-if="isChecking" class="status-spinner"></span>
      <span v-else-if="error" class="status-icon status-icon--error">
        <AppIcon name="alert" :size="13" />
      </span>
      <span v-else class="status-icon status-icon--done">
        <AppIcon name="check" :size="13" />
      </span>
      <div class="status-scroller">
        <div class="status-text" :class="{ active: isChecking }">
          {{ statusMessage }}
        </div>
      </div>
    </div>

    <div class="progress-bar-container">
      <div class="progress-bar" :class="progressStatus" :style="{ width: progress + '%' }"></div>
    </div>

    <ul class="steps-list">
      <li 
        v-for="(step, index) in steps" 
        :key="index"
        class="step-item"
        :class="step.status"
      >
        <div class="step-icon">
          <div v-if="step.status === 'active'" class="spinner"></div>
          <AppIcon v-else-if="step.status === 'completed'" name="check" :size="13" />
          <AppIcon v-else-if="step.status === 'failed'" name="x" :size="13" />
          <span v-else class="step-num">{{ index + 1 }}</span>
        </div>
        <div class="step-content">
          <div class="step-title">{{ step.title }}</div>
          <div class="step-desc">{{ step.desc }}</div>
        </div>
      </li>
    </ul>

    <div class="log-area">
      <div v-for="(log, index) in logs" :key="index" class="log-line" :class="log.type">
        {{ log.text }}
      </div>
    </div>

    <div v-if="error" class="error-footer">
      <div class="error-msg">
        <AppIcon name="alert" :size="14" />
        <span>{{ error }}</span>
      </div>
      <div class="btn-row">
        <button class="btn-retry" @click="retry">
          <AppIcon name="refresh" :size="14" />
          重试
        </button>
        <button class="btn-quit" @click="quit">退出程序</button>
      </div>
    </div>

    <div class="success-overlay" :class="{ visible: showSuccess }">
      <div class="success-particles"></div>
      <div class="success-icon">
        <svg class="success-checkmark" viewBox="0 0 40 40">
          <polyline points="10,20 18,28 30,12" />
        </svg>
      </div>
      <div class="success-title">环境检查完成</div>
      <div class="success-subtitle">正在启动应用程序...</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import AppIcon from '../components/AppIcon.vue'

// 在 nodeIntegration 环境下，必须通过 window.require 获取 electron 模块
// 直接使用 ESM import 会被 Vite 打包解析，导致运行时错误
const { ipcRenderer } = window.require('electron')

const steps = ref([
  { title: '检查虚拟环境', desc: '检测 .venv 目录是否存在', status: 'pending' },
  { title: '检查依赖安装', desc: '验证 requirements.txt 中的依赖是否已安装', status: 'pending' },
  { title: '检查 Python', desc: '检测系统是否安装了 Python', status: 'pending' },
  { title: '下载 Python', desc: '从互联网下载 Python 嵌入式版本', status: 'pending' }
])

const logs = ref([])
const progress = ref(0)
const progressStatus = ref('')
const statusMessage = ref('正在检查 Python 运行环境...')
const isChecking = ref(true)
const error = ref('')
const showSuccess = ref(false)

const stepMap = {
  '检查虚拟环境': 0,
  '检查依赖安装': 1,
  '检查Python': 2,
  '检查 Python': 2,
  '创建虚拟环境': 2,
  '下载Python': 3,
  '下载 Python': 3,
  '解压Python': 3,
  '配置Python环境': 3,
  '安装依赖': 1
}

const setStepStatus = (stepName, status) => {
  const index = stepMap[stepName]
  if (index !== undefined) {
    steps.value[index].status = status
  }
}

const addLog = (text, type = '') => {
  logs.value.push({ text, type })
  if (logs.value.length > 50) {
    logs.value.shift()
  }
}

const updateProgress = (percent, status = '') => {
  progress.value = percent
  progressStatus.value = status
}

onMounted(() => {
  ipcRenderer.on('env-check-step', (event, data) => {
    setStepStatus(data.step, 'active')
    statusMessage.value = `正在${data.step}...`
    
    const index = stepMap[data.step]
    if (index !== undefined) {
      updateProgress((index / steps.value.length) * 100)
    }
  })

  ipcRenderer.on('env-check-step-done', (event, data) => {
    setStepStatus(data.step, 'completed')
    statusMessage.value = `${data.step} ✓`
  })

  ipcRenderer.on('env-check-log', (event, data) => {
    const type = data.error ? 'error' : (data.success ? 'success' : '')
    addLog(data.message, type)
  })

  ipcRenderer.on('env-check-progress', (event, data) => {
    addLog(data.message)
  })

  ipcRenderer.on('env-check-complete', (event, data) => {
    if (data.success) {
      updateProgress(100, 'success')
      statusMessage.value = '✅ 环境检查完成'
      isChecking.value = false
      addLog('✅ 环境检查完成，正在启动应用...', 'success')
      
      setTimeout(() => {
        showSuccess.value = true
        setTimeout(() => {
          ipcRenderer.send('setup-ready-to-close')
        }, 1000)
      }, 300)
    }
  })

  ipcRenderer.on('env-check-error', (event, data) => {
    updateProgress(100, 'error')
    error.value = `环境配置失败: ${data.message}`
    isChecking.value = false
    
    steps.value.forEach(step => {
      if (step.status === 'active') {
        step.status = 'failed'
      }
    })
  })

  ipcRenderer.send('setup-ready')
})

const retry = () => {
  steps.value.forEach(step => step.status = 'pending')
  logs.value = []
  error.value = ''
  updateProgress(0)
  statusMessage.value = '正在检查 Python 运行环境...'
  isChecking.value = true
  showSuccess.value = false
  
  ipcRenderer.send('env-check-retry')
}

const quit = () => {
  ipcRenderer.invoke('quit-app')
}
</script>

<style scoped>
/* 窗口本身是透明无边框的：这里只铺内容，不铺整窗背景，
   避免把主进程那边的透明圆角外壳盖成一块实心矩形 */
.setup-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 560px;
  min-height: 100vh;
  margin: 0 auto;
  padding: 26px 30px 28px;
}

/* ===== 页头 ===== */
.setup-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  /* 该窗口由主进程以无边框方式创建，页头承担"标题栏"职责：
     可拖拽移动，按钮等交互元素在需要时再单独声明 no-drag */
  -webkit-app-region: drag;
  user-select: none;
}

.setup-header button,
.setup-header a {
  -webkit-app-region: no-drag;
}

.setup-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: var(--r-md);
  color: var(--amber-300);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
  box-shadow: var(--hairline);
}

.setup-head-text {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--amber-500);
  margin-bottom: 4px;
}

.setup-header h1 {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
  color: var(--text-1);
}

/* ===== 状态条：内凹的深色面板 ===== */
.status-panel {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  margin-bottom: 10px;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.status-spinner {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 2px solid var(--amber-a20);
  border-top-color: var(--amber-400);
  animation: spin 0.8s linear infinite;
}

.status-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.status-icon--done {
  color: var(--jade-400);
}

.status-icon--error {
  color: var(--coral-400);
}

.status-scroller {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.status-text {
  font-size: 12.5px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color var(--dur) var(--ease-out);
}

.status-text.active {
  color: var(--amber-300);
}

/* ===== 进度条 ===== */
.progress-bar-container {
  width: 100%;
  height: 4px;
  margin-bottom: 16px;
  border-radius: var(--r-full);
  background: var(--ink-700);
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  width: 0;
  border-radius: var(--r-full);
  background: var(--amber-grad);
  box-shadow: 0 0 12px var(--amber-a35);
  transition: width var(--dur-slow) var(--ease-out);
}

.progress-bar.error {
  background: var(--coral-400);
  box-shadow: none;
}

.progress-bar.success {
  background: var(--jade-400);
  box-shadow: 0 0 12px rgba(126, 203, 161, 0.35);
}

/* ===== 步骤卡片 ===== */
.steps-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 11px 13px;
  border-radius: var(--r-md);
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  box-shadow: var(--shadow-1);
  transition: border-color var(--dur) var(--ease-out), background var(--dur) var(--ease-out),
    box-shadow var(--dur) var(--ease-out), opacity var(--dur) var(--ease-out);
}

.step-item.active {
  border-color: var(--amber-a35);
  box-shadow: var(--shadow-2), inset 0 0 0 1px var(--amber-a12);
}

.step-item.completed {
  border-color: rgba(126, 203, 161, 0.22);
}

.step-item.failed {
  border-color: rgba(233, 119, 110, 0.34);
  background: var(--coral-a12);
}

.step-item.pending {
  opacity: 0.72;
}

/* 编号圆点：激活 = 琥珀实心，完成 = 玉色勾，失败 = 珊瑚叉，待办 = 弱描边 */
.step-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border-radius: 50%;
  font-size: 11.5px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
  background: var(--ink-700);
  border: 1px solid var(--line-2);
  transition: background var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out),
    color var(--dur) var(--ease-out);
}

.step-num {
  line-height: 1;
}

.step-item.active .step-icon {
  color: var(--amber-ink);
  background: var(--amber-grad);
  border-color: transparent;
  box-shadow: 0 4px 14px -6px rgba(239, 168, 76, 0.6);
}

.step-item.completed .step-icon {
  color: var(--jade-400);
  background: var(--jade-a12);
  border-color: rgba(126, 203, 161, 0.4);
}

.step-item.failed .step-icon {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.42);
}

.spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--amber-ink) 28%, transparent);
  border-top-color: var(--amber-ink);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.step-content {
  flex: 1;
  min-width: 0;
}

.step-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--text-1);
}

.step-desc {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--text-4);
  overflow-wrap: anywhere;
}

.step-item.failed .step-desc {
  color: var(--coral-400);
}

/* ===== 日志区 ===== */
.log-area {
  flex: 1 1 auto;
  min-height: 82px;
  max-height: 190px;
  padding: 10px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
  font-family: var(--font-mono);
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-3);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.03),
    inset 0 12px 24px -20px rgba(0, 0, 0, 0.9);
}

.log-area::-webkit-scrollbar {
  width: 8px;
}

.log-area::-webkit-scrollbar-thumb {
  background: var(--ink-600);
  border-radius: var(--r-full);
  border: 2px solid transparent;
  background-clip: padding-box;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.log-line.error {
  color: var(--coral-400);
}

.log-line.success {
  color: var(--jade-400);
}

/* ===== 失败页脚 ===== */
.error-footer {
  margin-top: 14px;
  text-align: center;
}

.error-msg {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  font-size: 12.5px;
  line-height: 1.6;
  text-align: left;
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.3);
  overflow-wrap: anywhere;
}

.btn-row {
  display: flex;
  justify-content: center;
  gap: 10px;
}

.btn-retry {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 20px;
  font-size: 13px;
  font-weight: 650;
  color: var(--amber-ink);
  background: var(--amber-grad);
  border: none;
  border-radius: var(--r-sm);
  cursor: pointer;
  box-shadow: var(--shadow-1), inset 0 1px 0 rgba(255, 255, 255, 0.28);
  transition: filter var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}

.btn-retry:hover {
  filter: brightness(1.07);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.btn-quit {
  height: 34px;
  padding: 0 18px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-2);
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}

.btn-quit:hover {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.45);
}

/* ===== 完成遮罩 ===== */
.success-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  text-align: center;
  background: color-mix(in srgb, var(--ink-1000) 93%, transparent);
  backdrop-filter: blur(10px);
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--dur-slow) var(--ease-out), visibility var(--dur-slow) var(--ease-out);
}

.success-overlay.visible {
  opacity: 1;
  visibility: visible;
}

.success-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 78px;
  height: 78px;
  margin-bottom: 18px;
  border-radius: 50%;
  color: var(--jade-400);
  background: var(--jade-a12);
  border: 1px solid rgba(126, 203, 161, 0.35);
  box-shadow:
    0 0 0 8px rgba(126, 203, 161, 0.05),
    0 24px 50px -24px rgba(0, 0, 0, 0.9);
  transform: scale(0.6);
  transition: transform 0.5s var(--ease-spring);
}

.success-overlay.visible .success-icon {
  transform: scale(1);
}

.success-checkmark {
  width: 34px;
  height: 34px;
  fill: none;
  stroke: currentColor;
  stroke-width: 3.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 100;
  stroke-dashoffset: 100;
  animation: drawCheck 0.6s var(--ease-out) 0.25s forwards;
}

@keyframes drawCheck {
  to { stroke-dashoffset: 0; }
}

.success-title {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text-1);
  opacity: 0;
  transform: translateY(12px);
  transition: opacity var(--dur-slow) var(--ease-out) 0.2s,
    transform var(--dur-slow) var(--ease-out) 0.2s;
}

.success-overlay.visible .success-title {
  opacity: 1;
  transform: translateY(0);
}

.success-subtitle {
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--text-3);
  opacity: 0;
  transform: translateY(12px);
  transition: opacity var(--dur-slow) var(--ease-out) 0.3s,
    transform var(--dur-slow) var(--ease-out) 0.3s;
}

.success-overlay.visible .success-subtitle {
  opacity: 1;
  transform: translateY(0);
}

/* ===== 窗口偏窄时（580×680 固定窗）===== */
@media (max-width: 540px) {
  .setup-container {
    padding: 22px 20px 24px;
  }

  .setup-header h1 {
    font-size: 18px;
  }
}
</style>
