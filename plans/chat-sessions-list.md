# 聊天多会话列表（Conversations）方案

## 需求
当前聊天永远只有一个 sessionId（localStorage 持久化），所有消息续写到同一 thread。
目标：
1. 会话列表：展示所有历史对话（标题 + 时间），可点击切换回任一对话继续聊
2. 「新建对话」按钮：开一个全新 thread
3. 元数据用 JSON 文件持久化，只存关键信息（标题、thread_id 等）

## 现状关键事实
- LangGraph checkpointer 已按 `thread_id` 完整持久化每个会话（`runtime/checkpoints.sqlite`，见 `agent/constant.py`），
  切回旧 thread 即可续聊，**消息本体无需新存储**
- 滑动窗口（`agent.middlewares.trim_messages`，memoryWindow=50）截断 `state.values`，
  单会话消息上限 ~50 条——本方案不解决翻页，只解决多会话管理
- 前端 sessionId 在 `useAgentSocket.js:13` 生成并 localStorage 持久化 → 迁移为服务端下发
- 桌宠 `PetApp.vue:206` 用 `sock.sessionId` 发消息 → 需跟随"当前激活会话"
- `hub.publish(session_id, ...)` 按 sessionId 房间 fan-out → 多窗口天然按会话隔离同步

## 存储位置（安全约束）
`runtime/` 是 agent 的 sandbox 工作目录（skills 加载、脚本执行），会话元数据放那里会被模型篡改，**禁止**。

元数据文件放 **Electron userData 目录**：
- Windows：`C:\Users\<user>\AppData\Roaming\sassy-cat\conversations.json`
- macOS：`~/Library/Application Support/sassy-cat/`
- Linux：`~/.local/share/sassy-cat/`

传递方式（与现有 `config.user.json` 同套路）：
- Electron `main.js` 启动 Python 时追加参数 `--data-dir <app.getPath('userData')>`
- Python `main.py` argparse 接收，`config_loader`（或新建 `paths.py`）暴露 `DATA_DIR`
- 兜底：Python 独立运行（CLI 调试、无 Electron）时，`--data-dir` 缺省则按平台自算
  （`%APPDATA%/sassy-cat` / `~/Library/Application Support/sassy-cat` / `~/.local/share/sassy-cat`），
  不依赖 hardcode 用户名
- **已确认**：`checkpoints.sqlite` 一并迁移到 userData（同属用户数据，现位于 runtime 有被篡改风险）。
  Python 启动时检测 `runtime/checkpoints.sqlite` 旧文件，存在且 userData 下无新文件则搬迁一次
  （sqlite 需连同 `-wal`/`-shm` 伴生文件一起 move；WAL 模式下先 checkpoint 再搬）
- 实现方式：`agent/constant.py` 的 `DB_URL` 改为从 `paths.DATA_DIR` 派生

## 会话元数据文件 `conversations.json`
```json
{
  "version": 1,
  "activeId": "conv-xxxxxxxx",
  "conversations": [
    {
      "id": "conv-xxxxxxxx",          // 会话唯一 id，同时作为 LangGraph thread_id
      "title": "现在几点了？",          // 首条用户消息前 24 字符；可手动重命名
      "createdAt": 1730000000000,
      "updatedAt": 1730000123000
    }
  ]
}
```
- 列表按 `updatedAt` 倒序展示
- 写入策略：进程内 `threading.Lock` + 先写临时文件再 `os.replace` 原子替换

## 后端：新模块 `python/server/conversations.py`
- `list()` / `get(id)` / `touch(id)`（更新 updatedAt 并置顶）
- `create() -> conv`：生成 `conv-` + uuid hex；**若无 activeId 则自动激活**（桌宠发消息等场景）
- `set_active(id)` / `rename(id, title)` / `delete(id)`
- `active_id()`：读取 activeId；**文件不存在或 activeId 为空时自动创建一个默认会话**
  （兼容升级：老用户旧 localStorage sessionId 的历史不迁移，接受为新起点）
- `first_user_message(agent, thread_id)`：从 checkpoint 读首条 human 消息（自动标题用，可选）

