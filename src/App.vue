<template>
  <div class="layout">
    <!-- 左侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo">{{ appConfig.logo }}</div>
        <div class="app-name">{{ appConfig.name }}</div>
      </div>

      <div class="sidebar-divider"></div>

      <nav class="nav-menu">
        <router-link
          v-for="item in menuItems"
          :key="item.label"
          :to="item.path"
          class="nav-item"
          :class="{ disabled: item.disabled, active: !item.disabled && route.path === item.path }"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <span class="footer-dot"></span>
        <span class="footer-text">未连接</span>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { appConfig } from './appConfig'

const route = useRoute()

const menuItems = [
  { path: '/', label: '系统监控', icon: '📊', disabled: false },
  { path: '/logs', label: '日志', icon: '📋', disabled: false },
  { path: '/settings', label: '设置', icon: '🔧', disabled: true },
  { path: '/about', label: '关于', icon: 'ℹ️', disabled: false }
]
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  background: #0f172a;
  overflow: hidden;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: 240px;
  min-width: 240px;
  background: #1e293b;
  border-right: 1px solid #334155;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 28px 24px;
}

.logo {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
}

.app-name {
  font-size: 20px;
  font-weight: 700;
  color: #f1f5f9;
}

.sidebar-divider {
  height: 1px;
  background: #334155;
  margin: 0 16px 16px;
}

/* ===== 菜单 ===== */
.nav-menu {
  flex: 1;
  padding: 0 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  border-radius: 10px;
  color: #94a3b8;
  text-decoration: none;
  font-size: 15px;
  transition: all 0.2s;
}

.nav-item:hover:not(.disabled):not(.active) {
  background: #273449;
  color: #e2e8f0;
}

.nav-item.active {
  background: #4f46e5;
  color: #ffffff;
  font-weight: 500;
}

.nav-item.disabled {
  opacity: 0.45;
  cursor: not-allowed;
  pointer-events: none;
}

.nav-icon {
  font-size: 18px;
  width: 22px;
  text-align: center;
}

/* ===== 底部状态 ===== */
.sidebar-footer {
  padding: 20px 24px;
  border-top: 1px solid #334155;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #94a3b8;
}

.footer-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #64748b;
}

/* ===== 内容区 ===== */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
}

.content::-webkit-scrollbar {
  width: 8px;
}

.content::-webkit-scrollbar-track {
  background: transparent;
}

.content::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 4px;
}
</style>
