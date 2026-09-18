# LLM 调用失败的兜底与「重试」方案

> **版本**: v1（待评审）
> **范围**: 单阶段（后端事件结构化 + 前重试 UI + 失败落库）
> **背景**: Qwen/百炼侧内容审核返回 `400 InternalError.Algo.DataInspectionFailed`，
> 以及网络抖动、限流、超时等，都会让 `agent.stream` 抛出异常。当前实现已把异常转成
> `chat.error` 事件，但**没有重试入口**、**错误文案不可读**、**失败轮次不落库**。

---

## 一、现状分析

### 1.1 相关代码位置

| 层 | 文件 | 关键位置 | 说明 |
|----|------|----------|------|
| Runner | `python/agent/runner.py` | `_worker_stream` 127–129 | `except Exception` → 投 `{"kind":"error","message":str(e)}` |
| Runner | `python/agent/runner.py` | `run_turn` 132 / `resume_turn` 157 | 两个入口都复用 `_worker_stream` |
| WS 服务端 | `python/server/ws_agent.py` | `_stream_turn` 372–386 | `error` → `chat.error`；外层再兜 `code:"internal"` |
| WS 服务端 | `python/server/ws_agent.py` | `_handle_chat_send` 441–538 | `chat.started` 在调 LLM 前发出（511） |
| WS 服务端 | `python/server/ws_agent.py` | 消息分发 710–713 | `chat.send` / `chat.cancel` 等控制帧 |
| 前端状态 | `src/composables/useChatStore.js` | `chat.error` 161–165 | 置 `m.error`、`streaming=false`、`generating=false` |
| 前端状态 | `src/composables/useChatStore.js` | `chat.started` 87–122 | 判断"复用上一条"还是"新建"助手消息 |
| 前端视图 | `src/views/ChatView.vue` | 193 / 764 | `<div v-if="m.error" class="msg-error">` |
| 前端 WS | `src/composables/useAgentSocket.js` | `send/on` 102–110 | 通用控制帧发送 |
| 持久化 | `python/server/db/models.py` | `Message` 20–45 | **无 error 字段** |
| 持久化 | `python/server/db/message_repository.py` | `save_message` / `update_message` | 无 error 参数 |

### 1.2 现状链路（异常已事件化，不会崩）

```
agent.stream 抛异常
  └─ runner._worker_stream  except → q.put({kind:"error", message:str(e)})
       └─ ws_agent._stream_turn  → hub.publish("chat.error", {code:"agent_error", message})
            └─ useChatStore.on('chat.error') → m.error=..., generating=false
                 └─ ChatView  <div class="msg-error">{{ m.error }}</div>
```

> 即"不直接抛出异常、改为返回 error 事件"**已经满足**。本方案不重复造这一层。

### 1.3 现状缺口

| # | 缺口 | 影响 |
|---|------|------|
| G1 | `message` 是原始异常字符串（含英文 + JSON body） | 用户看不懂，且泄露内部结构 |
| G2 | 无重试入口 | 用户只能重新手打一遍问题 |
| G3 | 失败轮次的 assistant 消息**不落库**（仅 `done` 分支保存，353） | 刷新后错误与消息一起消失，历史不完整 |
| G4 | `chat.error` 找不到消息时静默丢弃（161） | 多窗口 / 边界场景错误无声消失 |
| G5 | `Message` 表无 error 字段 | 无法持久化"这条回复失败了"状态 |

---

## 二、目标与非目标

### 2.1 目标

1. **可读的错误提示**：任何 LLM 调用失败，前端展示一条友好中文提示（原始堆栈只进日志）。
2. **始终提供重试按钮**：错误气泡下**一律**渲染「重试」按钮；是否重试**完全由用户决定**。
3. **重试 = 重新生成上一轮**：不追加重复的用户消息，不污染会话历史。
4. **失败轮次落库**：刷新/切回会话后，错误状态与重试入口依然存在。
5. **多窗口一致**：重试事件经 `hub.publish` 广播，所有窗口同步。

### 2.2 非目标（明确排除）

