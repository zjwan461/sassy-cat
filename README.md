<p align="center">
  <img src="assets/icon.png" alt="Sassy Cat" width="120" />
</p>

<h1 align="center">🐱 优墨 · Sassy Cat</h1>

<p align="center">
  <strong>An AI desktop pet assistant</strong> — Electron + Vue 3 + Python
</p>

<p align="center">
  <a href="#-features">Features</a> ·
  <a href="#-tech-stack">Tech Stack</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-development-guide">Dev Guide</a> ·
  <a href="#-configuration">Configuration</a>
</p>

<p align="center">
  <strong>English</strong> | <a href="README.zh-CN.md">简体中文</a>
</p>

---

A slightly sassy but dependable desktop cat companion. Built with **Electron + Vue 3 + Python**, it combines an **AI Agent** (LangChain / LangGraph) with a transparent, always-on-top **desktop pet** that chats with you, watches your system, reminds you to take a break, and can even read documents and answer questions from your own knowledge base.

## ✨ Features

- 🤖 **AI Conversational Agent** — Powered by LangChain / LangGraph / DeepAgents, with streaming replies, tool calling, multi-turn memory, and a customizable system persona (人设)
- 🐾 **Desktop Pet** — Transparent, always-on-top window with sprite frame animations; drag it around, click to interact, and read bubble messages
- 💬 **Dual Chat Entry** — Full chat page in the main window + a quick-ask bubble on the pet (shortcut `Alt+Shift+Q`), with real-time session sync
- 🧠 **Knowledge Base (RAG)** — Build your own local knowledge base with automatic document chunking, vector search (ChromaDB) and a local embedding model (BAAI/bge-small-zh-v1.5, auto-downloaded if missing)
- 📄 **Document Parsing & OCR** — Upload PDF / Word / Excel / images and more; parsed with MarkItDown, Docling, RapidOCR, etc., then fed to the agent or indexed into the knowledge base
- ⏰ **Proactive Reminders** — Idle detection and greeting scheduling; the pet proactively bubbles up ("Why aren't you talking to me? 😾"), plus scheduled reminder tools
- 🧩 **Skill & Tool Extensions** — Built-in toolkits plus a skill plugin system (`runtime/skills/`, e.g. weather query), with MCP adapter support
- 🪄 **Agent Actions** — The agent can run commands, execute Python, and read/write files (with confirmation before dangerous actions)
- 📊 **System Monitoring** — Real-time CPU, GPU, memory, and disk metrics on a dashboard
- 💬 **Rich Chat Rendering** — Markdown, code highlighting, LaTeX (KaTeX) and Mermaid diagrams rendered in chat
- 🛠️ **Flexible Settings** — Visual settings page with multiple LLM provider profiles, persona / system prompt editing, proxy configuration, and RAG options
- 🎨 **Dual-Layer Config** — Template defaults + user overrides; personal settings survive app upgrades
- 📦 **One-Click Packaging** — Cross-platform builds for Windows / macOS / Linux via electron-builder

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Desktop Framework | Electron 28 |
| Frontend | Vue 3 (Composition API) + Vue Router + Vite 5 + ECharts |
| Backend | Python 3.11 + FastAPI + uvicorn + asyncio |
| AI Agent | LangChain + LangGraph + DeepAgents (+ MCP adapters) |
| Knowledge Base | ChromaDB + sentence-transformers + langchain-huggingface |
| Document Parsing | MarkItDown + Docling + RapidOCR + Unstructured |
| Persistence | SQLAlchemy + SQLite + Alembic migrations |
| Monitoring | psutil + pynvml |
| Communication | WebSocket (chat/events) + IPC (window/config) + stdio protocol lines (monitor) |
| Packaging | electron-builder |

## 📁 Project Structure

