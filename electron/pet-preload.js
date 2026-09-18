const { contextBridge, ipcRenderer } = require('electron');

// 桌宠窗口专用 API
contextBridge.exposeInMainWorld('petAPI', {
  // 指针进入/离开宠物区域时切换鼠标穿透
  setInteractive: (interactive) => ipcRenderer.invoke('pet:set-interactive', interactive),
  // 相对移动窗口（拖动/走动，主进程节流合并）
  moveDelta: (dx, dy) => ipcRenderer.send('pet:move-delta', { dx, dy }),
  getPosition: () => ipcRenderer.invoke('pet:get-position'),
  // 动态调整窗口高度（快捷输入展开/收起）
  resize: (height) => ipcRenderer.invoke('pet:resize', height),
  // 请求主窗口显示并跳转到聊天页
  showChat: () => ipcRenderer.invoke('pet:show-chat'),
  hideSelf: () => ipcRenderer.invoke('pet:hide'),
  // 全局快捷键触发快速提问（主进程 pet:quick-ask 事件）
  onQuickAsk: (cb) => ipcRenderer.on('pet:quick-ask', () => cb()),
  // 原生右键菜单
  popupMenu: (items) => ipcRenderer.invoke('pet:popup-menu', items),
  onMenuAction: (cb) => ipcRenderer.on('pet:menu-action', (e, data) => cb(data)),

  onAgentReady: (cb) => ipcRenderer.on('agent-ready', (e, info) => cb(info)),
  onActivityPing: (cb) => ipcRenderer.on('activity-ping', (e, data) => cb(data)),

  // 主窗口是否处于前台激活（挂载时主动查询一次）
  getMainWindowActive: () => ipcRenderer.invoke('pet:main-window-active'),
  // 主窗口激活状态变化推送：{ active: boolean }
  onMainWindowState: (cb) => ipcRenderer.on('main-window-state', (e, data) => cb(data))
});
