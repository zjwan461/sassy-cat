<p align="center">
  <img src="assets/icon.png" alt="优墨" width="120" />
</p>

<h1 align="center">🐱 优墨 · Sassy Cat</h1>

<p align="center">
  <strong>会傲娇但可靠的 AI 桌面猫咪助手</strong> — Electron + Vue 3 + Python
</p>

<p align="center">
  <a href="#-特性总览">特性</a> ·
  <a href="#-界面一览">界面</a> ·
  <a href="#-技术栈">技术栈</a> ·
  <a href="#-架构设计">架构</a> ·
  <a href="#-项目结构">结构</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-使用指南">使用指南</a> ·
  <a href="#-开发指南">开发指南</a> ·
  <a href="#-配置说明">配置</a> ·
  <a href="#-常见问题">FAQ</a>
</p>

<p align="center">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

---

一只傲娇但可靠的桌面猫咪助手 —— 基于 **Electron + Vue 3 + Python** 构建的 AI 桌宠应用。它把 **AI Agent**（LangChain / LangGraph / DeepAgents）与透明置顶的**桌面宠物**相结合：能陪你聊天、帮你盯系统状态、主动提醒你休息，甚至能解析文档、基于你自己的知识库回答问题、动手执行任务。

## ✨ 特性总览

### 🤖 AI 智能对话
- 基于 LangChain / LangGraph / DeepAgents 构建的智能体，支持**流式回复**、**工具调用**、**多轮记忆**（可配置记忆窗口）
- **人设（系统提示词）可自定义**，随时调教你家猫咪的性格
- 多 LLM 供应商配置：OpenAI 兼容接口、DeepSeek 等，可视化切换
- 支持 **MCP 适配器**，接入外部 MCP 工具服务
- 联网搜索（Tavily）、定时/主动提醒等内置工具集

### 🐾 桌面宠物
- 透明、无边框、置顶窗口，精灵帧动画（idle / walk / talk / think / sleep / react 等多种姿态）
- 支持拖拽移动、点击互动、鼠标穿透模式
- 气泡对话：Agent 的回复与提醒会以气泡形式出现在猫咪头顶
- 快捷提问：全局快捷键 `Alt+Shift+Q` 直接在桌宠上快速提问，会话与主窗口实时同步

### 🧠 知识库（RAG）
- 构建本地私有知识库：文档自动分块、向量化入库（ChromaDB）
- 本地嵌入模型 `BAAI/bge-small-zh-v1.5`（缺失时可自动下载），也支持远程嵌入 API
- 知识库管理页支持多库管理、文档上传、详情查看与删除
- Agent 通过检索工具引用知识库内容回答问题

### 📄 文档解析与 OCR
- 支持 PDF / Word / Excel / PPT / 图片 / 文本等多种格式
- 多引擎解析：MarkItDown、Docling、RapidOCR、Unstructured（引擎可在配置中切换）
- 解析结果可直接喂给 Agent 对话，或写入知识库长期沉淀

### ⏰ 主动式交互
- 闲置检测 + 问候调度：长时间不理猫，它会主动冒泡撒娇（"为什么不理本喵😾"）
- 定时提醒工具：让 Agent 帮你设喝水、休息、待办提醒
- 语气（TTS）朗读：支持将回复朗读出来（Web Speech API，可配置音色/语速/音调）

### 🪄 Agent 行动能力
- Agent 可执行 shell 命令、运行 Python、读写/编辑文件；危险操作（execute / write_file / edit_file / delete）默认**需用户确认**（human-in-the-loop 中断）
- **DSH 动手子代理**（DeepSeek Harness）：把多步骤的"体力活"委托给独立工作进程，自动建 todo 清单、逐步执行并汇报，主猫不再被长任务阻塞
- 技能插件体系：`runtime/skills/` 下按约定放置技能目录（含 `SKILL.md`），即装即用，如内置的 `html-ppt` 幻灯片技能

