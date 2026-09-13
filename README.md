# 🐱 优墨（Sassy Cat）

一只傲娇但可靠的桌面猫咪助手 —— 基于 Electron + Vue 3 + Python 构建的 AI 桌宠应用。

## ✨ 特性

- 🤖 **AI 智能对话**：集成 LangChain / LangGraph Agent，支持流式回复、工具调用、多轮对话
- 🐾 **桌面宠物**：透明置顶窗口，精灵帧动画，支持拖拽、点击互动、气泡对话
- 💬 **双入口聊天**：主窗口完整聊天页 + 桌宠气泡快捷输入，会话实时同步
- 📊 **系统监控**：实时查看 CPU、GPU、内存、磁盘等系统指标
- ⚙️ **灵活配置**：可视化设置页，支持多 LLM 配置切换、系统提示词（人设）自定义编辑
- 🔔 **主动提醒**：闲置检测，桌宠会主动冒泡提醒（"为什么不理本喵😾"）
- 🧩 **技能扩展**：支持内置工具和技能插件（如天气查询）
- 🎨 **双层配置**：模板默认值 + 用户覆盖，升级不丢失个人配置
- 🔌 **WebSocket 通信**：渲染进程直连 Python 后端，低延迟流式传输
- 📦 **一键打包**：支持 Windows / macOS / Linux 多平台打包

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 桌面框架 | Electron 28 |
| 前端 | Vue 3 (Composition API) + Vue Router + Vite 5 |
| 后端 | Python 3.11 + FastAPI + uvicorn |
| AI Agent | LangChain + LangGraph + deepagents |
| 通信 | WebSocket（聊天/事件）+ IPC（窗口控制/配置）+ stdio 协议行（监控） |
| 打包 | electron-builder |

## 📁 项目结构

```
sassy-cat/
├── electron/                  # Electron 主进程
│   ├── main.js               # 主进程入口（主窗口 + 桌宠窗口 + 托盘管理）
│   ├── preload.js            # 主窗口预加载脚本
│   ├── pet-preload.js        # 桌宠窗口预加载脚本
│   ├── config-store.js       # 双层配置读写（深度合并 + 原子写）
│   └── python-env-checker.js # Python 环境检查器
├── src/                       # 主窗口 Vue3 前端
│   ├── views/
│   │   ├── ChatView.vue      # AI 聊天页（流式对话 + 工具状态）
│   │   ├── Dashboard.vue     # 系统监控仪表盘
│   │   ├── Settings.vue      # 设置页（LLM 配置 + 人设编辑）
│   │   ├── Logs.vue          # 日志查看
│   │   ├── About.vue         # 关于页
│   │   ├── Setup.vue         # 环境检查页面
│   │   └── ...
│   ├── composables/
│   │   └── useAgentSocket.js # WebSocket 客户端（单例 + 自动重连）
│   ├── App.vue               # 根组件
│   ├── main.js               # Vue 应用入口
│   └── styles.css            # 全局样式
├── pet/                       # 桌宠窗口（Vite 多页入口）
│   ├── pet.html
│   ├── pet-main.js
│   └── components/PetApp.vue # 精灵动画 + 气泡 + 互动
├── python/                    # Python 后端
│   ├── main.py               # 入口（asyncio + FastAPI）
│   ├── server/               # WebSocket 服务层
│   │   ├── app.py            # FastAPI 实例 + 路由 + lifespan
│   │   ├── ws_agent.py       # /ws/agent 端点 + 会话管理
│   │   ├── protocol.py       # WS 消息模型定义
│   │   └── bus.py            # 服务端事件总线
│   ├── agent/                # AI Agent 引擎
│   │   ├── engine.py         # Agent 构建（配置注入）
│   │   ├── llms.py           # LLM 工厂
│   │   ├── prompts.py        # 人设模板 + 运行时提示词拼接
│   │   ├── main_agent.py     # 流式对话核心
│   │   └── builtin_tools.py  # 内置工具集
│   ├── monitor/              # 系统监控采集
│   │   ├── service.py        # 采集调度
│   │   ├── cpu.py / gpu.py / memory.py / disks.py ...
│   │   └── ...
│   └── proactive/            # 主动提醒引擎
│       └── scheduler.py      # 闲置检测 + 提醒规则
├── runtime/skills/            # 技能插件目录
├── assets/                    # 静态资源（图标等）
├── config.json               # 应用配置模板
├── package.json              # Node.js 依赖
├── requirements.txt          # Python 依赖
├── vite.config.js            # Vite 配置（多页入口）
├── start.bat                 # Windows 启动脚本
└── plans/sassy-cat-design.md # 详细设计文档
```

