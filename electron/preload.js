const { contextBridge, ipcRenderer } = require('electron');

// 暴露安全的 API 到渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 运行平台（渲染层用于 mac 红绿灯留白 / 快捷键文案）
  platform: process.platform,

  // 自绘标题栏：窗口控制
  minimizeWindow: () => ipcRenderer.invoke('window:minimize'),
  toggleMaximizeWindow: () => ipcRenderer.invoke('window:toggle-maximize'),
  closeWindow: () => ipcRenderer.invoke('window:close'),
  isWindowMaximized: () => ipcRenderer.invoke('window:is-maximized'),
  onWindowMaximized: (callback) => {
    const handler = (event, value) => callback(value)
    ipcRenderer.on('window:maximized', handler)
    return () => ipcRenderer.removeListener('window:maximized', handler)
  },

  // 服务状态（只读，服务随应用常驻运行）
  getStatus: () => ipcRenderer.invoke('get-status'),

  // 拉取缓存的监控数据（解决页面挂载晚于推送的时序问题）
  getMetrics: () => ipcRenderer.invoke('get-metrics'),
  getSysinfo: () => ipcRenderer.invoke('get-sysinfo'),

  // 日志：拉取历史缓冲 / 导出为文件
  getLogs: () => ipcRenderer.invoke('get-logs'),
  exportLogs: (logs) => ipcRenderer.invoke('logs:export', logs),

  // 配置系统
  getConfig: () => ipcRenderer.invoke('config:get'),
  // 选择工作区目录（系统文件夹选择框）：{ success, path } 或 { canceled: true }
  pickDirectory: (opts) => ipcRenderer.invoke('dialog:pick-directory', opts),
  // 模板层默认值（只读）：设置页「恢复默认」按钮取内置默认文本用
  getConfigTemplate: () => ipcRenderer.invoke('config:get-template'),
  setConfig: (path, value) => ipcRenderer.invoke('config:set', { path, value }),
  setConfigMany: (patches) => ipcRenderer.invoke('config:set-many', patches),
  getRawProfileKey: (profileName) => ipcRenderer.invoke('config:get-raw-profile-key', profileName),
  // dsh 子代理独立 LLM 的 apiKey（未掩码）
  getRawDshKey: () => ipcRenderer.invoke('config:get-raw-dsh-key'),

  // Agent 服务信息
  getAgentInfo: () => ipcRenderer.invoke('get-agent-info'),
  restartAgent: () => ipcRenderer.invoke('agent:restart'),

  // 快速提问全局快捷键注册状态
  getShortcutStatus: () => ipcRenderer.invoke('shortcut:status'),

  // 测试 LLM 连接（经主进程，无 CORS 限制）
  testLlmConnection: (params) => ipcRenderer.invoke('test-llm-connection', params),

  // 事件监听
  onNavigateChat: (callback) => ipcRenderer.on('navigate-chat', () => callback()),
  onStatusUpdate: (callback) => ipcRenderer.on('status-update', (event, status) => callback(status)),
  offStatusUpdate: (callback) => ipcRenderer.removeListener('status-update', callback),
  onLogOutput: (callback) => ipcRenderer.on('log-output', (event, log) => callback(log)),
  onLogUpdate: (callback) => ipcRenderer.on('log-update', (event, log) => callback(log)),
  onMetricsUpdate: (callback) => ipcRenderer.on('metrics-update', (event, metrics) => callback(metrics)),
  onSysinfoUpdate: (callback) => ipcRenderer.on('sysinfo-update', (event, info) => callback(info)),
  onAgentReady: (callback) => ipcRenderer.on('agent-ready', (event, info) => callback(info)),
  onConfigChanged: (callback) => {
    const handler = (event, data) => callback(data)
    ipcRenderer.on('config:changed', handler)
    // 返回取消订阅函数：组件卸载时移除监听，避免路由来回切换后重复累积
    return () => ipcRenderer.removeListener('config:changed', handler)
  },
  onActivityPing: (callback) => ipcRenderer.on('activity-ping', (event, data) => callback(data)),
  onShortcutStatus: (callback) => ipcRenderer.on('shortcut-status', (event, data) => callback(data)),

  // 移除监听器
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel),

  // 用系统默认浏览器打开外部链接
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  // 用系统默认程序打开本地文件（present 文件卡片）
  openPath: (target) => ipcRenderer.invoke('shell:open-path', target),

  // 系统通知：主进程按桌宠可见性裁决（桌宠可见则丢弃，不可见则弹原生通知）
  showNotification: (payload) => ipcRenderer.invoke('notify:show', payload),

  // HTML 代码块预览：保存到 runtime/preview 并在应用内 Electron 预览窗口打开
  openHtmlPreview: (html) => ipcRenderer.invoke('html-preview:open', html)
});