### 📊 系统监控
- 仪表盘实时展示 CPU、GPU（NVIDIA）、内存、磁盘、进程等指标（psutil + pynvml）
- ECharts 图表可视化，支持静态硬件信息展示

### 💬 富文本聊天
- Markdown 渲染 + 代码高亮（highlight.js）+ LaTeX 公式（KaTeX）+ Mermaid 图表
- 流式渲染优化：分块增量渲染，长回复不卡顿
- 会话历史持久化（SQLite），支持多会话、置顶、删除

### 🛠️ 工程能力
- 可视化设置页：LLM 配置、人设、RAG、代理（HTTP/HTTPS）、桌宠偏好、语音等
- **双层配置**：模板默认值（`config.json`）+ 用户覆盖（`config.user.json`），应用升级不丢个人配置
- 数据库迁移：Alembic 管理表结构，启动时自动升级（详见 [MIGRATION.md](MIGRATION.md)）
- 日志页：Python 后端日志实时推送到前端查看
- Python 环境自动检测：缺失时自动下载嵌入式 Python，依赖自动安装
- 一键打包：electron-builder 支持 Windows（NSIS）/ macOS（DMG）/ Linux（AppImage）

## 🖼️ 界面一览

| 页面 | 路由 | 说明 |
|---|---|---|
| 仪表盘 | `#/` | 系统监控图表（CPU / GPU / 内存 / 磁盘） |
| AI 聊天 | `#/chat` | 流式对话、工具调用状态、会话历史、文件附件 |
| 知识库 | `#/kb` | 多知识库管理、文档上传与检索配置 |
| MCP 服务 | `#/mcp` | MCP 服务器配置与管理 |
| 技能管理 | `#/skills` | 技能插件浏览、详情、创建 |
| 设置 | `#/settings` | LLM / 人设 / RAG / 语音 / 代理 / 桌宠 |
| 日志 | `#/logs` | 后端运行日志实时查看 |
| 关于 | `#/about` | 版本与项目链接 |

桌宠窗口为独立页面（`pet/pet.html`），透明置顶，与主窗口通过 IPC/WebSocket 同步状态。

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 桌面框架 | Electron 28 |
| 前端 | Vue 3 (Composition API) + Vue Router + Vite 5 + ECharts |
| 聊天渲染 | markdown-it + highlight.js + KaTeX + Mermaid |
| 后端 | Python 3.11 + FastAPI + uvicorn + asyncio（单进程模型） |
| AI Agent | LangChain + LangGraph + DeepAgents（+ langchain-mcp-adapters） |
| 动手子代理 | deepseek-harness-sdk（DSH 工作进程） |
| 知识库 | ChromaDB + sentence-transformers + langchain-huggingface |
| 文档解析 | MarkItDown + Docling + RapidOCR + Unstructured |
| 持久化 | SQLAlchemy (asyncio) + SQLite (aiosqlite) + Alembic 迁移 |
| 监控采集 | psutil + pynvml + wmi/pywin32 |
| 通信 | WebSocket（聊天/事件）+ IPC（窗口/配置）+ stdio 协议行（监控/日志/就绪信号） |
| 打包 | electron-builder（NSIS / DMG / AppImage） |

## 🏗️ 架构设计