## 🚀 快速开始

### 环境要求

- **Node.js**: 18+
- **npm**: 9+
- **Python**: 3.10+（程序会自动检测，缺失时自动下载嵌入式 Python）

### 安装依赖

```bash
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

```bash
# 构建所有平台
npm run electron:build

# 仅构建 Windows
npm run electron:build:win

# 仅构建 macOS
npm run electron:build:mac

# 仅构建 Linux
npm run electron:build:linux
```

构建产物位于 `dist_electron/` 目录。

## 🔧 开发指南

### 前端（主窗口）

前端使用 Vue 3 + Vite，代码位于 `src/` 目录：

- [`ChatView.vue`](src/views/ChatView.vue) — AI 聊天页，流式对话 + 工具调用展示
- [`Dashboard.vue`](src/views/Dashboard.vue) — 系统监控仪表盘
- [`Settings.vue`](src/views/Settings.vue) — LLM 配置 + 人设/系统提示词编辑
- [`useAgentSocket.js`](src/composables/useAgentSocket.js) — WebSocket 客户端封装

修改前端代码会自动热重载。

### 桌宠窗口

桌宠使用 Vite 多页入口，代码位于 `pet/` 目录：

- [`PetApp.vue`](pet/components/PetApp.vue) — 精灵动画 + 气泡 + 交互逻辑
- [`pet-preload.js`](electron/pet-preload.js) — 桌宠专用预加载脚本

### Python 后端

后端代码位于 `python/` 目录，基于 FastAPI + asyncio：

- [`main.py`](python/main.py) — 服务入口
- [`server/ws_agent.py`](python/server/ws_agent.py) — WebSocket 聊天端点
- [`agent/engine.py`](python/agent/engine.py) — Agent 构建引擎
- [`monitor/service.py`](python/monitor/service.py) — 系统监控采集

在 `requirements.txt` 中添加 Python 依赖，程序启动时会自动安装。

### 通信架构

| 数据类型 | 通道 | 说明 |
|---|---|---|
| AI 对话 / 流式 token / 主动提醒 | WebSocket | 渲染进程直连 Python，低延迟 |
| 配置持久化（LLM / 人设 / 桌宠偏好） | IPC | 主进程读写 config.user.json |
| 系统监控数据 | stdio 协议行 + IPC | 兼容现有解析逻辑 |
| 窗口控制（拖动 / 置顶 / 穿透） | IPC | 主进程管理 |

## ⚙️ 配置说明

### 应用配置（config.json）

项目基础信息维护在根目录 [`config.json`](config.json) 中：

```json
{
  "app": {
    "name": "优墨",
    "description": "结合AI Agent能力的桌宠",
    "version": "1.0.0"
  },
  "pythonVersion": "3.11.9"
}
```

### 用户配置（config.user.json）

运行时用户配置（LLM 连接、人设提示词、桌宠偏好等）存储在 `userData/config.user.json`，通过设置页可视化编辑，采用双层配置设计（模板 + 用户覆盖），应用升级不丢失。

### 自定义 Python 版本

修改 `config.json` 中的 `pythonVersion`，重启应用生效。若已下载过嵌入式 Python，需删除 `python_env` 目录后重启。

## 📦 打包说明

将应用图标放置在 `assets/` 目录：

- `icon.ico` — Windows 图标
- `icon.icns` — macOS 图标
- `icon.png` — Linux 图标

`extraResources` 配置会自动将 `requirements.txt`、`python/`、`config.json`、`assets/` 打包到应用中。

## 📝 许可证

Apache License 2.0

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📮 反馈

如有问题，请前往 [项目主页](https://gitee.com/zjwan461/sassy-cat) 提交 Issue。
