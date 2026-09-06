<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">关于</h1>
      <p class="page-subtitle">应用信息与版本说明</p>
    </header>

    <div class="about-grid">
      <section class="card">
        <div class="card-body brand">
          <div class="brand-logo"><img :src="logoUrl" alt="logo" /></div>
          <div class="brand-name">{{ appConfig.name }}</div>
          <div class="brand-version mono">v{{ appConfig.version }}</div>
          <p class="brand-desc">
            {{ appConfig.introduction }}
          </p>
        </div>
      </section>

      <section class="card">
        <div class="card-header">技术信息</div>
        <div class="card-body info-list">
          <div v-for="row in techInfo" :key="row.label" class="info-row">
            <span class="info-label">{{ row.label }}</span>
            <span class="info-value mono">{{ row.value }}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-header">相关链接</div>
        <div class="card-body link-list">
          <a
            v-for="link in links"
            :key="link.label"
            class="link-item"
            href="javascript:void(0)"
            @click="openLink(link.url)"
          >
            <span class="link-text">
              <span class="link-label">{{ link.label }}</span>
              <span class="link-url mono">{{ link.url }}</span>
            </span>
            <span class="link-arrow">→</span>
          </a>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { appConfig, pythonVersion, appLinks } from '../appConfig'
import logoUrl from '../../assets/icon.png'

// 静态示例数据，不接入真实功能
const techInfo = [
  { label: 'Electron', value: '28.0.0' },
  { label: 'Vue', value: '3.4.0' },
  { label: 'Vite', value: '5.4.21' },
  { label: 'Python', value: pythonVersion },
  { label: '平台', value: 'Windows x64' }
]

// 相关链接统一来自 config.json 的 links 配置
const links = appLinks

function openLink(url) {
  if (!url) return
  // 通过 Electron 主进程用系统默认浏览器打开
  if (window.electronAPI && window.electronAPI.openExternal) {
    window.electronAPI.openExternal(url)
  } else {
    window.open(url, '_blank')
  }
}
</script>

<style scoped>
.page {
  max-width: 900px;
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

.about-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 14px;
  overflow: hidden;
}

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

/* ===== 品牌区 ===== */
.brand {
  text-align: center;
  padding: 40px 24px;
}

.brand-logo {
  width: 72px;
  height: 72px;
  margin: 0 auto 16px;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 6px 18px rgba(99, 102, 241, 0.35);
}

.brand-logo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.brand-name {
  font-size: 24px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 6px;
}

.brand-version {
  display: inline-block;
  font-size: 13px;
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.15);
  border-radius: 20px;
  padding: 4px 14px;
  margin-bottom: 16px;
}

.brand-desc {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.7;
}

/* ===== 信息列表 ===== */
.info-list {
  display: flex;
  flex-direction: column;
  padding: 12px 24px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 0;
  border-bottom: 1px solid #273449;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 14px;
  color: #94a3b8;
}

.info-value {
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
}

.mono {
  font-family: 'Consolas', 'Monaco', monospace;
}

/* ===== 链接列表 ===== */
.link-list {
  display: flex;
  flex-direction: column;
  padding: 8px 24px;
}

.link-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 18px 0;
  border-bottom: 1px solid #273449;
  color: #cbd5e1;
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s;
}

.link-text {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.link-label {
  font-weight: 600;
  line-height: 1.5;
}

.link-url {
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.link-item:hover .link-url {
  color: #818cf8;
}

.link-item:last-child {
  border-bottom: none;
}

.link-item:hover {
  color: #a5b4fc;
}

.link-arrow {
  color: #6366f1;
}
</style>
