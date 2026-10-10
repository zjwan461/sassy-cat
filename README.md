<p align="center">
  <img src="assets/icon.png" alt="Sassy Cat" width="120" />
</p>

<h1 align="center">🐱 优墨 · Sassy Cat</h1>

<p align="center">
  <strong>An AI desktop pet assistant</strong> — Electron + Vue 3 + Python
</p>

<p align="center">
  <a href="#-features">Features</a> ·
  <a href="#-screens">Screens</a> ·
  <a href="#-tech-stack">Tech Stack</a> ·
  <a href="#-architecture">Architecture</a> ·
  <a href="#-project-structure">Structure</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-user-guide">User Guide</a> ·
  <a href="#-development-guide">Dev Guide</a> ·
  <a href="#-configuration">Configuration</a> ·
  <a href="#-faq">FAQ</a>
</p>

<p align="center">
  <strong>English</strong> | <a href="README.zh-CN.md">简体中文</a>
</p>

---

A slightly sassy but dependable desktop cat companion. Built with **Electron + Vue 3 + Python**, it combines an **AI Agent** (LangChain / LangGraph / DeepAgents) with a transparent, always-on-top **desktop pet** that chats with you, watches your system, reminds you to take a break, parses documents, answers questions from your own knowledge base, and even gets its paws dirty doing real work.

## ✨ Features

### 🤖 AI Conversational Agent
- Powered by LangChain / LangGraph / DeepAgents: **streaming replies**, **tool calling**, **multi-turn memory** (configurable memory window)
- **Customizable system persona (人设)** — tune your cat's personality anytime
- Multiple LLM provider profiles (OpenAI-compatible, DeepSeek, etc.), switchable from the visual settings page
- **MCP adapter** support to plug in external MCP tool servers
- Built-in toolkits: web search (Tavily), reminders, date/time, and more

### 🐾 Desktop Pet
- Transparent, frameless, always-on-top window with sprite frame animations (idle / walk / talk / think / sleep / react and more)
- Drag to move, click to interact, optional click-through mode
- Bubble messages: agent replies and reminders pop up above the cat
- Quick ask: global shortcut `Alt+Shift+Q` for instant questions right at the pet, with real-time session sync to the main window

### 🧠 Knowledge Base (RAG)
- Build a private local knowledge base: automatic document chunking and vector indexing (ChromaDB)
- Local embedding model `BAAI/bge-small-zh-v1.5` (auto-downloaded if missing); remote embedding APIs also supported
- Management UI: multiple knowledge bases, document upload, detail view, deletion
- The agent retrieves from your knowledge base to answer questions (via RAG tools)

### 📄 Document Parsing & OCR
- PDF / Word / Excel / PPT / images / text supported
- Multi-engine parsing: MarkItDown, Docling, RapidOCR, Unstructured (engine switchable in config)
- Parsed content can be fed directly into the chat or indexed into the knowledge base

### ⏰ Proactive Interaction
- Idle detection + greeting scheduling: ignore the cat too long and it bubbles up ("Why aren't you talking to me? 😾")
- Scheduled reminder tools: ask the cat to remind you to drink water or take a break
- **TTS voice read-aloud**: replies can be spoken (Web Speech API, configurable voice / rate / pitch)

### 🪄 Agent Actions
- The agent can run shell commands, execute Python, and read/write/edit files; dangerous actions (`execute` / `write_file` / `edit_file` / `delete`) **require user confirmation** by default (human-in-the-loop interrupts)
- **DSH hands-on subagent** (DeepSeek Harness): multi-step "chores" are delegated to an isolated worker process that auto-creates a todo list, executes step by step, and reports back — the main cat is never blocked by long tasks
- Skill plugin system: drop a conforming skill directory (with `SKILL.md`) into `runtime/skills/` and it works — e.g. the bundled `html-ppt` slide-deck skill

### 📊 System Monitoring
- Real-time CPU, GPU (NVIDIA), memory, disk, and process metrics on an ECharts dashboard (psutil + pynvml)

