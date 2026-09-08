# 聊天历史查询功能重构设计方案

## 1. 需求概述

将聊天历史查询从 LangGraph agent state 的 message 存储改为独立数据库表存储，解决 50 条上下文窗口限制问题。

### 核心需求
1. 新增 `messages` 表存储聊天消息（区分 user/ai/tool message）
2. 新增 `attachments` 表存储附件信息（图片存 base64，文档存 OCR 后的 markdown）
3. 新增 HTTP GET 接口查询历史消息，支持分页
4. 前端展示：图片用 base64 显示，文档显示 icon（区分格式），点击可打开查看 markdown 内容
5. 使用 SQLAlchemy 作为 ORM 框架

---

## 2. 数据库设计

### 2.1 技术栈

- **ORM**: SQLAlchemy 2.0+
- **数据库**: SQLite
- **数据库文件**: `{data_dir}/messages.sqlite`（与现有 `checkpoints.sqlite` 分离）

### 2.2 表结构

#### messages 表
```python
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True)              # 消息唯一 ID
    session_id = Column(String, nullable=False, index=True)  # 会话 ID，对应 LangChain 的 thread_id
    role = Column(String, nullable=False)              # 'user' | 'assistant' | 'tool'
    content = Column(Text)                             # 消息文本内容
    reasoning = Column(Text)                           # AI 思考内容 (仅 assistant)
    tool_calls = Column(Text)                          # 工具调用名称列表 JSON，如 ["search", "run_cmd"] (仅 assistant)
    tool_call_args = Column(Text)                      # 工具调用参数 JSON，如 {"search": {"q": "..."}} (仅 assistant)
    tool_call_id = Column(String)                      # 工具结果关联 ID (仅 tool)
    tool_name = Column(String)                         # 工具名称 (仅 tool)
    tool_status = Column(String)                       # 工具执行状态 (仅 tool)
    created_at = Column(BigInteger, nullable=False, index=True)  # 创建时间戳 (毫秒)
    
    # 关系
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
```

> **关于 session_id**：messages 表中的 `session_id` 直接对应 LangGraph checkpointer 的 `thread_id`，即 conversations.json 中的会话 `id`。所有消息通过此字段归属到具体对话。
#### attachments 表
```python
class Attachment(Base):
    __tablename__ = "attachments"
    
    id = Column(String, primary_key=True)              # 附件唯一 ID
    message_id = Column(String, ForeignKey("messages.id"), nullable=False, index=True)
    type = Column(String, nullable=False)              # 'image' | 'document'
    file_name = Column(String, nullable=False)         # 文件名
    file_ext = Column(String)                          # 文件后缀 (如 .pdf, .png)
    file_size = Column(Integer)                        # 文件大小 (字节)
    mime_type = Column(String)                         # MIME 类型
    base64_data = Column(Text)                         # 图片的 base64 数据 (仅 image)
    markdown_content = Column(Text)                    # 文档 OCR 后的 markdown (仅 document)
    created_at = Column(BigInteger, nullable=False)    # 创建时间戳 (毫秒)
    
    # 关系
    message = relationship("Message", back_populates="attachments")
```

### 2.3 索引优化

```sql
-- 查询历史消息（按会话和时间倒序）
CREATE INDEX idx_messages_session_time ON messages(session_id, created_at DESC);

-- 查询消息的附件
CREATE INDEX idx_attachments_message ON attachments(message_id);
```

---

## 3. 后端实现

### 3.1 新增模块结构

```
python/server/
├── db/
│   ├── __init__.py
│   ├── database.py          # 数据库连接和会话管理
│   ├── models.py            # SQLAlchemy 模型定义
│   └── message_repository.py # 消息和附件的 CRUD 操作
```

### 3.2 数据库初始化

在 `python/server/app.py` 的 lifespan 中初始化数据库：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化消息数据库
    await asyncio.to_thread(init_message_db)
    # ... 其他初始化
    yield
    # 关闭数据库
    await asyncio.to_thread(close_message_db)