```
┌───────────────────────────── Electron 主进程 (electron/main.js) ─────────────────────────────┐
│  主窗口 (BrowserWindow, src/index.html)      桌宠窗口 (透明置顶, pet/pet.html)      托盘/快捷键  │
│        │ IPC (preload.js)                        │ IPC (pet-preload.js)                       │
│        │                                         │                                            │
│  config-store.js 双层配置读写 ──► config.user.json                                            │
│  python-env-checker.js 检测/下载 Python ──► 启动并监管 python/main.py（stdio [READY]/协议行）   │
└──────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                               │
                    ┌──────────────────────────┴──────────────────────────┐
                    │        Python 后端 (FastAPI, 单进程 asyncio)         │
                    │  /ws/agent   WebSocket：流式对话/工具事件/主动提醒     │
                    │  REST：/api/kb /api/conversations /api/stats         │
                    │       /api/skills /api/mcp                           │
                    │  ┌────────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐  │
                    │  │ Agent 引擎  │ │ RAG 检索  │ │ 监控采集 │ │ 主动调度 │  │
                    │  │ LangGraph  │ │ ChromaDB │ │ psutil  │ │ 闲置问候  │  │
                    │  │ + 工具集    │ │ + OCR    │ │ pynvml  │ │ 定时提醒  │  │
                    │  │ + DSH 子代理│ └──────────┘ └────────┘ └─────────┘  │
                    │  └─────┬──────┘                                       │
                    │        │ SQLite (messages.sqlite) + Alembic 自动迁移   │
                    └────────┴─────────── WebSocket ◄──── 渲染进程直连 ──────┘
```

关键设计点：

- **渲染进程直连 Python WebSocket**：聊天 token 流、工具调用状态、主动提醒事件绕过主进程，低延迟；窗口控制与配置持久化仍走 IPC。
- **单进程 asyncio 后端**：FastAPI 服务、监控采集（`to_thread` 包装阻塞调用）、主动调度、Agent 引擎共存于一个 Python 进程，由 Electron 主进程监管生命周期。
- **stdio 协议行**：Python 通过 stdout 输出 `__PROTOCOL__` 行与 `[READY] {"port":...}` 就绪信号，兼容旧解析逻辑并把日志转发到前端日志页。
- **端口占用回退**：首选端口被占用时自动回退到临时可用端口，主进程据 `[READY]` 广播 `agent-ready`。
- **双层配置**：`config.json`（模板，随应用更新）+ `userData/config.user.json`（用户覆盖，深度合并），升级不丢配置。
- **子代理隔离**：DSH 动手子代理跑在独立工作进程，只拿到被委托的任务描述，多步任务强制先建 todo 清单再执行。

## 📁 项目结构