## WS 协议扩展（`ws_agent.py`）
| 方向 | type | payload | 说明 |
|---|---|---|---|
| 请求 | `conv.list` | `{}` | 响应 `conv.list.result {items}` |
| 请求 | `conv.create` | `{}` | 服务端创建+激活，响应 `conv.activated {id, title}` |
| 请求 | `conv.activate` | `{id}` | 切换激活会话，响应 `conv.activated {id, title}` |
| 请求 | `conv.rename` | `{id, title}` | 重命名，响应 `conv.list.result {items}`（全量刷新） |
| 请求 | `conv.delete` | `{id}` | 删除元数据（checkpoint 数据保留），响应 `conv.list.result {items}` |
| 广播 | `conv.activated` | `{id, title}` | 全局广播（publish_all）→ 桌宠/多窗口跟随切换 |

`connected` 帧（`ws_agent.py:381`）扩展携带 `sessionId: active_id()`，作为前端会话对齐的锚点。

`chat.send` 改造：
- 服务端以 payload.sessionId 定位房间，但**会话记录以服务端为准**：
  收到消息时若无对应会话记录则自动 `create()`
- 新会话首条消息到达时：`title = content[:24]`，rename 后广播 `conv.list.result`
- 每轮消息（send / completed）`touch(id)` 更新 updatedAt

## 前端改造

### `useAgentSocket.js`
- 收到服务端 `connected` 帧后，把 payload 中的 `sessionId`（= 激活会话 id）同步进 `state.sessionId`
  （当前 connected 帧在 `ws_agent.py:381`，扩展携带 activeId）
- `state.sessionId` 初始值改为占位（如 `'pending'`），不再从 localStorage 读取
- 重连场景：每次 `connected` 帧都重新对齐 sessionId；若与当前激活会话不同则触发历史重载

### `useChatStore.js`
- 新增 `conv = reactive({ list: [], activeId: null })`
- 订阅 `conv.list.result` / `conv.activated`
- `chat.history.result` 守卫改造：切换会话时 `switchConversation(id)` **清空 `chat.messages`**
  再请求历史，避免旧会话消息被误判为"已有本地数据"而跳过回填
- 导出 `loadConversations() / newConversation() / switchConversation(id) / renameConversation(id, title) / deleteConversation(id)`
- 流式进行中切换会话：允许切换查看，切换时复位 `chat.generating`；
  旧轮次事件按 msgId 在清空后的 messages 中找不到，自然丢弃（现有 find 守卫已覆盖）

### `ChatView.vue`
- 左侧新增会话侧栏（chat-page 内部 flex 布局，不改全局 App.vue）：
  - 顶部「＋ 新建对话」按钮
  - 会话条目：标题（ellipsis）+ 相对时间；hover 显示 ✎ 重命名 / 🗑 删除
  - 当前激活条目高亮
  - 窄屏（<900px）侧栏折叠为顶部下拉
- 进入页面：`loadConversations()` + `useChatStore()` 拉当前会话历史
- 切换/新建：清空消息区 → 拉新会话历史 → 滚到底部

### `PetApp.vue`
- 订阅 `conv.activated` 更新本地 sessionId 引用（跟随主窗口切换）

## Electron 改造（`main.js`）
- 启动 Python 子进程时追加 `--data-dir` 参数（`app.getPath('userData')`）
- 若决定迁移 checkpoints：Python 侧启动时检测 runtime 下旧 sqlite 并搬迁一次

## 实施顺序
1. 路径基建：Electron 传 `--data-dir` + Python 解析与平台兜底（`paths.py`）
2. 后端 `conversations.py` 模块 + 原子读写 + 默认会话自动创建
3. `ws_agent.py` 接入：connected 帧带 activeId、conv.* 消息路由、chat.send 标题/touch
4. 前端 `useAgentSocket.js` sessionId 服务端下发
5. 前端 `useChatStore.js` 会话状态 + 切换清空逻辑
6. 前端 `ChatView.vue` 会话侧栏 UI（列表/新建/重命名/删除）
7. `PetApp.vue` 跟随激活会话
8. 验证：重启恢复、多窗口同步、升级兼容、删除当前会话后自动切到下一个

## 边界与决策点
## 边界与决策点（已全部确认）
- **删除会话**：仅删元数据，checkpoint 数据留在 sqlite（可接受，避免误删 LangGraph 内部数据的风险）
- **升级兼容**：旧 localStorage 会话不迁移，首次启动生成全新默认会话
- **标题生成**：首条用户消息前 24 字符截断 + 手动重命名；不做 LLM 自动摘要
- **并发**：Electron 单 Python 进程，文件锁足够；无需考虑多进程
- **桌宠独立会话**：不做，桌宠始终跟随主窗口激活会话
- **checkpoints.sqlite**：一并迁移到 userData，启动时自动搬迁旧文件