```

### 3.3 消息记录时机

在 `python/server/ws_agent.py` 中：

1. **用户消息**：在 `_handle_chat_send` 中，发送消息前保存到数据库
2. **AI 消息**：在 `_stream_turn` 的 `done` 事件时保存完整内容
3. **Tool 消息**：在工具调用完成时保存（通过 agent 事件流捕获）

### 3.4 新增 HTTP 接口

在 `python/server/app.py` 中新增：

```python
@app.get("/api/messages")
async def get_messages(
    session_id: str = Query(..., description="会话 ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """分页查询历史消息（含附件）"""
    # 返回格式：
    # {
    #   "items": [
    #     {
    #       "id": "msg-xxx",
    #       "sessionId": "conv-xxx",
    #       "role": "user" | "assistant" | "tool",
    #       "content": "消息内容",
    #       "reasoning": "思考内容",          # 仅 assistant
    #       "toolCalls": ["search", "cmd"],   # 仅 assistant，工具名称列表
    #       "toolCallArgs": {                 # 仅 assistant，工具参数映射
    #         "search": {"q": "..."},
    #         "cmd": {"command": "..."}
    #       },
    #       "toolCallId": "tc-xxx",           # 仅 tool，关联的工具调用 ID
    #       "toolName": "search",             # 仅 tool，工具名称
    #       "toolStatus": "success",          # 仅 tool，执行状态
    #       "attachments": [
    #         {
    #           "id": "att-xxx",
    #           "type": "image",
    #           "fileName": "image.png",
    #           "fileExt": ".png",
    #           "fileSize": 12345,
    #           "mimeType": "image/png",
    #           "base64Data": "..."           # 仅图片
    #         },
    #         {
    #           "id": "att-yyy",
    #           "type": "document",
    #           "fileName": "doc.pdf",
    #           "fileExt": ".pdf",
    #           "fileSize": 54321,
    #           "mimeType": "application/pdf",
    #           "markdownContent": "OCR 内容..."  # 仅文档
    #         }
    #       ],
    #       "createdAt": 1234567890
    #     }
    #   ],
    #   "total": 100,
    #   "page": 1,
    #   "pageSize": 20
    # }
```

### 3.5 附件处理流程

#### 图片附件
1. 前端上传时转 base64
2. 后端保存到 attachments 表（base64_data 字段）
3. 查询时直接返回 base64 数据

#### 文档附件
1. 前端调用 `/api/ocr` 获取 markdown
2. 后端保存到 attachments 表（markdown_content 字段）
3. 查询时返回 markdown 内容和文件元信息

---

## 4. 前端实现

### 4.1 新增 API 模块

创建 `src/api/messages.js`：

```javascript
import { useAgentSocket } from '../composables/useAgentSocket'

const { state: socketState } = useAgentSocket()

/**
 * 分页查询历史消息
 * @param {string} sessionId 会话 ID
 * @param {number} page 页码
 * @param {number} pageSize 每页数量
 * @returns {Promise<{items: Array, total: number, page: number, pageSize: number}>}
 */
export async function fetchMessages(sessionId, page = 1, pageSize = 20) {
  const port = socketState.port
  const params = new URLSearchParams({
    session_id: sessionId,
    page: page.toString(),
    page_size: pageSize.toString()
  })
  
  const response = await fetch(
    `http://127.0.0.1:${port}/api/messages?${params}`
  )
  
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  
  return response.json()
}
```

### 4.2 修改 `useChatStore.js`

1. 移除 WebSocket 的 `chat.history` 和 `chat.history.result` 事件处理
2. 新增 `loadMessages()` 方法调用 HTTP 接口
3. 在会话切换时调用 `loadMessages()`
4. 支持分页加载（滚动到底部时加载下一页）

```javascript
// 新增状态
export const chat = reactive({
  messages: [],
  generating: false,
  convId: null,
  convTitle: '',
  // 分页相关
  currentPage: 1,
  pageSize: 20,
  totalMessages: 0,
  loadingMore: false
})

// 加载历史消息
export async function loadMessages(reset = false) {
  if (reset) {
    chat.currentPage = 1
    chat.messages.splice(0, chat.messages.length)
  }
  
  if (chat.loadingMore) return
  
  chat.loadingMore = true
  try {
    const result = await fetchMessages(chat.convId, chat.currentPage, chat.pageSize)
    
    // 转换消息格式并追加到列表
    const messages = result.items.map(transformMessage)
    if (reset) {
      chat.messages.splice(0, chat.messages.length, ...messages)
    } else {
      chat.messages.push(...messages)
    }
    
    chat.totalMessages = result.total
    chat.currentPage++
  } finally {
    chat.loadingMore = false
  }
}

// 转换后端消息格式为前端格式
function transformMessage(item) {
  // 构建工具调用列表（合并 toolCalls 和 toolCallArgs）
  const tools = []
  if (item.toolCalls && Array.isArray(item.toolCalls)) {
    const args = item.toolCallArgs || {}
    for (const name of item.toolCalls) {
      tools.push({
        name,
        done: true,  // 历史消息中的工具调用视为已完成
        args: args[name] ? JSON.stringify(args[name]) : '',
        result: ''   // 工具结果需要从 tool 角色的消息中获取
      })
    }
  }
  
  return {
    id: item.id,
    role: item.role,
    content: item.content,
    reasoning: item.reasoning || '',
    reasoningOpen: false,
    thinking: false,
    tools: tools,
    attachments: (item.attachments || []).map(transformAttachment)
  }
}

// 转换附件格式
function transformAttachment(att) {
  return {
    id: att.id,
    type: att.type,
    fileName: att.fileName,
    fileExt: att.fileExt,
    fileSize: att.fileSize,
    mimeType: att.mimeType,
    base64Data: att.base64Data,
    markdownContent: att.markdownContent
  }
}
```

### 4.3 修改 `ChatView.vue`

1. 图片附件：直接使用 base64 显示（与现有逻辑一致）
2. 文档附件：显示文档 icon + 文件名，点击可展开查看 OCR 内容

```vue
<!-- 用户消息的附件 -->
<div v-if="m.attachments && m.attachments.length" class="msg-attachments">
  <!-- 图片附件 -->
  <div v-for="att in imageAttachments(m)" :key="att.id" class="attachment-image">
    <img :src="`data:${att.mimeType};base64,${att.base64Data}`" 
         class="msg-image" 
         @click="openImagePreview(att)" />
  </div>
  
  <!-- 文档附件 -->
  <div v-for="att in docAttachments(m)" :key="att.id" class="attachment-doc">
    <DocumentAttachment :attachment="att" />
  </div>
</div>
```

### 4.4 新增组件：`DocumentAttachment.vue`

用于显示文档附件的 icon 和内容：

```vue
<template>
  <div class="doc-attachment" @click="toggleExpand">
    <div class="doc-icon">
      <!-- 根据文件后缀显示不同 icon -->
      <svg v-if="isPdf" class="icon-pdf" viewBox="0 0 24 24">...</svg>
      <svg v-else-if="isWord" class="icon-word" viewBox="0 0 24 24">...</svg>
      <svg v-else-if="isExcel" class="icon-excel" viewBox="0 0 24 24">...</svg>
      <svg v-else-if="isText" class="icon-text" viewBox="0 0 24 24">...</svg>
      <svg v-else class="icon-file" viewBox="0 0 24 24">...</svg>
    </div>
    <div class="doc-info">
      <div class="doc-name">{{ attachment.fileName }}</div>
      <div class="doc-size">{{ formatSize(attachment.fileSize) }}</div>
    </div>
    <div class="doc-expand-icon">
      {{ expanded ? '▼' : '▶' }}
    </div>
  </div>
  
  <!-- 展开的 markdown 内容 -->
  <div v-if="expanded" class="doc-content">
    <MarkdownRenderer :content="attachment.markdownContent" :done="true" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  attachment: {
    type: Object,
    required: true
  }
})

const expanded = ref(false)

function toggleExpand() {
  expanded.value = !expanded.value
}

const isPdf = computed(() => props.attachment.fileExt?.toLowerCase() === '.pdf')
const isWord = computed(() => ['.doc', '.docx'].includes(props.attachment.fileExt?.toLowerCase()))
const isExcel = computed(() => ['.xls', '.xlsx'].includes(props.attachment.fileExt?.toLowerCase()))
const isText = computed(() => ['.txt', '.md'].includes(props.attachment.fileExt?.toLowerCase()))

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.doc-attachment {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  min-width: 200px;
  max-width: 300px;
}

.doc-attachment:hover {
  background: #1e293b;
  border-color: #6366f1;
}

.doc-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
}

.doc-icon svg {
  width: 100%;
  height: 100%;
}

.icon-pdf { color: #ef4444; }
.icon-word { color: #3b82f6; }
.icon-excel { color: #10b981; }
.icon-text { color: #64748b; }
.icon-file { color: #94a3b8; }

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 13px;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-size {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.doc-expand-icon {
  flex-shrink: 0;
  color: #64748b;
  font-size: 12px;
}

.doc-content {
  margin-top: 8px;
  padding: 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  max-height: 400px;
  overflow-y: auto;
}
</style>
```

### 4.5 滚动加载更多

在 `ChatView.vue` 中监听滚动事件，当滚动到顶部时加载更多：

```javascript
function onScroll() {
  if (!listRef.value) return
  
  const { scrollTop, scrollHeight, clientHeight } = listRef.value
  
  // 当滚动到顶部附近时加载更多
  if (scrollTop < 50 && !chat.loadingMore && chat.messages.length < chat.totalMessages) {
    loadMoreMessages()
  }
}

async function loadMoreMessages() {
  const oldScrollHeight = listRef.value?.scrollHeight || 0
  
  await loadMessages(false)  // 加载下一页
  
  // 保持滚动位置
  await nextTick()
  if (listRef.value) {
    const newScrollHeight = listRef.value.scrollHeight
    const diff = newScrollHeight - oldScrollHeight
    listRef.value.scrollTop += diff
  }
}

onMounted(() => {
  listRef.value?.addEventListener('scroll', onScroll)
})

onUnmounted(() => {
  listRef.value?.removeEventListener('scroll', onScroll)
})
```

---

## 5. 实现步骤

### 阶段 1：数据库层
- [ ] 创建 `python/server/db/` 目录结构
- [ ] 实现 `database.py`：数据库连接和会话管理
- [ ] 实现 `models.py`：SQLAlchemy 模型定义
- [ ] 实现 `message_repository.py`：消息和附件的 CRUD 操作
- [ ] 在 `app.py` 的 lifespan 中初始化数据库

### 阶段 2：消息记录
- [ ] 修改 `ws_agent.py` 的 `_handle_chat_send`，保存用户消息和附件
- [ ] 修改 `_stream_turn`，在 done 时保存 AI 消息
- [ ] 处理工具消息的保存（通过 agent 事件流捕获）

### 阶段 3：HTTP 接口
- [ ] 在 `app.py` 中新增 `/api/messages` GET 接口
- [ ] 实现分页逻辑和附件关联查询
- [ ] 添加查询参数验证

### 阶段 4：前端改造
- [ ] 创建 `src/api/messages.js` API 模块
- [ ] 修改 `useChatStore.js`，使用 HTTP 接口加载历史
- [ ] 创建 `DocumentAttachment.vue` 组件
- [ ] 修改 `ChatView.vue`，支持附件显示和分页加载
- [ ] 实现滚动加载更多功能

### 阶段 5：清理和测试
- [ ] 移除 WebSocket 的 `chat.history` 相关代码
- [ ] 端到端测试
- [ ] 性能优化（如需要）

---

## 6. 数据迁移

现有数据在 LangGraph checkpointer 中，需要迁移脚本：

```python
# python/scripts/migrate_messages.py

def migrate_messages():
    """从 checkpoints.sqlite 迁移消息到 messages.sqlite"""
    # 1. 读取 checkpoints.sqlite 中的 messages
    # 2. 解析 LangChain 消息对象
    # 3. 转换格式并写入新数据库
    
    # 注意：
    # - HumanMessage -> role='user'
    # - AIMessage -> role='assistant'
    # - ToolMessage -> role='tool'
    # - 附件信息需要从消息内容中提取（如果有）
```

---

## 7. 技术要点

### 7.1 数据库连接管理

使用 SQLAlchemy 的异步支持：

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 使用 aiosqlite 作为异步驱动
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

### 7.2 消息 ID 生成

使用 UUID 生成唯一 ID，格式：`msg-{uuid4().hex[:12]}`

### 7.3 分页策略

- 按 `created_at DESC` 排序
- 使用 offset/limit 分页
- 返回总数供前端显示分页控件

### 7.4 文档 Icon 映射

| 文件后缀 | Icon 类型 | 颜色 |
|---------|----------|------|
| .pdf | PDF icon | 红色 (#ef4444) |
| .doc, .docx | Word icon | 蓝色 (#3b82f6) |
| .xls, .xlsx | Excel icon | 绿色 (#10b981) |
| .ppt, .pptx | PowerPoint icon | 橙色 (#f97316) |
| .txt, .md | Text icon | 灰色 (#64748b) |
| 其他 | Generic file icon | 浅灰 (#94a3b8) |

---

## 8. 风险与注意事项

1. **数据一致性**：消息保存失败时的回滚策略
2. **性能**：大量附件时的查询性能（考虑索引优化）
3. **存储**：base64 图片占用空间较大，考虑是否需要压缩
4. **兼容性**：旧版本数据的迁移和兼容
5. **并发**：多线程环境下的数据库连接管理

---

## 9. 容错设计：写库失败不影响聊天

### 9.1 核心原则

**聊天优先**：消息持久化是辅助功能，不能阻塞或影响正常的 AI 聊天流程。

### 9.2 异步写入策略

```python
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# 使用线程池执行数据库写入，避免阻塞主事件循环
_db_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="db_writer")

async def save_message_async(message_data: dict):
    """异步保存消息，失败时仅记录日志不影响聊天"""
    loop = asyncio.get_event_loop()
    try:
        # 在线程池中执行数据库写入
        await loop.run_in_executor(_db_executor, _save_message_sync, message_data)
    except Exception as e:
        # 捕获所有异常，仅记录警告日志
        logger.warning(f"消息保存失败（不影响聊天）: {e}")

def _save_message_sync(message_data: dict):
    """同步数据库写入实现"""
    # 实际的 SQLAlchemy 写入逻辑
    pass
```

### 9.3 写入时机与错误处理

| 消息类型 | 写入时机 | 错误处理 |
|---------|---------|---------|
| 用户消息 | 发送前异步写入 | 失败时继续发送，仅记录日志 |
| AI 消息 | 流式完成后异步写入 | 失败时仅记录日志，不影响下一轮对话 |
| 工具消息 | 工具执行完成后异步写入 | 失败时仅记录日志 |
| 附件 | OCR 完成后异步写入 | 失败时仅记录日志，附件内容仍传给 AI |

### 9.4 代码示例：用户消息保存

```python
# ws_agent.py 中的 _handle_chat_send

async def _handle_chat_send(ws, payload: dict, room_ref: dict | None = None):
    content = (payload.get("content") or "").strip()
    attachments = payload.get("attachments") or []
    msg_id = uuid.uuid4().hex[:12]
    
    # ... 消息校验和内容构造 ...
    
    session_id = conversations.active_id()
    
    # 异步保存用户消息（不阻塞聊天）
    asyncio.create_task(_save_user_message_safe(
        session_id=session_id,
        msg_id=msg_id,
        content=content,
        attachments=attachments
    ))
    
    # 继续正常的聊天流程（不受保存失败影响）
    # ... 后续代码 ...

async def _save_user_message_safe(session_id: str, msg_id: str, content: str, attachments: list):
    """安全地保存用户消息，失败不影响聊天"""
    try:
        await save_message_async({
            "id": msg_id,
            "session_id": session_id,
            "role": "user",
            "content": content,
            # ... 其他字段 ...
        })
        # 保存附件
        for att in attachments:
            await save_attachment_async({
                "message_id": msg_id,
                # ... 附件字段 ...
            })
    except Exception as e:
        logger.warning(f"用户消息保存失败: {e}")
```

### 9.5 降级策略

如果数据库持续写入失败（如磁盘满、权限问题），系统应：
1. 继续正常运行，聊天功能不受影响
2. 在日志中记录错误，便于排查
3. 可选：通过 WebSocket 通知前端显示"历史记录保存失败"提示（非阻塞）

### 9.6 数据恢复

对于写入失败的消息，可考虑：
- 短期：依赖 LangGraph checkpointer 中的消息（50 条窗口）
- 长期：实现消息补传机制（定时检查 checkpoint 与 messages 表的差异）

---

## 9. 后续优化

1. 消息搜索功能
2. 附件预览（PDF、Office 文档）
3. 消息导出功能
4. 软删除和回收站
5. 消息编辑和删除
