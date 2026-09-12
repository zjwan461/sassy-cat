const { contextBridge, ipcRenderer } = require('electron');

// 暴露安全的 API 到渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
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
  setConfig: (path, value) => ipcRenderer.invoke('config:set', { path, value }),
  setConfigMany: (patches) => ipcRenderer.invoke('config:set-many', patches),
  getRawProfileKey: (profileName) => ipcRenderer.invoke('config:get-raw-profile-key', profileName),

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
  onConfigChanged: (callback) => ipcRenderer.on('config:changed', (event, data) => callback(data)),
  onActivityPing: (callback) => ipcRenderer.on('activity-ping', (event, data) => callback(data)),
  onShortcutStatus: (callback) => ipcRenderer.on('shortcut-status', (event, data) => callback(data)),

  // 移除监听器
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel),

  // 用系统默认浏览器打开外部链接
  openExternal: (url) => ipcRenderer.invoke('open-external', url)
});