### 💬 Rich Chat Rendering
- Markdown + code highlighting (highlight.js) + LaTeX (KaTeX) + Mermaid diagrams
- Streaming-optimized incremental chunk rendering — long replies stay smooth
- Persistent chat history (SQLite): multiple conversations, pinning, deletion

### 🛠️ Engineering
- Visual settings page: LLM profiles, persona, RAG, proxy (HTTP/HTTPS), pet preferences, voice
- **Dual-layer config**: template defaults (`config.json`) + user overrides (`config.user.json`); personal settings survive app upgrades
- Database migrations managed by Alembic, auto-upgraded at startup (see [MIGRATION.md](MIGRATION.md))
- Logs page: backend logs streamed to the frontend in real time
- Python environment auto-detection: embedded Python downloaded automatically if missing; dependencies installed at startup
- One-click packaging: electron-builder for Windows (NSIS) / macOS (DMG) / Linux (AppImage)

## 🖼️ Screens

| Page | Route | Description |
|---|---|---|
| Dashboard | `#/` | System monitor charts (CPU / GPU / memory / disk) |
| Chat | `#/chat` | Streaming chat, tool-call states, session history, file attachments |
| Knowledge Base | `#/kb` | Multi-KB management, document upload, retrieval config |
| MCP Servers | `#/mcp` | MCP server configuration and management |
| Skills | `#/skills` | Skill plugin browsing, details, creation |
| Settings | `#/settings` | LLM / persona / RAG / voice / proxy / pet |
| Logs | `#/logs` | Live backend logs |
| About | `#/about` | Version and project links |

The pet window is a separate page (`pet/pet.html`) — transparent and always-on-top, synced with the main window via IPC/WebSocket.

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Desktop Framework | Electron 28 |
| Frontend | Vue 3 (Composition API) + Vue Router + Vite 5 + ECharts |
| Chat Rendering | markdown-it + highlight.js + KaTeX + Mermaid |
| Backend | Python 3.11 + FastAPI + uvicorn + asyncio (single-process model) |
| AI Agent | LangChain + LangGraph + DeepAgents (+ langchain-mcp-adapters) |
| Hands-on Subagent | deepseek-harness-sdk (DSH worker process) |
| Knowledge Base | ChromaDB + sentence-transformers + langchain-huggingface |
| Document Parsing | MarkItDown + Docling + RapidOCR + Unstructured |
| Persistence | SQLAlchemy (asyncio) + SQLite (aiosqlite) + Alembic migrations |
| Monitoring | psutil + pynvml + wmi/pywin32 |
| Communication | WebSocket (chat/events) + IPC (window/config) + stdio protocol lines (monitor/logs/ready) |
| Packaging | electron-builder (NSIS / DMG / AppImage) |

## 🏗️ Architecture

```
┌──────────────────────── Electron main process (electron/main.js) ────────────────────────┐
│  Main window (src/index.html)          Pet window (transparent, pet/pet.html)   Tray      │
│      │ IPC (preload.js)                    │ IPC (pet-preload.js)                          │
│  config-store.js dual-layer config ──► config.user.json                                    │
│  python-env-checker.js ──► spawn & supervise python/main.py (stdio [READY]/protocol)      │
└──────────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │
                 ┌─────────────────────────┴─────────────────────────┐
                 │       Python backend (FastAPI, single-process     │
                 │                    asyncio)                       │
                 │  /ws/agent  WebSocket: streaming chat / tool      │
                 │             events / proactive reminders          │
                 │  REST: /api/kb /api/conversations /api/stats      │
                 │      /api/skills /api/mcp                         │
                 │  ┌───────────┐ ┌─────────┐ ┌────────┐ ┌────────┐  │
                 │  │   Agent   │ │  RAG    │ │ Monitor│ │Proactive│  │
                 │  │ LangGraph │ │ ChromaDB│ │ psutil │ │ idle &  │  │
                 │  │ + tools   │ │ + OCR   │ │ pynvml │ │ greeting│  │
                 │  │ + DSH sub.│ └─────────┘ └────────┘ └────────┘  │
                 │  └────┬──────┘                                     │
                 │       │ SQLite (messages.sqlite) + Alembic         │
                 └───────┴──── WebSocket ◄── renderer direct ─────────┘
```