- ❌ 不做"改写措辞后重发"的引导或自动化（用户明确要求：不改写）。
- ❌ 不做"可重试/不可重试"驱动的按钮显隐（重试按钮一律显示，不做判断）。
- ❌ 不做前端自动重试 / 指数退避（完全交给用户手动点）。
- ❌ 不改动 SDK 层 `max_retries`（保持 `ChatOpenAI` 默认 2 次，仅覆盖 429/5xx/网络）。
- ❌ 不改动 interrupt / 工具确认（HITL）链路。

---

## 三、已确认的产品决策

| 决策点 | 结论 |
|--------|------|
| 失败处理方式 | 不抛未捕获异常（现状已满足），统一转为 `chat.error` 事件 |
| 重试按钮 | **一律显示**，不做错误类型判断，不给"改写"引导；是否重试由用户全权决定 |
| 重试语义 | **重新生成上一轮**（从当前 checkpoint 续跑），不新增重复 user 消息 |
| 消息复用 | 复用**失败的那条 assistant 消息**（同 `msgId`），避免界面出现"报错一条 + 成功一条" |
| 失败落库 | 失败轮次也落库，保留 `error` 状态字段 |
| 错误文案 | 轻量分类**仅用于生成中文提示**，不用于控制按钮显隐 |

---

## 四、关键技术决策

### 4.1 错误事件契约（扩展 `chat.error` payload）

`runner._worker_stream` 的 except 分支产出结构化 error：

```python
# runner.py  —— 伪代码
except Exception as e:
    logger.exception("agent.stream 异常")
    q.sync_q.put({
        "kind": "error",
        "code": classify_error_code(e),      # 仅用于文案，见 4.2
        "message": friendly_error_message(e), # 面向用户的中文提示
        "raw": str(e),                        # 仅日志/调试，不下发前端
    })
```

`ws_agent._stream_turn` 的 `error` 分支透传：

```python
elif kind == "error":
    await flush()
    await emit("chat.error", {
        "msgId": msg_id,
        "code": event.get("code", "agent_error"),
        "message": event.get("message") or "生成失败",
    })
```

> 与现状（372–386）的差异：`message` 由 `str(e)` 改为**友好文案**；新增 `code`（可保留 `agent_error`/`internal` 作为兜底值）。

### 4.2 错误文案（轻量分类，只为可读性）

> 分类**不参与**按钮显隐决策，仅把技术异常翻译成一句人话。

| 判定（按优先级） | code | 面向用户文案 |
|------------------|------|--------------|
| `status==400` 且 body 含 `DataInspectionFailed` | `content_inspection` | 请求被平台内容审核拦截，请调整输入后重试 |
| `status==400` 其他 | `bad_request` | 请求参数有误（可能是上下文过长或格式问题），请重试或检查输入 |
| `status==401` | `auth` | API Key 无效或已过期，请到设置中检查 |
| `status==404` | `model_not_found` | 模型不存在，请检查模型配置 |
| `status==429` | `rate_limit` | 请求过于频繁，请稍后重试 |
| `status>=500` | `upstream` | 上游服务异常，请稍后重试 |
| `APIConnectionError`/`APITimeoutError` | `network` | 网络异常或超时，请重试 |
| 其他 | `unknown` | 生成失败，请重试 |

- 判定依据来自 `openai.APIStatusError`（`status_code` / `body`），`langchain_openai` 会透传。
- 分类失败（拿不到 status）一律落到 `unknown`，不阻断主流程。

### 4.3 重试机制（核心）

**目标语义**：点「重试」= 让 Agent 从"上一轮失败的地方"重新生成，**不新增用户消息**。

设 `thread_id = session_id`，LangGraph 带 checkpointer。一次失败轮次的状态：

- 用户输入已被写入 checkpoint（图在接收 input 时落一次 checkpoint），
- 失败的**模型节点未提交**，因此 checkpoint 里没有新的 `AIMessage`。

**方案 A（首选）：从 checkpoint 续跑，输入传 `None`**