```
sassy-cat/
├── electron/                      # Electron 主进程
│   ├── main.js                    # 入口（主窗口 + 桌宠窗口 + 托盘 + Python 生命周期）
│   ├── preload.js                 # 主窗口预加载脚本
│   ├── pet-preload.js             # 桌宠窗口预加载脚本
│   ├── config-store.js            # 双层配置读写（深度合并 + 原子写）
│   └── python-env-checker.js      # Python 环境检查/嵌入式 Python 下载
├── src/                           # 主窗口 Vue3 前端
│   ├── views/
│   │   ├── Dashboard.vue          # 系统监控仪表盘
│   │   ├── ChatView.vue           # AI 聊天页（流式 + 工具状态 + 会话历史）
│   │   ├── KnowledgeBase.vue      # 知识库管理
│   │   ├── KnowledgeBaseDetail.vue# 知识库详情（文档列表/上传）
│   │   ├── SkillManager.vue / SkillDetail.vue  # 技能插件管理
│   │   ├── McpManager.vue         # MCP 服务管理
│   │   ├── Settings.vue           # 设置（LLM + 人设 + RAG + 语音 + 代理）
│   │   └── Logs.vue / About.vue / Setup.vue
│   ├── composables/
│   │   ├── useAgentSocket.js      # WebSocket 客户端（单例 + 自动重连）
│   │   ├── useChatStore.js        # 聊天状态管理
│   │   ├── useFileUpload.js       # 文件上传（OCR / RAG）
│   │   ├── useTTS.js              # 语音朗读（Web Speech）
│   │   └── useKbUploadState.js / useModelDownloadState.js / useRestartState.js
│   ├── components/
│   │   ├── MarkdownRenderer.vue   # Markdown/LaTeX/Mermaid 渲染（增量分块）
│   │   ├── ConversationItem.vue / DocumentAttachment.vue / FilePreview.vue
│   ├── utils/streamSplitter.js    # 流式文本分块工具
│   └── api/                       # REST 客户端（kb / messages / stats / skills / mcp）
├── pet/                           # 桌宠窗口（Vite 多页入口）
│   ├── pet.html / pet-main.js
│   ├── assets/sprites/cat/        # 精灵帧图片 + config.json（动作/帧率配置）
│   └── components/
│       ├── PetApp.vue             # 气泡 + 交互 + 状态编排
│       └── sprite/                # 精灵渲染体系（PetSprite / Svg & Spritesheet 渲染器 / 预加载）
├── python/                        # Python 后端（单进程 asyncio）
│   ├── main.py                    # 服务入口（[READY] 就绪信号 + 端口回退）
│   ├── config_loader.py / paths.py / utils.py
│   ├── server/
│   │   ├── app.py                 # FastAPI 实例 + 路由 + lifespan
│   │   ├── ws_agent.py            # /ws/agent 端点 + 会话管理
│   │   ├── bus.py                 # 进程内事件总线
│   │   ├── conversations.py / kb_api.py / stats_api.py / skills_api.py / mcp_api.py
│   │   └── db/                    # SQLAlchemy 模型 + 仓储 + Alembic 迁移 + seed
│   ├── agent/
│   │   ├── engine.py              # Agent 构建（配置注入）
│   │   ├── runner.py / main_agent.py  # 流式对话桥接
│   │   ├── llms.py                # LLM 工厂
│   │   ├── prompts.py             # 人设模板 + 运行时提示词组装
│   │   ├── middlewares.py         # Agent 中间件
│   │   ├── reminders.py           # 提醒上下文注入
│   │   ├── virtual_shell.py       # 沙箱化 shell 执行
│   │   ├── tools/                 # builtin / rag / reminder / mcp / subagent(dsh)
│   │   └── rag/                   # rag_service / document_retriever / model_download
│   ├── monitor/                   # 系统监控采集（cpu / gpu / memory / disks / protocol）
│   ├── ocr/                       # 文档解析（markitdown / docling / rapidocr / xls ...）
│   └── proactive/                 # 闲置检测 + 问候 + 提醒调度
├── runtime/
│   └── skills/                    # 技能插件目录（如内置 html-ppt 幻灯片技能）
├── tests/                         # 临时验证/探针脚本（迁移、流式渲染、提醒等）
├── plans/                         # 设计与迁移方案文档
├── assets/                        # 应用图标
├── config.json                    # 应用配置模板
├── requirements.txt               # Python 依赖
├── vite.config.js                 # Vite 多页配置（index / setup / pet）
├── start.bat                      # Windows 一键开发启动脚本
├── MIGRATION.md                   # 数据库迁移指南
└── package.json                   # Node 依赖与 electron-builder 配置
```

## 🚀 快速开始

### 环境要求

- **Node.js**: 18+
- **npm**: 9+
- **Python**: 3.10+（程序会自动检测；系统没有可用 Python 时会自动下载嵌入式 Python 到 `python_env/`）

### 安装依赖

```bash
npm install
```

### 开发模式

**Windows（推荐，一键脚本）：**
```bash
start.bat
```
脚本会检查 Node/npm、首次运行自动 `npm install`，然后启动开发环境。

**macOS / Linux：**
```bash
npm run electron:dev
```

开发模式通过 `concurrently` 同时启动 Vite 开发服务器（`http://localhost:5173`）和 Electron，前端改动热重载；Python 后端由 Electron 主进程拉起，`requirements.txt` 中的依赖在启动时自动安装。

### 生产构建

```bash
# 构建当前平台
npm run electron:build

# 构建指定平台
npm run electron:build:win     # Windows NSIS 安装包
npm run electron:build:mac     # macOS DMG
npm run electron:build:linux   # Linux AppImage

# 仅构建前端资源并本地预览 Electron
npm run electron:preview
```

构建产物位于 `dist_electron/` 目录。

