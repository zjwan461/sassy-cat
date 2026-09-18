<p align="center">
  <img src="assets/icon.png" alt="优墨" width="120" />
</p>

<h1 align="center">🐱 优墨 · Sassy Cat</h1>

<p align="center">
  <strong>会傲娇但可靠的 AI 桌面猫咪助手</strong> — Electron + Vue 3 + Python
</p>

<p align="center">
  <a href="#-特性">特性</a> ·
  <a href="#-技术栈">技术栈</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-开发指南">开发指南</a> ·
  <a href="#-配置说明">配置说明</a>
</p>

<p align="center">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

---

一只傲娇但可靠的桌面猫咪助手 —— 基于 **Electron + Vue 3 + Python** 构建的 AI 桌宠应用。它把 **AI Agent**（LangChain / LangGraph）与透明置顶的**桌面宠物**相结合：能陪你聊天、帮你盯系统状态、主动提醒你休息，甚至能解析文档、基于你自己的知识库回答问题。

## ✨ 特性

- 🤖 **AI 智能对话**：基于 LangChain / LangGraph / DeepAgents，支持流式回复、工具调用、多轮记忆，人设（系统提示词）可自定义
- 🐾 **桌面宠物**：透明置顶窗口 + 精灵帧动画，支持拖拽、点击互动、气泡对话
- 💬 **双入口聊天**：主窗口完整聊天页 + 桌宠气泡快捷提问（快捷键 `Alt+Shift+Q`），会话实时同步
- 🧠 **知识库（RAG）**：构建本地知识库，自动文档分块、向量检索（ChromaDB）+ 本地嵌入模型（BAAI/bge-small-zh-v1.5，缺失时自动下载）
- 📄 **文档解析与 OCR**：支持上传 PDF / Word / Excel / 图片等，由 MarkItDown、Docling、RapidOCR 等解析后喂给 Agent 或写入知识库
- ⏰ **主动提醒**：闲置检测 + 问候调度，桌宠会主动冒泡（"为什么不理本喵😾"），并支持定时提醒工具
- 🧩 **技能与工具扩展**：内置工具集 + 技能插件体系（`runtime/skills/`，如天气查询），并支持 MCP 适配器
- 🪄 **Agent 行动能力**：Agent 可执行命令、运行 Python、读写文件（危险操作前需确认）
- 📊 **系统监控**：仪表盘实时展示 CPU、GPU、内存、磁盘等指标
- 💬 **富文本聊天渲染**：聊天中支持 Markdown、代码高亮、LaTeX 公式（KaTeX）与 Mermaid 图表
- 🛠️ **灵活配置**：可视化设置页，支持多 LLM 配置切换、人设编辑、代理配置、RAG 选项
- 🎨 **双层配置**：模板默认值 + 用户覆盖，应用升级不丢失个人配置
- 📦 **一键打包**：基于 electron-builder 支持 Windows / macOS / Linux 多平台构建

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 桌面框架 | Electron 28 |
| 前端 | Vue 3 (Composition API) + Vue Router + Vite 5 + ECharts |
| 后端 | Python 3.11 + FastAPI + uvicorn + asyncio |
| AI Agent | LangChain + LangGraph + DeepAgents（+ MCP 适配器） |
| 知识库 | ChromaDB + sentence-transformers + langchain-huggingface |
| 文档解析 | MarkItDown + Docling + RapidOCR + Unstructured |
| 持久化 | SQLAlchemy + SQLite + Alembic 迁移 |
| 监控采集 | psutil + pynvml |
| 通信 | WebSocket（聊天/事件）+ IPC（窗口/配置）+ stdio 协议行（监控） |
| 打包 | electron-builder |

## 📁 项目结构