```python
# runner.py —— 新增
async def retry_turn(thread_id: str, cancel_event: threading.Event):
    """重试：从当前 checkpoint 续跑，不追加新的用户输入。"""
    version, agent = holder.get()
    q = janus.Queue()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": _recursion_limit()}
    thread = threading.Thread(
        target=_worker_stream,
        args=(agent, None, config, q, cancel_event),   # ← input_payload=None
        daemon=True,
    )
    thread.start()
    try:
        while True:
            event = await q.async_q.get()
            yield event
            if event["kind"] in ("done", "error"):
                break
    finally:
        q.close()
```

- `agent.stream(None, config, ...)` 从 last checkpoint 继续，等价于"重跑失败的那个节点"。
- **前提**：checkpoint 存在且存在待执行节点（`state.next` 非空）。

**方案 B（兜底）：重发最后一条用户消息**

- 触发条件：方案 A 不适用（无 checkpoint、`state.next` 为空、或续跑直接报"无输入"）。
- 实现：从 DB 读该会话最后一条 `role='user'` 消息内容，走 `run_turn(content, ...)`。
- **代价**：会在历史里新增一条重复 user 消息。作为罕见情况的降级，接受此代价。
- 判定顺序：先尝试 A，捕获到"无 pending 节点/输入为空"类错误再回退 B。

> ⚠️ 待验证（见第七节 R1）：LangGraph 对 `input=None` 续跑在"节点异常未提交"场景的实际行为，
> 需要用最小用例实测确认 `state.next` / 重复执行范围。

### 4.4 消息复用（扩展 `chat.started` 的复用分支）

重试时应**复用失败的那条 assistant 消息**，而不是再 push 一条。当前复用条件（`useChatStore.js` 99）：

```js
if (last && last.role === 'assistant' && (hasTools || wasInterrupted)) { /* 复用 */ }
```

扩展为：最后一条 assistant 消息**带 error 标记**时也复用：

```js
const wasErrored = !!last?.error
if (last && last.role === 'assistant' && (hasTools || wasInterrupted || wasErrored)) {
  last.id = p.msgId
  last.streaming = true
  last.thinking = false
  last.error = null            // ← 清除错误，进入新一轮
  last.errorCode = null
  last.reasoningOpen = true
}
```

### 4.5 失败落库（新增 `error` 字段 + 迁移 0005）

`Message` 表当前无 error 字段。新增：

```python
# models.py —— Message 增列
error = Column(Text)   # 失败提示文案（为空表示正常完成）
```

- 迁移文件：`python/server/db/migrations/versions/0005_message_error.py`（沿用 0001–0004 命名规范）。
- `save_message` / `update_message` 增加 `error: Optional[str] = None` 参数并写库。
- `_save_or_update_assistant_message_sage` 增加 `error` 透传。
- `ws_agent` 的 `chat.error` 分支补一次落库（含已积累的 `content_parts`）：

```python
elif kind == "error":
    await flush()
    msg = event.get("message") or "生成失败"
    await emit("chat.error", {"msgId": msg_id, "code": event.get("code"), "message": msg})
    asyncio.create_task(_save_or_update_assistant_message_sage(
        session_id=session_id, msg_id=msg_id,
        content="".join(content_parts), error=msg,
        reasoning="".join(reasoning_parts) or None,
        tool_calls=tool_call or None,
        tool_call_args=tool_call_args_list or None,
        tool_call_result=tool_call_result or None,
        usage_metadata=usage_metadata,
    ))
```

- HTTP 列表接口（`python/server/app.py` 消息查询）+ 前端 `transformMessage`（`useChatStore.js` 390+）
  一并透出 `error`，使历史回填后仍渲染错误气泡与重试按钮。

### 4.6 多窗口与并发

- 重试经 `hub.publish(session_id, ...)` 广播，**不要**只在当前 ws `_send`。
- 复用 `_handle_chat_send` 的并发保护：重试前取消同 session 旧轮次（`_session_cancel`，490–493）。
- `msgId` 复用失败消息的 id（前端从 `chat.error` 已拿到），保证多窗口按 `msgId` 精准回填。

---

## 五、实施阶段