Key design points:

- **Renderer connects directly to the Python WebSocket**: chat tokens, tool-call states, and proactive events bypass the main process for low latency; window control and config persistence still go through IPC.
- **Single-process asyncio backend**: FastAPI server, monitoring (blocking calls wrapped with `to_thread`), proactive scheduling, and the agent engine all live in one Python process, supervised by the Electron main process.
- **stdio protocol lines**: the Python process emits `__PROTOCOL__` lines and a `[READY] {"port":...}` signal on stdout — logs are forwarded to the frontend Logs page.
- **Port fallback**: if the preferred port is occupied, the backend automatically falls back to a free port; the main process broadcasts `agent-ready` based on `[READY]`.
- **Dual-layer config**: `config.json` (template, updated with the app) deep-merged with `userData/config.user.json` (user overrides) — upgrades never lose settings.
- **Subagent isolation**: the DSH hands-on subagent runs in an independent worker process that only receives the delegated task; multi-step work must start with a todo list.

## 📁 Project Structure

```
sassy-cat/
├── electron/                      # Electron main process
│   ├── main.js                    # Entry (main + pet window + tray + Python lifecycle)
│   ├── preload.js                 # Main-window preload script
│   ├── pet-preload.js             # Pet-window preload script
│   ├── config-store.js            # Dual-layer config (deep merge + atomic write)
│   └── python-env-checker.js      # Python env check / embedded Python download
├── src/                           # Main-window Vue 3 frontend
│   ├── views/
│   │   ├── Dashboard.vue          # System monitor dashboard
│   │   ├── ChatView.vue           # AI chat (streaming + tools + history)
│   │   ├── KnowledgeBase.vue / KnowledgeBaseDetail.vue  # RAG management
│   │   ├── SkillManager.vue / SkillDetail.vue           # Skill plugins
│   │   ├── McpManager.vue         # MCP server management
│   │   ├── Settings.vue           # LLM + persona + RAG + voice + proxy
│   │   └── Logs.vue / About.vue / Setup.vue
│   ├── composables/
│   │   ├── useAgentSocket.js      # WebSocket client (singleton + auto-reconnect)
│   │   ├── useChatStore.js        # Chat state store
│   │   ├── useFileUpload.js       # File upload (OCR / RAG)
│   │   ├── useTTS.js              # Voice read-aloud (Web Speech)
│   │   └── useKbUploadState.js / useModelDownloadState.js / useRestartState.js
│   ├── components/
│   │   ├── MarkdownRenderer.vue   # Markdown/LaTeX/Mermaid (incremental chunks)
│   │   ├── ConversationItem.vue / DocumentAttachment.vue / FilePreview.vue
│   ├── utils/streamSplitter.js    # Streaming text chunking
│   └── api/                       # REST clients (kb / messages / stats / skills / mcp)
├── pet/                           # Pet window (Vite multi-page entry)
│   ├── pet.html / pet-main.js
│   ├── assets/sprites/cat/        # Sprite frames + config.json (actions/FPS)
│   └── components/
│       ├── PetApp.vue             # Bubbles + interaction + state orchestration
│       └── sprite/                # Sprite system (PetSprite / Svg & Spritesheet renderers / preload)
├── python/                        # Python backend (single-process asyncio)
│   ├── main.py                    # Entry ([READY] signal + port fallback)
│   ├── config_loader.py / paths.py / utils.py
│   ├── server/
│   │   ├── app.py                 # FastAPI app + routes + lifespan
│   │   ├── ws_agent.py            # /ws/agent endpoint + session management
│   │   ├── bus.py                 # In-process event bus
│   │   ├── conversations.py / kb_api.py / stats_api.py / skills_api.py / mcp_api.py
│   │   └── db/                    # SQLAlchemy models + repositories + Alembic + seed
│   ├── agent/
│   │   ├── engine.py              # Agent builder (config injection)
│   │   ├── runner.py / main_agent.py  # Streaming bridge
│   │   ├── llms.py                # LLM factory
│   │   ├── prompts.py             # Persona templates + runtime prompt assembly
│   │   ├── middlewares.py         # Agent middlewares
│   │   ├── reminders.py           # Reminder context injection
│   │   ├── virtual_shell.py       # Sandboxed shell execution
│   │   ├── tools/                 # builtin / rag / reminder / mcp / subagent(dsh)
│   │   └── rag/                   # rag_service / document_retriever / model_download
│   ├── monitor/                   # System metrics (cpu / gpu / memory / disks / protocol)
│   ├── ocr/                       # Document parsing (markitdown / docling / rapidocr / xls …)
│   └── proactive/                 # Idle detection + greetings + reminder scheduling
├── runtime/
│   └── skills/                    # Skill plugin directory (e.g. bundled html-ppt skill)
├── tests/                         # Ad-hoc verification / probe scripts
├── plans/                         # Design & migration docs
├── assets/                        # App icons
├── config.json                    # App config template
├── requirements.txt               # Python dependencies
├── vite.config.js                 # Vite multi-page config (index / setup / pet)
├── start.bat                      # Windows one-click dev launcher
├── MIGRATION.md                   # Database migration guide
└── package.json                   # Node dependencies + electron-builder config
```