## 📖 使用指南

### 首次启动

1. 应用启动后会进行环境自检（Python / 依赖安装），`Setup` 页面展示进度。
2. 进入 **设置页** 配置至少一个 LLM：填写 Base URL、API Key、模型名（支持 OpenAI 兼容接口与 DeepSeek 等），保存并切换为当前激活配置。
3. 打开聊天页或直接戳桌宠开始对话；按 `Alt+Shift+Q` 可在桌宠旁快速提问。

### 知识库

1. **知识库页** → 新建知识库。
2. 上传 PDF / Word / Excel / 图片等文档，系统自动解析（OCR/文档引擎）、分块、向量化。
3. 对话时 Agent 会按需检索知识库内容回答（可用 `rag` 工具，也可显式要求"根据知识库回答"）。
4. 嵌入模型默认使用本地 `BAAI/bge-small-zh-v1.5`，首次使用时若缺失会自动下载；也可在设置中改为远程嵌入 API。

### 技能与 MCP

- **技能**：将符合约定的技能目录放入 `runtime/skills/`（包含 `SKILL.md` 描述文件），在技能管理页即可查看/创建/使用。
- **MCP**：在 MCP 管理页添加服务器配置（命令/参数/环境变量），Agent 即可调用其暴露的工具。

### 危险操作确认

Agent 默认在执行 shell 命令、写文件、改文件、删除时**中断等待确认**（可在 `config.json` 的 `agent.interruptOn` 中调整）。

### 主动提醒

桌宠会基于闲置检测主动打招呼；也可以直接让猫"提醒我 10 分钟后喝水"，它会用提醒工具定时冒泡。

## 🔧 开发指南

### 前端（主窗口）

前端使用 Vue 3 + Vite，代码位于 `src/`（别名 `@` 指向该目录）：

- [`ChatView.vue`](src/views/ChatView.vue) — AI 聊天页（流式对话 + 工具调用展示 + 会话历史）
- [`Dashboard.vue`](src/views/Dashboard.vue) — 系统监控仪表盘（ECharts）
- [`KnowledgeBase.vue`](src/views/KnowledgeBase.vue) / [`KnowledgeBaseDetail.vue`](src/views/KnowledgeBaseDetail.vue) — 知识库管理
- [`SkillManager.vue`](src/views/SkillManager.vue) / [`McpManager.vue`](src/views/McpManager.vue) — 扩展管理
- [`Settings.vue`](src/views/Settings.vue) — LLM / 人设 / RAG / 语音 / 代理设置
- [`useAgentSocket.js`](src/composables/useAgentSocket.js) — WebSocket 客户端封装（单例 + 自动重连）
- [`MarkdownRenderer.vue`](src/components/MarkdownRenderer.vue) — 富文本渲染（配合 [`streamSplitter.js`](src/utils/streamSplitter.js) 做增量分块）

Vite 为多页入口：`index.html`（主窗口）、`setup.html`（引导页）、[`pet/pet.html`](pet/pet.html)（桌宠），见 [`vite.config.js`](vite.config.js)。修改前端代码自动热重载。

### 桌宠窗口

桌宠位于 `pet/` 目录，独立 Vite 入口：

- [`PetApp.vue`](pet/components/PetApp.vue) — 气泡、拖拽、点击互动与状态编排
- [`pet/components/sprite/`](pet/components/sprite/) — 精灵渲染体系：[`PetSprite.vue`](pet/components/sprite/PetSprite.vue) 为入口，[`SpritesheetRenderer.vue`](pet/components/sprite/SpritesheetRenderer.vue) / [`SvgSpriteRenderer.vue`](pet/components/sprite/SvgSpriteRenderer.vue) 两种渲染后端，[`useSpritePreload.js`](pet/components/sprite/useSpritePreload.js) 负责帧预加载
- [`pet/assets/sprites/cat/config.json`](pet/assets/sprites/cat/config.json) — 动作/帧动画配置（idle、walk、talk、think、sleep、react、remind 等）
- [`pet-preload.js`](electron/pet-preload.js) — 桌宠专用预加载脚本（窗口穿透、拖动等）