```
sassy-cat/
├── electron/                  # Electron main process
│   ├── main.js               # Entry: main window + pet window + tray
│   ├── preload.js            # Main window preload script
│   ├── pet-preload.js        # Pet window preload script
│   ├── config-store.js       # Dual-layer config (deep merge + atomic write)
│   └── python-env-checker.js # Python environment checker
├── src/                       # Main window Vue 3 frontend
│   ├── views/
│   │   ├── ChatView.vue      # AI chat page (streaming + tool states)
│   │   ├── Dashboard.vue     # System monitor dashboard
│   │   ├── KnowledgeBase.vue # RAG knowledge base management
│   │   ├── Settings.vue      # Settings (LLM + persona + RAG + proxy)
│   │   ├── Logs.vue / About.vue / Setup.vue
│   ├── composables/
│   │   ├── useAgentSocket.js # WebSocket client (singleton + auto-reconnect)
│   │   ├── useChatStore.js   # Chat state store
│   │   ├── useFileUpload.js  # File upload (OCR / RAG)
│   │   └── ...
│   ├── components/
│   │   ├── MarkdownRenderer.vue # Markdown/LaTeX/Mermaid rendering
│   │   ├── DocumentAttachment.vue / FilePreview.vue
│   └── api/                  # REST clients (kb / messages / stats)
├── pet/                       # Pet window (Vite multi-page entry)
│   ├── pet.html / pet-main.js
│   └── components/PetApp.vue # Sprite animation + bubbles + interaction
├── python/                    # Python backend
│   ├── main.py               # Entry (asyncio + FastAPI)
│   ├── server/
│   │   ├── app.py            # FastAPI app + routes + lifespan
│   │   ├── ws_agent.py       # /ws/agent endpoint + session management
│   │   ├── conversations.py  # Conversation history APIs
│   │   ├── kb_api.py         # Knowledge base APIs
│   │   ├── stats_api.py      # Monitor stats APIs
│   │   └── db/               # SQLAlchemy models + Alembic migrations
│   ├── agent/
│   │   ├── engine.py         # Agent builder (config injection)
│   │   ├── llms.py           # LLM factory
│   │   ├── prompts.py        # Persona templates + runtime prompt assembly
│   │   ├── main_agent.py     # Streaming conversation core
│   │   ├── middlewares.py    # Agent middlewares
│   │   ├── tools/            # builtin_tools / rag_tools / reminder_tools
│   │   └── rag/              # document_retriever / rag_service / model_download
│   ├── monitor/              # System monitoring (cpu / gpu / memory / disks)
│   ├── ocr/                  # Document parsing (markitdown / docling / rapidocr)
│   └── proactive/            # Idle detection + greetings + reminders
├── runtime/skills/            # Skill plugin directory (e.g. weather-skill)
├── assets/                    # Static assets (icons)
├── config.json               # App config template
├── package.json              # Node.js dependencies
├── requirements.txt          # Python dependencies
├── vite.config.js            # Vite config (multi-page)
├── start.bat                 # Windows start script
└── plans/                    # Design & migration docs
```

## 🚀 Quick Start

### Requirements

- **Node.js**: 18+
- **npm**: 9+
- **Python**: 3.10+ (auto-detected; an embedded Python is downloaded automatically if missing)

### Install Dependencies

```bash
npm install
```

### Development Mode

**Windows:**
```bash
start.bat
```

**macOS / Linux:**
```bash
npm run electron:dev
```

Development mode launches the Vite dev server and the Electron app together, with hot reload.

### Production Build

```bash
# Build for all platforms
npm run electron:build

# Build for a specific platform
npm run electron:build:win
npm run electron:build:mac
npm run electron:build:linux
```

Build artifacts are output to the `dist_electron/` directory.

## 🔧 Development Guide

### Frontend (Main Window)

The frontend uses Vue 3 + Vite and lives in `src/`:

- [`ChatView.vue`](src/views/ChatView.vue) — AI chat page with streaming and tool-call display
- [`Dashboard.vue`](src/views/Dashboard.vue) — System monitor dashboard
- [`KnowledgeBase.vue`](src/views/KnowledgeBase.vue) — Knowledge base management
- [`Settings.vue`](src/views/Settings.vue) — LLM / persona / RAG / proxy settings
- [`useAgentSocket.js`](src/composables/useAgentSocket.js) — WebSocket client wrapper

Frontend changes are hot-reloaded automatically.

### Pet Window

The pet uses a separate Vite multi-page entry under `pet/`:

- [`PetApp.vue`](pet/components/PetApp.vue) — Sprite animation + bubble + interaction logic
- [`pet-preload.js`](electron/pet-preload.js) — Dedicated preload script

### Python Backend

The backend lives in `python/` and is built on FastAPI + asyncio:

- [`main.py`](python/main.py) — Service entry
- [`server/ws_agent.py`](python/server/ws_agent.py) — WebSocket chat endpoint
- [`agent/engine.py`](python/agent/engine.py) — Agent builder engine
- [`monitor/service.py`](python/monitor/service.py) — System monitoring collection

Add Python dependencies to `requirements.txt`; they are installed automatically at startup.

### Communication Architecture

| Data Type | Channel | Description |
|---|---|---|
| AI chat / streaming tokens / proactive reminders | WebSocket | Renderer connects directly to Python for low latency |
| Config persistence (LLM / persona / pet preferences) | IPC | Main process reads/writes `config.user.json` |
| System monitoring data | stdio protocol lines + IPC | Compatible with existing parsing logic |
| Window control (drag / always-on-top / click-through) | IPC | Managed by the main process |

## ⚙️ Configuration

### App Config (`config.json`)

Base project info is maintained in the root [`config.json`](config.json):

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

### User Config (`config.user.json`)

Runtime user settings (LLM connections, persona prompts, pet preferences, etc.) are stored in `userData/config.user.json` and edited via the visual settings page. It uses a dual-layer design (template + user override) so settings survive upgrades.

### Custom Python Version

Change `pythonVersion` in `config.json` and restart. If an embedded Python was already downloaded, delete the `python_env` directory before restarting.

## 📦 Packaging

Place app icons in `assets/`:

- `icon.ico` — Windows icon
- `icon.icns` — macOS icon
- `icon.png` — Linux icon

`extraResources` auto-bundles `requirements.txt`, `python/`, `config.json`, and `assets/` into the app.

## 📝 License

[Apache License 2.0](LICENSE)

## 🤝 Contributing

Issues and pull requests are welcome!

## 📮 Feedback

Report issues on the [project homepage](https://gitee.com/zjwan461/sassy-cat).
