<template>
  <div class="setup-container">
    <div class="setup-header">
      <div class="icon">🐍</div>
      <h1>环境检查与配置</h1>
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
          <span v-else-if="step.status === 'completed'">✓</span>
          <span v-else-if="step.status === 'failed'">✗</span>
          <span v-else>{{ index + 1 }}</span>
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
      <div class="error-msg">{{ error }}</div>
      <div class="btn-row">
        <button class="btn-retry" @click="retry">重试</button>
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
.setup-container {
  width: 520px;
  padding: 40px;
  margin: 0 auto;
}

.setup-header {
  text-align: center;
  margin-bottom: 32px;
}

.setup-header .icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.setup-header h1 {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 8px;
}

.status-scroller {
  margin-top: 16px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #1e293b, #334155);
  border-radius: 8px;
  border: 1px solid #475569;
  overflow: hidden;
  position: relative;
}

.status-text {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
}

.status-text.active {
  color: #60a5fa;
}

.progress-bar-container {
  width: 100%;
  height: 6px;
  background: #334155;
  border-radius: 3px;
  margin-bottom: 20px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-bar.error {
  background: linear-gradient(90deg, #ef4444, #dc2626);
}

.progress-bar.success {
  background: linear-gradient(90deg, #10b981, #059669);
}

.steps-list {
  list-style: none;
  margin-bottom: 24px;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 10px;
  margin-bottom: 8px;
  background: #1e293b;
  border: 1px solid #334155;
  transition: all 0.3s ease;
}

.step-item.active {
  border-color: #4f46e5;
  box-shadow: 0 0 0 1px rgba(79, 70, 229, 0.3);
}

.step-item.completed {
  border-color: #10b981;
  opacity: 0.8;
}

.step-item.failed {
  border-color: #ef4444;
  background: rgba(239, 68, 68, 0.05);
}

.step-item.pending {
  opacity: 0.5;
}

.step-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
  background: #334155;
  color: #94a3b8;
}

.step-item.active .step-icon {
  background: #4f46e5;
  color: white;
}

.step-item.completed .step-icon {
  background: #10b981;
  color: white;
}

.step-item.failed .step-icon {
  background: #ef4444;
  color: white;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.step-content {
  flex: 1;
}

.step-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
}

.step-desc {
  font-size: 12px;
  color: #94a3b8;
}

.step-item.failed .step-desc {
  color: #fca5a5;
}

.log-area {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
  max-height: 180px;
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #94a3b8;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
}

.log-line.error {
  color: #fca5a5;
}

.log-line.success {
  color: #6ee7b7;
}

.error-footer {
  margin-top: 20px;
  text-align: center;
}

.error-msg {
  color: #fca5a5;
  font-size: 13px;
  margin-bottom: 16px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 8px;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.btn-row {
  display: flex;
  justify-content: center;
  gap: 12px;
}

.btn-retry {
  padding: 10px 24px;
  background: #4f46e5;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-retry:hover {
  background: #4338ca;
}

.btn-quit {
  padding: 10px 24px;
  background: transparent;
  color: #94a3b8;
  border: 1px solid #475569;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-quit:hover {
  color: #f1f5f9;
  border-color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.success-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.95);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.4s ease, visibility 0.4s ease;
  z-index: 100;
}

.success-overlay.visible {
  opacity: 1;
  visibility: visible;
}

.success-icon {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: linear-gradient(135deg, #10b981, #059669);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
  transform: scale(0);
  transition: transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 0 0 40px rgba(16, 185, 129, 0.4);
}

.success-overlay.visible .success-icon {
  transform: scale(1);
}

.success-checkmark {
  width: 40px;
  height: 40px;
  stroke: white;
  stroke-width: 4;
  fill: none;
  stroke-dasharray: 100;
  stroke-dashoffset: 100;
  animation: drawCheck 0.6s ease 0.3s forwards;
}

@keyframes drawCheck {
  to { stroke-dashoffset: 0; }
}

.success-title {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 8px;
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.4s ease 0.5s, transform 0.4s ease 0.5s;
}

.success-overlay.visible .success-title {
  opacity: 1;
  transform: translateY(0);
}

.success-subtitle {
  font-size: 14px;
  color: #94a3b8;
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.4s ease 0.6s, transform 0.4s ease 0.6s;
}

.success-overlay.visible .success-subtitle {
  opacity: 1;
  transform: translateY(0);
}
</style>