### Python 后端

后端位于 `python/`，FastAPI + 单进程 asyncio：

- [`main.py`](python/main.py) — 服务入口（端口回退 + `[READY]` 就绪信号）
- [`server/ws_agent.py`](python/server/ws_agent.py) — WebSocket 聊天端点与会话管理
- [`agent/engine.py`](python/agent/engine.py) / [`agent/runner.py`](python/agent/runner.py) — Agent 构建与流式桥接
- [`agent/prompts.py`](python/agent/prompts.py) — 人设模板与运行时提示词组装
- [`agent/tools/`](python/agent/tools/) — 工具集：内置命令/文件工具、RAG 检索、提醒、MCP、DSH 子代理
- [`monitor/service.py`](python/monitor/service.py) — 系统监控周期采集
- [`proactive/scheduler.py`](python/proactive/scheduler.py) — 闲置检测/问候/提醒调度

新增 Python 依赖请写入 [`requirements.txt`](requirements.txt)，应用启动时会自动安装。

### 数据库迁移

表结构由 Alembic 管理（`python/server/db/migrations/`），应用启动自动升级，用户无感。开发中新增/修改表请参考 [MIGRATION.md](MIGRATION.md)（autogenerate + 人工审查 + 验证脚本三步走）。

### 测试

`tests/` 目录包含若干临时验证/探针脚本（如 [`tmp_test_migration.py`](tests/tmp_test_migration.py)、[`stream_splitter.test.mjs`](tests/stream_splitter.test.mjs)、[`incremental_render_equivalence.test.mjs`](tests/incremental_render_equivalence.test.mjs)），可按需运行验证对应子系统。

### 通信架构

| 数据类型 | 通道 | 说明 |
|---|---|---|
| AI 对话 / 流式 token / 工具事件 / 主动提醒 | WebSocket | 渲染进程直连 Python，低延迟 |
| 配置持久化（LLM / 人设 / 桌宠偏好） | IPC | 主进程读写 `config.user.json` |
| 系统监控数据 / 后端日志 / 就绪信号 | stdio 协议行 + IPC | `__PROTOCOL__` 行 + `[READY] {"port":...}` |
| 窗口控制（拖动 / 置顶 / 穿透） | IPC | 主进程管理 |

## ⚙️ 配置说明

### 应用配置模板（config.json）

项目基础配置维护在根目录 [`config.json`](config.json)（模板层，随应用更新）：

```json
{
  "app": { "name": "优墨", "version": "1.0.0" },
  "agent": {
    "memoryWindow": 50,
    "recursionLimit": 100,
    "enableOcr": true,
    "ocrEngine": "markitdown",
    "interruptOn": { "execute": true, "write_file": true, "edit_file": true, "delete": true }
  },
  "dsh": { "useMainLlm": true, "maxTokens": 131072, "reasoningEffort": "" },
  "rag": {
    "autoEmbedding": true,
    "embeddingModel": { "type": "local", "model": "BAAI/bge-small-zh-v1.5" },
    "ocrEngine": "docling"
  },
  "pet": {
    "enabled": true,
    "quickAsk": { "shortcut": "Alt+Shift+Q" },
    "reminders": { "pollIntervalSeconds": 5, "bubbleDurationMs": 8000 }
  },
  "voice": { "enabled": false, "engine": "web-speech", "autoRead": false, "rate": 1.0, "pitch": 1.0 },
  "network": { "proxy": { "enabled": false, "http": "", "https": "", "noProxy": "" } },
  "pythonVersion": "3.11.9"
}
```

主要字段：

