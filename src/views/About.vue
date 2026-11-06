<template>
  <div class="page">
    <header class="page-header">
      <div class="header-main">
        <div class="eyebrow">
          <AppIcon name="sparkles" :size="12" />
          关于优墨
        </div>
        <h1 class="page-title">关于</h1>
        <p class="page-subtitle">应用信息与版本说明</p>
      </div>
    </header>

    <div class="about-grid">
      <section class="card hero">
        <div class="hero-glow" aria-hidden="true"></div>
        <div class="hero-body">
          <div class="brand-logo"><img :src="logoUrl" alt="logo" /></div>
          <div class="brand-name">{{ appConfig.name }}</div>
          <span class="brand-version mono">v{{ appConfig.version }}</span>
          <p class="brand-desc">
            {{ appConfig.introduction }}
          </p>
        </div>
      </section>

      <section class="card">
        <div class="card-header">
          <AppIcon name="settings" :size="14" class="header-icon" />
          技术信息
        </div>
        <div class="card-body info-list">
          <div v-for="row in techInfo" :key="row.label" class="info-row">
            <span class="info-label">{{ row.label }}</span>
            <span class="info-value mono">{{ row.value }}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-header">
          <AppIcon name="link" :size="14" class="header-icon" />
          相关链接
        </div>
        <div class="card-body link-list">
          <a
            v-for="link in links"
            :key="link.label"
            class="link-item"
            href="javascript:void(0)"
            @click="openLink(link.url)"
          >
            <span class="link-icon"><AppIcon name="globe" :size="14" /></span>
            <span class="link-text">
              <span class="link-label">{{ link.label }}</span>
              <span class="link-url mono">{{ link.url }}</span>
            </span>
            <span class="link-arrow"><AppIcon name="external-link" :size="14" /></span>
          </a>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { appConfig, pythonVersion, appLinks } from '../appConfig'
import AppIcon from '../components/AppIcon.vue'
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
  margin: 0 auto;
  animation: fadeUp var(--dur-slow) var(--ease-out) backwards;
}

/* ===== 页头 ===== */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.header-main {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--amber-500);
  margin-bottom: 8px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
  color: var(--text-1);
}

.page-subtitle {
  margin-top: 7px;
  font-size: 13px;
  color: var(--text-3);
}

/* ===== 卡片 ===== */
.about-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}

.card {
  position: relative;
  min-width: 0;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 13px 18px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
  border-bottom: 1px solid var(--line-1);
}

.header-icon {
  color: var(--text-4);
}

.card-body {
  padding: 0;
}

/* ===== 品牌英雄区 ===== */
.hero {
  grid-column: 1 / -1;
}

/* 一小片琥珀环境光，落在产品标识后面 */
.hero-glow {
  position: absolute;
  top: -180px;
  left: 50%;
  width: 560px;
  height: 360px;
  transform: translateX(-50%);
  pointer-events: none;
  background: radial-gradient(closest-side, var(--amber-a12), transparent 72%);
}

.hero-body {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 38px 28px 34px;
}

/* 黑猫是纯黑剪影：必须落在浅色「月光瓦片」上才看得见 */
.brand-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  border-radius: var(--r-lg);
  background: linear-gradient(150deg, #FBF0DA, #E9D2A6);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.14),
    0 14px 30px -14px rgba(239, 168, 76, 0.55),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.brand-logo img {
  width: 44px;
  height: 44px;
  object-fit: contain;
}

.brand-name {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 1.25;
  color: var(--text-1);
}

.brand-version {
  display: inline-flex;
  align-items: center;
  height: 20px;
  margin-top: 8px;
  padding: 0 10px;
  border-radius: var(--r-full);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--amber-300);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

.brand-desc {
  max-width: 56ch;
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-3);
}

/* ===== 技术信息：两列定义网格 ===== */
.info-list {
  padding: 4px 18px 8px;
}

.info-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: baseline;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid var(--line-1);
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 12px;
  letter-spacing: 0.02em;
  color: var(--text-4);
}

.info-value {
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-1);
  text-align: right;
  overflow-wrap: anywhere;
}

/* ===== 相关链接 ===== */
.link-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px 14px;
}

.link-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 11px;
  border-radius: var(--r-md);
  border: 1px solid var(--line-1);
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-1);
  text-decoration: none;
  transition: transform var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out),
    background var(--dur) var(--ease-out), box-shadow var(--dur) var(--ease-out);
}

.link-item:hover {
  transform: translateY(-2px);
  border-color: var(--amber-a35);
  background: rgba(255, 255, 255, 0.04);
  box-shadow: var(--shadow-2);
}

.link-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: var(--r-sm);
  color: var(--amber-300);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

.link-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.link-label {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--text-1);
}

.link-url {
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color var(--dur) var(--ease-out);
}

.link-item:hover .link-url {
  color: var(--text-3);
}

.link-arrow {
  display: flex;
  align-items: center;
  color: var(--text-4);
  flex-shrink: 0;
  transition: color var(--dur) var(--ease-out), transform var(--dur) var(--ease-out);
}

.link-item:hover .link-arrow {
  color: var(--amber-400);
  transform: translate(1px, -1px);
}

.mono {
  font-family: var(--font-mono);
}

/* ===== 响应式 ===== */
@media (max-width: 980px) {
  .page-title {
    font-size: 23px;
  }
}

@media (max-width: 860px) {
  .about-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .hero-body {
    padding: 32px 22px 30px;
  }
}
</style>