## 🚀 Quick Start

### Requirements

- **Node.js**: 18+
- **npm**: 9+
- **Python**: 3.10+ (auto-detected; an embedded Python is downloaded to `python_env/` if none is available)

### Install Dependencies

```bash
npm install
```

### Development Mode

**Windows (recommended, one-click):**
```bash
start.bat
```
The script checks Node/npm, runs `npm install` on first launch, then starts the dev environment.

**macOS / Linux:**
```bash
npm run electron:dev
```

Dev mode uses `concurrently` to start the Vite dev server (`http://localhost:5173`) and Electron together, with hot reload. The Python backend is spawned by the Electron main process, and `requirements.txt` dependencies are installed automatically at startup.

### Production Build

```bash
# Build for the current platform
npm run electron:build

# Build for a specific platform
npm run electron:build:win     # Windows NSIS installer
npm run electron:build:mac     # macOS DMG
npm run electron:build:linux   # Linux AppImage

# Build frontend assets and preview Electron locally
npm run electron:preview
```

Build artifacts are output to the `dist_electron/` directory.

## 📖 User Guide

### First Launch

1. On startup the app runs an environment check (Python / dependency installation); the `Setup` page shows progress.
2. Go to **Settings** and configure at least one LLM: Base URL, API Key, and model name (OpenAI-compatible endpoints and DeepSeek are supported), then save and activate it.
3. Open the chat page or poke the pet to start talking; press `Alt+Shift+Q` for a quick ask right next to the pet.

### Knowledge Base

1. **Knowledge Base page** → create a new KB.
2. Upload PDF / Word / Excel / images and more — documents are parsed (OCR/doc engines), chunked, and vectorized automatically.
3. During chat, the agent retrieves from the KB to answer (via RAG tools; you can also explicitly ask "answer based on my knowledge base").
4. The default embedding model is local `BAAI/bge-small-zh-v1.5`, downloaded on first use if missing; a remote embedding API can be configured instead.

### Skills & MCP

- **Skills**: place a conforming skill directory (with `SKILL.md`) under `runtime/skills/`; browse, create, and use them from the Skills page.
- **MCP**: add server configs (command / args / env) on the MCP page, and the agent can call the tools they expose.

### Dangerous Action Confirmation

By default the agent **interrupts and waits for confirmation** before executing shell commands, writing, editing, or deleting files (tune via `agent.interruptOn` in `config.json`).

### Proactive Reminders

The pet greets you based on idle detection; you can also just say "remind me to drink water in 10 minutes" and it will bubble up on schedule.

## 🔧 Development Guide

### Frontend (Main Window)

The frontend uses Vue 3 + Vite under `src/` (alias `@` → `src/`):