| 段 | 说明 |
|---|---|
| `agent` | 记忆窗口、递归上限、OCR 开关与引擎、危险操作确认（`interruptOn`） |
| `dsh` | 动手子代理：LLM 来源（默认复用主模型）、maxTokens、推理强度 |
| `rag` | 嵌入模型（本地/远程）、自动嵌入、知识库文档解析引擎 |
| `pet` | 桌宠开关、快捷提问热键、提醒轮询与气泡时长 |
| `voice` | 语音朗读开关、引擎、自动朗读、音色/语速/音调 |
| `network` | HTTP/HTTPS 代理 |

### 用户配置（config.user.json）

运行时用户配置（LLM 连接、人设提示词、桌宠偏好等）存储在 Electron `userData/config.user.json`，通过设置页可视化编辑。采用**双层配置**设计：模板默认值 + 用户覆盖深度合并，应用升级不丢失个人配置。

### 自定义 Python 版本

修改 `config.json` 中的 `pythonVersion`，重启应用生效。若已下载过嵌入式 Python，需删除 `python_env` 目录后重启。

## 📦 打包说明

将应用图标放置在 `assets/` 目录：

- `icon.ico` — Windows 图标
- `icon.icns` — macOS 图标
- `icon.png` — Linux 图标

`electron-builder` 的 `extraResources` 会自动将 `requirements.txt`、`python/`、`config.json`、`assets/`、`runtime/skills/` 打包进应用。Windows 安装包为 NSIS 格式，支持自选安装目录、创建桌面/开始菜单快捷方式（配置见 [`package.json`](package.json) 的 `build` 段）。

## ❓ 常见问题

<details>
<summary><b>启动后 Python 服务没起来 / 聊天无响应？</b></summary>

- 打开 **日志页** 查看后端输出；首次启动会自动下载嵌入式 Python 并安装 `requirements.txt` 依赖，耗时较长属正常。
- 若端口被占用，后端会自动回退到随机可用端口，一般无需处理。
- 依赖安装失败多为网络问题，可在设置中配置代理后重启。

</details>

<details>
<summary><b>知识库嵌入模型没有下载成功？</b></summary>

默认从 HuggingFace 下载 `BAAI/bge-small-zh-v1.5`，网络受限时请在设置中配置代理，或将嵌入模型改为远程 API。

</details>

<details>
<summary><b>桌宠不显示 / 位置不对？</b></summary>

桌宠开关在设置页与 `config.json` 的 `pet.enabled`。桌宠窗口透明置顶，找不到时可从托盘菜单切换显示。

</details>

<details>
<summary><b>Agent 每次执行命令都要确认，太繁琐？</b></summary>

确认行为由 `config.json` 的 `agent.interruptOn` 控制，可按工具逐项关闭（不推荐全部关闭）。

</details>

## 🗺️ 开发路线图

进行中的设计/迁移方案记录在 [`plans/`](plans/) 目录，包括：

- ✅ 桌宠精灵动画迁移（[`pet-sprite-migration-plan.md`](plans/pet-sprite-migration-plan.md)）
- ✅ 语音朗读 TTS（[`tts-voice-read-aloud-plan.md`](plans/tts-voice-read-aloud-plan.md)）
- ✅ 流式 Markdown 渲染性能优化（[`streaming-markdown-render-perf-plan.md`](plans/streaming-markdown-render-perf-plan.md)）
- ✅ DSH 动手子代理设置（[`dsh-settings-plan.md`](plans/dsh-settings-plan.md)）
- 🚧 Agent 错误重试（[`agent-error-retry-plan.md`](plans/agent-error-retry-plan.md)）
- 🚧 上下文窗口压缩（[`context-window-compression-plan.md`](plans/context-window-compression-plan.md)）

## 📝 许可证

[Apache License 2.0](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！建议改动前先阅读 [`plans/`](plans/) 中相关设计文档，保持架构一致。

## 📮 反馈

如有问题，请前往 [项目主页](https://github.com/zjwan461/sassy-cat) 提交 Issue，或查看 [更新日志](https://github.com/zjwan461/sassy-cat/releases)。