### 阶段 1：后端错误事件结构化（`runner.py`）
- [ ] 新增 `classify_error_code(e)` / `friendly_error_message(e)`
- [ ] `_worker_stream` except 产出 `{kind:"error", code, message, raw}`
- [ ] `ws_agent._stream_turn` error / 外层兜底分支透传 `code` + 友好 `message`

### 阶段 2：重试控制帧与 runner 入口
- [ ] `runner.retry_turn(thread_id, cancel)`（方案 A，`input=None`）
- [ ] 方案 B 兜底：无 pending 节点时回退重发最后一条 user 消息
- [ ] `ws_agent` 新增 `_handle_chat_retry`：取激活会话 → 取消旧轮次 → 发 `chat.started`（复用 msgId）→ 消费 `retry_turn`
- [ ] 分发器增加 `chat.retry` 分支（与 `chat.send` 并列，710–713）

### 阶段 3：前端重试 UI 与消息复用
- [ ] `useChatStore.js`：`chat.error` 保存 `m.error / m.errorCode`；找不到消息时兜底（G4）
- [ ] `useChatStore.js`：`chat.started` 复用分支增加 `wasErrored`（4.4）
- [ ] `useChatStore.js`：新增 `retryLastTurn(msgId)` → `send('chat.retry', {sessionId, msgId})`，并置 `generating=true`
- [ ] `ChatView.vue`：`.msg-error` 区域加「重试」按钮，`@click="retryLastTurn(m.id)"`

### 阶段 4：失败落库与历史回填
- [ ] `models.py` 增 `error` 列 + 迁移 `0005_message_error.py`
- [ ] `message_repository` 的 save/update 增 `error` 参数
- [ ] `_save_or_update_assistant_message_sage` 透传 `error`
- [ ] `chat.error` 分支触发落库
- [ ] HTTP 消息接口 + `transformMessage` 透出 `error` → 历史渲染错误气泡与重试入口

---

## 六、验收与测试

| 场景 | 期望 |
|------|------|
| 触发 `DataInspectionFailed`（400） | 气泡显示友好文案 + 「重试」按钮；控制台/日志保留原始堆栈 |
| 断网 / 网关超时 | 同上，文案为"网络异常或超时，请重试" |
| 点「重试」成功 | 复用同一条助手消息，错误消失、正常流式输出；**历史中不出现重复 user 消息** |
| 点「重试」再次失败 | 仍显示错误 + 重试按钮（可无限次重试，无死循环副作用） |
| 失败后刷新页面 | 错误气泡与重试按钮仍在（落库生效） |
| 双窗口 | 一端点重试，另一端同步看到新一轮流式输出 |
| 失败发生于工具执行中途 | 重试行为定义清晰（7 R2），不产生悬挂 tool_call |

单元/集成测试建议：
- `runner`：异常 → 事件字段断言（code/message 存在、`raw` 不下发）。
- `message_repository`：save/update 带 `error` 往返。
- 迁移：`0005` 升降级可执行。

---

## 七、风险与待验证

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| R1 | `agent.stream(None)` 续跑在"节点异常未提交"下的实际语义未实测 | 方案 A 可能不符合预期 | 先写最小 LangGraph 用例验证 `state.next` / 重跑范围；不达标则转方案 B |
| R2 | 失败发生在工具执行中途（有 tool_calls 无 ToolMessage） | 续跑可能悬挂或重复执行工具 | 明确该场景走方案 B 或先中断清理；加测试用例 |
| R3 | 方案 B 会产生重复 user 消息 | 历史脏 | 仅在 A 不可用时降级；文案与文档标注 |
| R4 | `Message` 增列需迁移，老库升级 | 兼容性 | 迁移幂等、可回滚；确认 alembic 升级链路 |
| R5 | `_session_cancel` 与多窗口并发重试 | 双流写同一 checkpoint | 重试前强制取消旧轮次；复用现有保护 |
| R6 | 友好文案分类覆盖不全 | 退化为通用文案 | 落到 `unknown` 兜底，不阻断 |

---

## 八、影响面清单（改动文件）