- [`ChatView.vue`](src/views/ChatView.vue) — AI chat page (streaming + tool-call display + history)
- [`Dashboard.vue`](src/views/Dashboard.vue) — System monitor dashboard (ECharts)
- [`KnowledgeBase.vue`](src/views/KnowledgeBase.vue) / [`KnowledgeBaseDetail.vue`](src/views/KnowledgeBaseDetail.vue) — KB management
- [`SkillManager.vue`](src/views/SkillManager.vue) / [`McpManager.vue`](src/views/McpManager.vue) — extension management
- [`Settings.vue`](src/views/Settings.vue) — LLM / persona / RAG / voice / proxy settings
- [`useAgentSocket.js`](src/composables/useAgentSocket.js) — WebSocket client wrapper (singleton + auto-reconnect)
- [`MarkdownRenderer.vue`](src/components/MarkdownRenderer.vue) — rich rendering (with [`streamSplitter.js`](src/utils/streamSplitter.js) for incremental chunks)

Vite is configured with multiple page entries: `index.html` (main window), `setup.html` (bootstrap), [`pet/pet.html`](pet/pet.html) (pet) — see [`vite.config.js`](vite.config.js). Frontend changes hot-reload automatically.

### Pet Window

The pet lives under `pet/` with its own Vite entry:

- [`PetApp.vue`](pet/components/PetApp.vue) — bubbles, dragging, click interaction, state orchestration
- [`pet/components/sprite/`](pet/components/sprite/) — sprite rendering system: [`PetSprite.vue`](pet/components/sprite/PetSprite.vue) as the entry, [`SpritesheetRenderer.vue`](pet/components/sprite/SpritesheetRenderer.vue) / [`SvgSpriteRenderer.vue`](pet/components/sprite/SvgSpriteRenderer.vue) as two render backends, [`useSpritePreload.js`](pet/components/sprite/useSpritePreload.js) for frame preloading
- [`pet/assets/sprites/cat/config.json`](pet/assets/sprites/cat/config.json) — action/frame animation config (idle, walk, talk, think, sleep, react, remind, …)
- [`pet-preload.js`](electron/pet-preload.js) — dedicated preload script (click-through, dragging, etc.)

### Python Backend

The backend lives under `python/` (FastAPI + single-process asyncio):

- [`main.py`](python/main.py) — service entry (port fallback + `[READY]` signal)
- [`server/ws_agent.py`](python/server/ws_agent.py) — WebSocket chat endpoint and session management
- [`agent/engine.py`](python/agent/engine.py) / [`agent/runner.py`](python/agent/runner.py) — agent builder and streaming bridge
- [`agent/prompts.py`](python/agent/prompts.py) — persona templates and runtime prompt assembly
- [`agent/tools/`](python/agent/tools/) — toolkits: builtin shell/file tools, RAG retrieval, reminders, MCP, DSH subagent
- [`monitor/service.py`](python/monitor/service.py) — periodic system metrics collection
- [`proactive/scheduler.py`](python/proactive/scheduler.py) — idle detection / greeting / reminder scheduling

Add Python dependencies to [`requirements.txt`](requirements.txt); they are installed automatically at startup.

### Database Migrations

Schema is managed by Alembic (`python/server/db/migrations/`) and auto-upgrades at startup — users never notice. When adding or changing tables during development, follow [MIGRATION.md](MIGRATION.md) (autogenerate → manual review → verification script).

### Testing

The `tests/` directory contains ad-hoc verification/probe scripts (e.g. [`tmp_test_migration.py`](tests/tmp_test_migration.py), [`stream_splitter.test.mjs`](tests/stream_splitter.test.mjs), [`incremental_render_equivalence.test.mjs`](tests/incremental_render_equivalence.test.mjs)) that can be run to validate the corresponding subsystems.

### Communication Architecture

| Data Type | Channel | Description |
|---|---|---|
| AI chat / streaming tokens / tool events / proactive reminders | WebSocket | Renderer connects directly to Python for low latency |
| Config persistence (LLM / persona / pet preferences) | IPC | Main process reads/writes `config.user.json` |
| System metrics / backend logs / ready signal | stdio protocol lines + IPC | `__PROTOCOL__` lines + `[READY] {"port":...}` |
| Window control (drag / always-on-top / click-through) | IPC | Managed by the main process |

