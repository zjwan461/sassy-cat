<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">日志</h1>
      <p class="page-subtitle">服务运行日志与事件记录</p>
    </header>

    <section class="card">
      <div class="card-header">
        <span>运行日志</span>
        <span class="log-count">共 {{ logs.length }} 条</span>
      </div>
      <div class="card-body log-container">
        <div v-for="(log, index) in logs" :key="index" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-level" :class="log.level">{{ log.level.toUpperCase() }}</span>
          <span class="log-text">{{ log.text }}</span>
        </div>
        <div v-if="logs.length === 0" class="log-empty">暂无日志...</div>
      </div>
    </section>
  </div>
</template>

<script setup>
// 静态示例日志，不接入真实功能
const logs = [
  { time: '10:00:01', level: 'info', text: '应用启动，正在检查运行环境...' },
  { time: '10:00:02', level: 'info', text: 'Python 环境检查通过 (3.11.9)' },
  { time: '10:00:03', level: 'info', text: '依赖校验完成，共 3 个包' },
  { time: '10:00:05', level: 'warn', text: '未检测到本地代理配置，使用默认值' },
  { time: '10:00:06', level: 'info', text: '主界面加载完成' }
]
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

.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 14px;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  font-size: 17px;
  font-weight: 600;
  color: #e2e8f0;
  border-bottom: 1px solid #334155;
}

.log-count {
  font-size: 13px;
  font-weight: 400;
  color: #64748b;
}

.card-body {
  padding: 16px 24px;
}

/* ===== 日志列表 ===== */
.log-container {
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.log-container::-webkit-scrollbar {
  width: 6px;
}

.log-container::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 3px;
}

.log-line {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #273449;
}

.log-line:last-child {
  border-bottom: none;
}

.log-time {
  color: #64748b;
  flex-shrink: 0;
}

.log-level {
  flex-shrink: 0;
  width: 52px;
  font-weight: 700;
  font-size: 11px;
}

.log-level.info { color: #38bdf8; }
.log-level.warn { color: #fbbf24; }
.log-level.error { color: #ef4444; }

.log-text {
  color: #cbd5e1;
  word-break: break-all;
}

.log-empty {
  color: #64748b;
  text-align: center;
  padding: 40px 0;
}
</style>
