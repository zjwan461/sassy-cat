<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">系统信息监控</h1>
      <p class="page-subtitle">
        CPU、内存、GPU 与磁盘实时用量
        <span class="data-source" :class="{ real: hasRealData }">
          {{ hasRealData ? '● 实时数据' : '○ 演示数据（服务未运行）' }}
        </span>
      </p>
    </header>

    <!-- 指标卡片 -->
    <div class="metrics-grid">
      <section v-for="m in metrics" :key="m.key" class="card metric-card">
        <div class="metric-head">
          <span class="metric-icon">{{ m.icon }}</span>
          <span class="metric-name">{{ m.name }}</span>
          <span class="metric-value" :class="levelClass(m.value)">{{ m.value.toFixed(1) }}%</span>
        </div>
        <div class="meter">
          <div class="meter-fill" :class="levelClass(m.value)" :style="{ width: m.value + '%' }"></div>
        </div>
        <div class="metric-foot">
          <span>{{ m.detail }}</span>
        </div>
      </section>
    </div>

    <!-- 系统信息 -->
    <section class="card">
      <div class="card-header">系统信息</div>
      <div class="card-body info-grid">
        <div v-for="row in sysInfo" :key="row.label" class="info-item">
          <div class="info-label">{{ row.label }}</div>
          <div class="info-value mono">{{ row.value }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, onUnmounted } from 'vue'

// 指标数据：收到 Python 端真实数据后由真实数据驱动；否则定时模拟波动作为回退
const metrics = reactive([
  { key: 'cpu', name: 'CPU 用量', icon: '🧠', value: 0, detail: '--' },
  { key: 'mem', name: '内存用量', icon: '💾', value: 0, detail: '--' },
  { key: 'gpu', name: 'GPU 用量', icon: '🎮', value: 0, detail: '--' },
  { key: 'disk', name: '磁盘占用', icon: '🗄️', value: 0, detail: '--' }
])

const sysInfo = ref([
  { label: '主机名', value: '--' },
  { label: '操作系统', value: '--' },
  { label: 'CPU 型号', value: '--' },
  { label: 'GPU 型号', value: '--' },
  { label: '内存总量', value: '--' },
  { label: 'Python 版本', value: '--' },
  { label: '系统启动时间', value: '--' }
])

const hasRealData = ref(false)

// ---------- 真实数据接入 ----------
const applyMetrics = (m) => {
  hasRealData.value = true
  if (m.cpu) {
    metrics[0].value = m.cpu.percent
    metrics[0].detail = `${m.cpu.cores || '?'} 核 ${m.cpu.threads || '?'} 线程`
  }
  if (m.memory) {
    metrics[1].value = m.memory.percent
    metrics[1].detail = `${m.memory.usedGB} GB / ${m.memory.totalGB} GB`
  }
  if (m.gpus && m.gpus.length > 0) {
    // 多卡时优先展示利用率最高的卡（通常为独显）
    const gpu = [...m.gpus].sort((a, b) => (b.percent || 0) - (a.percent || 0))[0]
    metrics[2].name = `GPU 用量 (${gpu.vendor || gpu.name})`
    metrics[2].value = gpu.percent || 0
    metrics[2].detail = gpu.memUsedGB != null
      ? `显存 ${gpu.memUsedGB} GB / ${gpu.memTotalGB} GB`
      : `${gpu.name}`
  } else {
    metrics[2].value = 0
    metrics[2].detail = '未检测到 GPU 数据'
  }
  if (m.disks && m.disks.length > 0) {
    const main = m.disks.find((d) => /^[A-Za-z]:\\$/.test(d.mount) && d.mount.toUpperCase() === 'C:\\') || m.disks[0]
    metrics[3].value = main.percent
    metrics[3].detail = `${main.mount} ${main.usedGB} GB / ${main.totalGB} GB`
  }
}

const applySysinfo = (info) => {
  const map = {
    '主机名': info.hostname,
    '操作系统': info.osName && `${info.osName} (${info.osArch})`,
    'CPU 型号': info.cpuName,
    'GPU 型号': info.gpuName,
    '内存总量': info.totalMemGB && `${info.totalMemGB} GB`,
    'Python 版本': info.pythonVersion,
    '系统启动时间': info.bootTime
  }
  sysInfo.value.forEach((row) => {
    if (map[row.label] != null) {
      row.value = String(map[row.label])
    }
  })
}

let offMetrics = null
let offSysinfo = null

onMounted(async () => {
  if (window.electronAPI) {
    window.electronAPI.onMetricsUpdate(applyMetrics)
    window.electronAPI.onSysinfoUpdate(applySysinfo)
    // 主动拉取缓存（页面挂载可能晚于 Python 首次推送）
    try {
      const cached = await window.electronAPI.getSysinfo()
      if (cached) applySysinfo(cached)
      const cachedMetrics = await window.electronAPI.getMetrics()
      if (cachedMetrics) applyMetrics(cachedMetrics)
    } catch (e) {
      // ignore
    }
  }
})

// ---------- 模拟回退（收到真实数据后自动停用） ----------
const jitter = (base, range) =>
  Math.min(99, Math.max(1, base + (Math.random() - 0.5) * range))

const timer = setInterval(() => {
  if (hasRealData.value) return
  metrics[0].value = jitter(metrics[0].value, 12)
  metrics[1].value = jitter(metrics[1].value, 4)
  metrics[2].value = jitter(metrics[2].value, 16)
  metrics[3].value = jitter(metrics[3].value, 1)
}, 2000)

onUnmounted(() => {
  clearInterval(timer)
  if (window.electronAPI && window.electronAPI.removeAllListeners) {
    window.electronAPI.removeAllListeners('metrics-update')
    window.electronAPI.removeAllListeners('sysinfo-update')
  }
})

const levelClass = (v) => (v >= 80 ? 'high' : v >= 55 ? 'mid' : 'low')
</script>

<style scoped>
.page {
  max-width: 1200px;
}

.page-header {
  margin-bottom: 28px;
}

.page-title {
  font-size: 30px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 8px;
}

.page-subtitle {
  font-size: 15px;
  color: #64748b;
}

.data-source {
  margin-left: 10px;
  font-size: 12px;
  color: #fbbf24;
}

.data-source.real {
  color: #10b981;
}

/* ===== 指标卡片 ===== */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 14px;
  overflow: hidden;
}

.metric-card {
  padding: 20px 22px;
}

.metric-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.metric-icon {
  font-size: 18px;
}

.metric-name {
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
  flex: 1;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  font-family: 'Consolas', 'Monaco', monospace;
}

.metric-value.low { color: #10b981; }
.metric-value.mid { color: #fbbf24; }
.metric-value.high { color: #ef4444; }

/* ===== 进度条 ===== */
.meter {
  height: 8px;
  background: #0f172a;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 12px;
}

.meter-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.8s ease;
}

.meter-fill.low { background: #10b981; }
.meter-fill.mid { background: #fbbf24; }
.meter-fill.high { background: #ef4444; }

.metric-foot {
  font-size: 13px;
  color: #64748b;
}

/* ===== 系统信息 ===== */
.card-header {
  padding: 20px 24px;
  font-size: 17px;
  font-weight: 600;
  color: #e2e8f0;
  border-bottom: 1px solid #334155;
}

.card-body {
  padding: 24px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 20px;
}

.info-item {
  background: #273449;
  border-radius: 10px;
  padding: 16px 18px;
}

.info-label {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 8px;
}

.info-value {
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
}

.mono {
  font-family: 'Consolas', 'Monaco', monospace;
}
</style>
