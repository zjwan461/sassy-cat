// 项目信息统一从根目录 config.json 读取（Vite 原生支持 JSON 导入）
import rawConfig from '../config.json'

const defaults = {
  name: 'SS Client',
  description: 'Electron + Python 应用控制面板',
  introduction: '基于 Electron + Vue 3 + Python 构建的桌面应用脚手架。',
  version: '1.0.0',
  logo: '🔐'
}

export const appConfig = {
  ...defaults,
  ...(rawConfig.app || {})
}

export const pythonVersion = rawConfig.pythonVersion || '3.11.9'

// 相关链接配置（来自 config.json 的 links 字段）
export const appLinks = Array.isArray(rawConfig.links) ? rawConfig.links : []
