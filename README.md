# Electron + Python + Vue3 桌面应用脚手架

一个现代化的桌面应用脚手架，基于 Electron + Python + Vue3 技术栈，提供开箱即用的开发环境。

## ✨ 特性

- 🚀 **现代化技术栈**：Electron 28 + Vue 3 + Vite 5
- 🐍 **Python 后端**：支持 Python 3.9+，自动环境检测和依赖安装
- 🎨 **Vue3 前端**：使用 Composition API 和 Vue Router
- ⚡ **Vite 构建**：快速的热重载和构建
- 🔧 **开发友好**：开发环境自动热更新
- 📦 **一键打包**：支持 Windows/macOS/Linux 多平台打包
- 🛡️ **环境检查**：启动时自动检测 Python 环境，缺失时自动下载安装
- 🎯 **系统托盘**：内置系统托盘支持

## 📁 项目结构

```
demo/
├── electron/              # Electron 主进程
│   ├── main.js           # 主进程入口
│   ├── preload.js        # 预加载脚本
│   └── python-env-checker.js  # Python 环境检查器
├── src/                  # Vue3 前端源码
│   ├── views/
│   │   ├── Home.vue     # 主页面
│   │   └── Setup.vue    # 环境检查页面
│   ├── App.vue          # 根组件
│   ├── main.js          # Vue 应用入口
│   ├── setup.js         # Setup 页面入口
│   └── styles.css       # 全局样式
├── python/               # Python 后端
│   └── main.py          # Python 服务入口
├── assets/               # 静态资源（图标等）
├── index.html           # 主页面 HTML
├── setup.html           # 环境检查页面 HTML
├── package.json         # Node.js 依赖
├── vite.config.js       # Vite 配置
├── requirements.txt     # Python 依赖
├── start.bat            # Windows 启动脚本
└── README.md            # 项目说明
```

## 🚀 快速开始

### 环境要求

- **Node.js**: 18+ 
- **npm**: 9+
- **Python**: 3.9+（可选，程序会自动检测和安装）

### 安装依赖

```bash
cd demo
npm install
```

### 开发模式

**Windows:**
```bash
start.bat
```

**macOS/Linux:**
```bash
npm run electron:dev
```

开发模式会同时启动 Vite 开发服务器和 Electron 应用，支持热重载。

### 生产构建

**构建所有平台:**
```bash
npm run electron:build
```

**仅构建 Windows:**
```bash
npm run electron:build:win
```

**仅构建 macOS:**
```bash
npm run electron:build:mac
```

**仅构建 Linux:**
```bash
npm run electron:build:linux
```

构建产物位于 `dist_electron/` 目录。

## 🔧 开发指南

### 前端开发

前端使用 Vue3 + Vite，代码位于 `src/` 目录：

- `src/views/Home.vue` - 主页面
- `src/views/Setup.vue` - 环境检查页面
- `src/App.vue` - 根组件
- `src/main.js` - Vue 应用入口

修改前端代码会自动热重载。

### 后端开发

Python 后端代码位于 `python/` 目录：

- `python/main.py` - Python 服务入口
- `requirements.txt` - Python 依赖列表

在 `requirements.txt` 中添加需要的 Python 包，程序启动时会自动安装。

### 主进程开发

Electron 主进程代码位于 `electron/` 目录：

- `electron/main.js` - 主进程入口
- `electron/preload.js` - 预加载脚本
- `electron/python-env-checker.js` - Python 环境检查器

修改主进程代码需要重启 Electron 应用。

### IPC 通信

通过 `preload.js` 暴露的 API 进行前后端通信：

```javascript
// 前端调用
const result = await window.electronAPI.startService()
const status = await window.electronAPI.getStatus()

// 监听事件
window.electronAPI.onStatusUpdate((status) => {
  console.log('状态更新:', status)
})
```

## 📦 打包说明

### 配置打包

编辑 `package.json` 中的 `build` 字段进行配置：

```json
{
  "build": {
    "appId": "com.yourcompany.app",
    "productName": "Your App Name",
    "directories": {
      "output": "dist_electron"
    }
  }
}
```

### 添加图标

将应用图标放置在 `assets/` 目录：

- `icon.ico` - Windows 图标
- `icon.icns` - macOS 图标
- `icon.png` - Linux 图标

### 打包资源

`extraResources` 配置会自动将以下资源打包到应用中：

- `requirements.txt` - Python 依赖
- `python/` - Python 代码
- `assets/` - 静态资源

## 🐍 Python 环境

### 环境检测流程

应用启动时会自动检测 Python 环境：

1. 检查虚拟环境（`.venv` 或 `python_env`）
2. 检查依赖是否已安装
3. 检查系统 Python 版本
4. 如未找到，自动下载嵌入式 Python
5. 自动安装依赖

### 项目配置（config.json）

项目信息统一维护在根目录 `config.json` 中，界面（侧边栏、仪表盘、关于页）与主进程窗口标题、托盘提示均从此读取：

```json
{
  "app": {
    "name": "SS Client",
    "description": "Electron + Python 应用控制面板",
    "introduction": "基于 Electron + Vue 3 + Python 构建的桌面应用脚手架。",
    "version": "1.0.0",
    "logo": "🔐"
  },
  "pythonVersion": "3.11.9"
}
```

### 自定义 Python 版本

将 `pythonVersion` 修改为需要的完整版本号（如 `3.12.7`、`3.10.11`），主次版本会自动推导。修改后重启应用生效；若已下载过嵌入式 Python，需删除 `python_env` 目录后重启以重新配置环境。

### 添加 Python 依赖

在 `requirements.txt` 中添加：

```
requests==2.31.0
flask==3.0.0
numpy==1.24.0
```

## 🎨 自定义

### 修改应用名称

编辑 `package.json`：

```json
{
  "name": "your-app-name",
  "productName": "Your App Name"
}
```

### 修改窗口大小

编辑 `electron/main.js`：

```javascript
mainWindow = new BrowserWindow({
  width: 1200,  // 修改宽度
  height: 800,  // 修改高度
  // ...
})
```

### 修改主题颜色

编辑 `src/styles.css` 和各个 Vue 组件的 `<style>` 部分。

## 📝 许可证

MIT

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📮 联系方式

如有问题，请提交 Issue。
