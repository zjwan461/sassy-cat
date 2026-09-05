const { contextBridge, ipcRenderer } = require('electron');

// 暴露安全的 API 到渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 服务控制
  startService: () => ipcRenderer.invoke('start-service'),
  stopService: () => ipcRenderer.invoke('stop-service'),
  getStatus: () => ipcRenderer.invoke('get-status'),

  // 拉取缓存的监控数据（解决页面挂载晚于推送的时序问题）
  getMetrics: () => ipcRenderer.invoke('get-metrics'),
  getSysinfo: () => ipcRenderer.invoke('get-sysinfo'),
  
  // 事件监听
  onStatusUpdate: (callback) => ipcRenderer.on('status-update', (event, status) => callback(status)),
  onLogOutput: (callback) => ipcRenderer.on('log-output', (event, log) => callback(log)),
  onMetricsUpdate: (callback) => ipcRenderer.on('metrics-update', (event, metrics) => callback(metrics)),
  onSysinfoUpdate: (callback) => ipcRenderer.on('sysinfo-update', (event, info) => callback(info)),
  
  // 移除监听器
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel),

  // 用系统默认浏览器打开外部链接
  openExternal: (url) => ipcRenderer.invoke('open-external', url)
});