```
sassy-cat/
├── electron/                  # Electron 主进程
│   ├── main.js               # 入口（主窗口 + 桌宠窗口 + 托盘管理）
│   ├── preload.js            # 主窗口预加载脚本
│   ├── pet-preload.js        # 桌宠窗口预加载脚本
│   ├── config-store.js       # 双层配置读写（深度合并 + 原子写）
│   └── python-env-checker.js # Python 环境检查器
├── src/                       # 主窗口 Vue3 前端
│   ├── views/
│   │   ├── ChatView.vue      # AI 聊天页（流式对话 + 工具状态）
│   │   ├── Dashboard.vue     # 系统监控仪表盘
│   │   ├── KnowledgeBase.vue # 知识库管理
│   │   ├── Settings.vue      # 设置页（LLM + 人设 + RAG + 代理）
│   │   ├── Logs.vue / About.vue / Setup.vue
│   ├── composables/
│   │   ├── useAgentSocket.js # WebSocket 客户端（单例 + 自动重连）
│   │   ├── useChatStore.js   # 聊天状态管理
│   │   ├── useFileUpload.js  # 文件上传（OCR / RAG）
│   │   └── ...
│   ├── components/
│   │   ├── MarkdownRenderer.vue # Markdown/LaTeX/Mermaid 渲染
│   │   ├── DocumentAttachment.vue / FilePreview.vue
│   └── api/                  # REST 客户端（kb / messages / stats）
├── pet/                       # 桌宠窗口（Vite 多页入口）
│   ├── pet.html / pet-main.js
│   └── components/PetApp.vue # 精灵动画 + 气泡 + 互动
├── python/                    # Python 后端
│   ├── main.py               # 入口（asyncio + FastAPI）
│   ├── server/
│   │   ├── app.py            # FastAPI 实例 + 路由 + lifespan
│   │   ├── ws_agent.py       # /ws/agent 端点 + 会话管理
│   │   ├── conversations.py  # 会话历史 API
│   │   ├── kb_api.py         # 知识库 API
│   │   ├── stats_api.py      # 监控数据 API
│   │   └── db/               # SQLAlchemy 模型 + Alembic 迁移
│   ├── agent/
│   │   ├── engine.py         # Agent 构建（配置注入）
│   │   ├── llms.py           # LLM 工厂
│   │   ├── prompts.py        # 人设模板 + 运行时提示词拼接
│   │   ├── main_agent.py     # 流式对话核心
│   │   ├── middlewares.py    # Agent 中间件
│   │   ├── tools/            # builtin_tools / rag_tools / reminder_tools
│   │   └── rag/              # document_retriever / rag_service / model_download
│   ├── monitor/              # 系统监控采集（cpu / gpu / memory / disks）
│   ├── ocr/                  # 文档解析（markitdown / docling / rapidocr）
│   └── proactive/            # 闲置检测 + 问候 + 提醒
├── runtime/skills/            # 技能插件目录（如 weather-skill）
├── assets/                    # 静态资源（图标等）
├── config.json               # 应用配置模板
├── package.json              # Node.js 依赖
├── requirements.txt          # Python 依赖
├── vite.config.js            # Vite 配置（多页入口）
├── start.bat                 # Windows 启动脚本
└── plans/                    # 设计与迁移文档
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

**macOS / Linux:**
```bash
npm run electron:dev
```

开发模式会同时启动 Vite 开发服务器和 Electron 应用，支持热重载。

### 生产构建

```bash
# 构建所有平台
npm run electron:build

# 构建指定平台
npm run electron:build:win
npm run electron:build:mac
npm run electron:build:linux
```

构建产物位于 `dist_electron/` 目录。

## 🔧 开发指南

### 前端（主窗口）

前端使用 Vue 3 + Vite，代码位于 `src/` 目录：

- [`ChatView.vue`](src/views/ChatView.vue) — AI 聊天页，流式对话 + 工具调用展示
- [`Dashboard.vue`](src/views/Dashboard.vue) — 系统监控仪表盘
- [`KnowledgeBase.vue`](src/views/KnowledgeBase.vue) — 知识库管理
- [`Settings.vue`](src/views/Settings.vue) — LLM / 人设 / RAG / 代理设置
- [`useAgentSocket.js`](src/composables/useAgentSocket.js) — WebSocket 客户端封装

修改前端代码会自动热重载。

### 桌宠窗口

桌宠使用独立的 Vite 多页入口，位于 `pet/` 目录：

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
    "version": "1.0.0"
  },
  "agent": { "memoryWindow": 50, "recursionLimit": 100, "ocrEngine": "markitdown" },
  "rag": { "autoEmbedding": true, "embeddingModel": { "type": "local", "model": "BAAI/bge-small-zh-v1.5" }, "ocrEngine": "docling" },
  "network": { "proxy": { "enabled": false } },
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

[Apache License 2.0](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📮 反馈

如有问题，请前往 [项目主页](https://gitee.com/zjwan461/sassy-cat) 提交 Issue。