| 文件 | 改动 |
|------|------|
| `python/agent/runner.py` | 错误结构化 + `retry_turn` |
| `python/server/ws_agent.py` | `chat.error` 透传/落库 + `_handle_chat_retry` + `chat.retry` 分发 |
| `python/server/db/models.py` | `Message.error` 列 |
| `python/server/db/message_repository.py` | save/update 增 `error` |
| `python/server/db/migrations/versions/0005_message_error.py` | 新增迁移 |
| `python/server/app.py` | ~~消息查询接口透出 `error`~~（实际无需改动，见 9.2） |
| `src/composables/useChatStore.js` | `chat.error` / `chat.started` / `retryLastTurn` / `transformMessage` |
| `src/views/ChatView.vue` | 错误气泡 + 重试按钮 |
| `tests/tmp_test_migration.py` | 断言升级至 0005 + `messages.error` 列校验 + 旧库按 0001 schema 建表 |

---

## 九、实施状态（v1 已完成）

> 已完成并验证。以下为落地记录与相对原计划的偏差。

### 9.1 已完成（阶段 1–4 全部）

- **阶段 1**：`runner.classify_error()` 分类 + 友好文案；`_worker_stream` 产出 `{kind:"error", code, message, raw}`；`ws_agent._stream_turn` 透传 `code`。
- **阶段 2**：`runner.retry_turn()`（`input=None` 从 checkpoint 续跑）；`ws_agent._handle_chat_retry()` + `chat.retry` 控制帧分发；方案 B 兜底（`_last_user_content`）。
- **阶段 3**：`useChatStore` 的 `chat.error`（存 `error`/`errorCode` + 找不到消息时兜底）、`chat.started`（`wasErrored` 复用分支 + 清空旧内容）、`retryLastTurn()`、`transformMessage` 透出 `error`；`ChatView.vue` 错误气泡 + 「重试」按钮 + 样式。
- **阶段 4**：`Message.error` 列 + 迁移 `0005_message_error`（batch_alter_table）；`save_message`/`update_message` 增 `error` 参数；两个查询 dict 透出 `error`；`chat.error` 分支失败落库；done 分支以 `error=""` 显式清除历史错误标记。

### 9.2 与原计划的偏差

| 项 | 原计划 | 实际 |
|----|--------|------|
| `python/server/app.py` | 需改为透出 `error` | **无需改动**：`/api/messages` 直接返回 repository 的 item dict，字段随 repository 自动透出 |
| 重试消息内容重复 | 未细化 | 新增：`_handle_chat_retry` 落库前**重置**该消息 content/reasoning/tools/error，避免与失败残留拼接；前端 `chat.started` 同步清空 |
| 方案 A/B 判定 | 描述性 | 落在 `_handle_chat_retry`：`state.next` 非空走 A，否则读最后一条 user 消息走 B；两者皆无则回 `nothing_to_retry` |
| 迁移测试 | 未提及 | 更新 `tests/tmp_test_migration.py`（版本断言、error 列校验、旧库 schema） |

### 9.3 验证记录

| 验证项 | 结果 |
|--------|------|
| Python 语法编译（5 个改动文件） | ✅ 通过 |
| `agent.runner.classify_error()` 分类 | ✅ 400+DataInspectionFailed→`content_inspection`；401→`auth`；500→`upstream`；其他→`unknown` |
| `server.ws_agent` / `message_repository` / `models` 导入 | ✅ 通过（`_handle_chat_retry` 存在、`error` 参数与列存在） |
| `tests/tmp_test_migration.py`（全新库 / 旧库升级 / 幂等重启） | ✅ **ALL PASSED**（0005 迁移正确应用，`messages.error` 列存在） |
| 前端 `npm run build` | ✅ 通过（exit 0） |

### 9.4 仍待人工验收（需运行态）

- 真实触发 `DataInspectionFailed` 等异常 → 气泡显示友好文案 + 重试按钮。
- 点「重试」→ 复用同一条助手消息、无重复 user 消息（**依赖 7-R1：LangGraph `input=None` 续跑行为需实测**）。
- 失败后刷新页面 → 错误气泡与重试入口仍在（落库生效）。
- 双窗口一端重试另一端同步。
- 失败发生于工具执行中途（7-R2）的实际表现。