## ⚙️ Configuration

### App Config Template (`config.json`)

Base project configuration lives in the root [`config.json`](config.json) (template layer, updated with the app):

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

Sections at a glance:

| Section | Description |
|---|---|
| `agent` | Memory window, recursion limit, OCR toggle/engine, dangerous-action confirmation (`interruptOn`) |
| `dsh` | Hands-on subagent: LLM source (defaults to the main model), maxTokens, reasoning effort |
| `rag` | Embedding model (local/remote), auto-embedding, KB document parse engine |
| `pet` | Pet toggle, quick-ask shortcut, reminder polling and bubble duration |
| `voice` | Read-aloud toggle, engine, auto-read, voice name / rate / pitch |
| `network` | HTTP/HTTPS proxy |

### User Config (`config.user.json`)

Runtime user settings (LLM connections, persona prompts, pet preferences, etc.) are stored in `userData/config.user.json` and edited via the visual settings page. The dual-layer design (template + user override, deep-merged) ensures settings survive upgrades.

### Custom Python Version

Change `pythonVersion` in `config.json` and restart. If an embedded Python was already downloaded, delete the `python_env` directory before restarting.

## 📦 Packaging

Place app icons in `assets/`:

- `icon.ico` — Windows icon
- `icon.icns` — macOS icon
- `icon.png` — Linux icon

`extraResources` auto-bundles `requirements.txt`, `python/`, `config.json`, `assets/`, and `runtime/skills/` into the app. The Windows installer is NSIS-based with a customizable install directory and desktop/Start-Menu shortcuts (see the `build` section in [`package.json`](package.json)).

## ❓ FAQ

<details>
<summary><b>Python service didn't start / chat is unresponsive?</b></summary>

- Open the **Logs page** to inspect backend output. On first launch, embedded Python is downloaded and `requirements.txt` is installed — this takes a while and is normal.
- If the port is occupied, the backend automatically falls back to a random free port; usually nothing to do.
- Dependency install failures are often network issues; configure a proxy in Settings and restart.

</details>

<details>
<summary><b>Embedding model download failed?</b></summary>

The default downloads `BAAI/bge-small-zh-v1.5` from HuggingFace. If your network is restricted, configure a proxy in Settings, or switch to a remote embedding API.

</details>

<details>
<summary><b>Pet window not visible / wrong position?</b></summary>

The pet toggle lives in Settings and `pet.enabled` in `config.json`. The pet window is transparent and always-on-top; if you can't find it, switch its visibility from the tray menu.

</details>

<details>
<summary><b>The agent asks for confirmation on every command — too tedious?</b></summary>

Confirmation is controlled by `agent.interruptOn` in `config.json`, which can be disabled per tool (turning everything off is not recommended).

</details>

## 🗺️ Roadmap

Ongoing design/migration docs are recorded in [`plans/`](plans/), including:

- ✅ Pet sprite animation migration ([`pet-sprite-migration-plan.md`](plans/pet-sprite-migration-plan.md))
- ✅ TTS voice read-aloud ([`tts-voice-read-aloud-plan.md`](plans/tts-voice-read-aloud-plan.md))
- ✅ Streaming Markdown render performance ([`streaming-markdown-render-perf-plan.md`](plans/streaming-markdown-render-perf-plan.md))
- ✅ DSH subagent settings ([`dsh-settings-plan.md`](plans/dsh-settings-plan.md))
- 🚧 Agent error retry ([`agent-error-retry-plan.md`](plans/agent-error-retry-plan.md))
- 🚧 Context window compression ([`context-window-compression-plan.md`](plans/context-window-compression-plan.md))

## 📝 License

[Apache License 2.0](LICENSE)

## 🤝 Contributing

Issues and pull requests are welcome! Please read the relevant docs under [`plans/`](plans/) before making changes, to keep the architecture consistent.

## 📮 Feedback

Report issues on the [project homepage](https://github.com/zjwan461/sassy-cat), or check the [release notes](https://github.com/zjwan461/sassy-cat/releases).
