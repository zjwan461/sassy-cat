# 上下文窗口（contextWindow）动态检查与自动压缩方案

> **版本**: v1（设计稿，待评审，仅设计不含实现）
> **范围**: 后端 middleware 阶段（动态 token 检查 + 摘要式压缩）；前端设置页提供 `contextWindow` 配置项
> **一句话**: 每次进入模型调用前估算当前请求的 token 占用，达到 `contextWindow` 的 **85%** 时，
> 把久远历史「总结成一条摘要消息」，保留近端原文，而不是粗暴丢弃。

---

## 一、背景与现状

### 1.1 配置早已备好，但无人读取

`python/config_loader.py` 的 `DEFAULTS` 里，`llm.profiles.<name>` 已定义：

```python
"default": {
    "label": "默认",
    "provider": "openai",
    "baseUrl": "",
    "apiKey": "",
    "model": "",
    "temperature": 0.7,
    "contextWindow": 262144,   # <-- 后端目前没有任何读取点（前端设置页已可写入）
    "extraParams": {},
}
```

实测全仓 `grep contextWindow`，后端只命中 `config_loader.py` 这一处声明 —— 也就是说
**在后端它只是被"声明"了，从未参与任何逻辑**（前端「设置 → 模型连接」现已可写入该字段，
但后端仍无读取点）。本次方案就是把 `contextWindow` 真正用起来。

### 1.2 现有的上下文治理方式：只按「条数」裁剪

`python/agent/middlewares.py::trim_messages`（`@before_model`）当前的策略：

```python
memory_window = int(cfg.active_agent_config().get("memoryWindow", 50))
if len(messages) <= memory_window:
    return None
first_msg = messages[0]
recent_messages = messages[-memory_window:]      # 只保留首条 + 最近 N 条
return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), first_msg, *recent_messages]}
```

它**只看消息条数，完全不看 token 量**，因此存在两类失效场景：

| # | 场景 | 后果 |
|---|------|------|
| P1 | 消息条数少，但单条极长（整篇文档、超长工具输出、大段代码） | 条数没到 50，token 却早已溢出 → 上游 400 / 被静默截断 |
| P2 | 消息条数多，但每条都很短 | 可能过早丢弃仍有价值的历史 |
| P3 | 裁剪是「硬丢」 | 被丢掉的历史信息永久消失，模型失去连续性 |

### 1.3 现状链路（相关位置）

| 层 | 文件 | 关键位置 | 说明 |
|----|------|----------|------|
| 配置 | `python/config_loader.py` | `DEFAULTS.llm.profiles.*` 28–30 | 已含 `temperature` / `contextWindow` |
| 中间件 | `python/agent/middlewares.py` | `trim_messages` 20–42 | 按条数的硬裁剪（`before_model`） |
| 中间件 | `python/agent/middlewares.py` | `inject_base_info` / `inject_kb_info` | `wrap_model_call`，改写 system message |
| 装配 | `python/agent/engine.py` | `middleware=[trim_messages, inject_base_info, inject_kb_info]` 156 | 中间件注册顺序 |
| 构建 | `python/agent/llms.py` | `build_chat_llm(profile)` | 由 profile 构建 LLM，可复用于摘要调用 |
| 流式 | `python/agent/runner.py` | `usage_metadata` 135–137 | 已产出真实 token 用量事件，可用于校准估算 |
| 调用 | `python/agent/llms.py` | `simple_blocking_call(llm, prompt)` | 现成的同步摘要调用工具 |

---

## 二、目标与非目标

### 2.1 目标

1. **按 token 而非条数** 作为上下文压力的判据。
2. 每次 `before_model` **动态估算**当前请求的 token 占用。
3. 占用 **≥ 85% × contextWindow** 时触发**压缩**（summarization），而非直接丢弃。
4. 压缩产物 = 「一条历史摘要消息」+「近端 N 条原文」；system 与首条消息保留不动。
5. **幂等**：摘要消息带标记，反复触发时替换旧摘要而非叠加。
6. **可降级**：压缩失败（LLM 报错等）退化为现有硬裁剪，**绝不阻断对话**。
7. 与现有 `trim_messages` **协同**而非替代：条数上限继续作为廉价的第一道闸。

### 2.2 非目标（明确排除）

- ❌ 不做向量化的长期记忆 / RAG 式回忆（另立项）。
- ❌ 不改动 checkpointer 的持久化表结构（摘要作为普通 message 写回 state 即可）。
- ❌ 不做精确 tokenizer 依赖（不引入 tiktoken / 模型分词器本地化）。
- ❌ 不做前端 token 仪表盘 / 手动"压缩"按钮（列为可选后续）。
- ℹ️ `contextWindow` 本期**已在设置页可配**（见 §三）；压缩子参数（阈值 / 保留条数 / 开关）暂用内置默认。
- ❌ 不改动 `interrupt`（HITL）与工具确认链路。

---

## 三、配置设计

在 `llm.profiles.<name>` 下扩展（**与模型绑定**，故放 llm profile 而非 agent profile）：

| 键 | 含义 | 默认 | 说明 |
|----|------|------|------|
| `contextWindow` | 模型上下文窗口（token） | `262144` | 已存在，本次首次启用 |
| `contextCompression.enabled` | 是否启用自动压缩 | `true` | 关闭则退化为纯 `trim_messages` |
| `contextCompression.threshold` | 触发阈值（占 `contextWindow` 比例） | `0.85` | `used ≥ window × threshold` 即压缩 |
| `contextCompression.keepRecent` | 压缩后保留的近端原文条数 | `20` | 与 `memoryWindow` 独立 |
| `contextCompression.reserveTokens` | 为「输出 + system 注入」预留的 token | `4096` | 计算预算时先扣除，避免压完仍溢出 |

> 设计取舍：默认值直接写进 `config_loader.DEFAULTS`，用户不配也能生效。
> **前端可见性**：`contextWindow` 本期**已在设置页「模型连接」卡片提供输入**（步进器，
> 范围 8192~1048576，默认 262144），落盘路径 `llm.profiles.<name>.contextWindow`，
> 随「保存设置」一并写入；压缩子参数（`enabled` / `threshold` / `keepRecent` /
> `reserveTokens`）先用内置默认，后续可选地在同一卡片加一个可折叠的「上下文管理（高级）」分组暴露。

---

## 四、token 估算策略

三条路线，推荐 **A 起步 + C 校准**：

| 方案 | 做法 | 依赖 | 精度 | 采用 |
|------|------|------|------|------|
| A. 轻量估算 | 按字符类别加权：CJK ≈ 1 token/字，其余 ≈ 0.25 token/字；每条消息固定开销 | 无 | ±15% | ✅ 默认 |
| B. 精确编码 | `tiktoken` / 模型自带 tokenizer | 重、qwen 系不一定可用 | 高 | ❌ |
| C. 实测校准 | 用上一轮真实 `usage_metadata.input_tokens` 反推修正系数（EMA） | 无（runner 已产 `usage`） | 逼近真实 | ✅ 预留钩子 |

**为什么 ±15% 够用**：阈值本身就是 **85%（留 15% 余量）**，再叠加 `reserveTokens`，
估算误差被两重缓冲吸收；压缩后目标占用降到 ~50% 窗口，不会在临界点抖动。

估算函数签名：

```python
def estimate_tokens(messages: list) -> int:
    """估算一批消息的 token 占用（粗粒度，用于阈值判断）。"""
    # 文本：CJK 字数 * 1.0 + 其他字符数 * 0.25
    # + 每条消息固定开销 ~4
    # + tool_calls 的 name/args（JSON 字符串同理计）
    # + 多模态图片块按固定大额计（如 1000/张）
```

**校准钩子（C）**：维护全局 EMA `_token_calibration`（初值 1.0），
每次拿到真实 `usage_metadata.input_tokens` 时 `factor = ema(estimate/actual)`，
估算结果乘以该系数。无数据时用 1.0。

---

## 五、压缩流程（middleware）

新增 `@before_model async def compress_context(state, runtime)`，注册在 `trim_messages` **之后**
（见 §七 顺序理由）。`engine.py` 的 middleware 列表改为：

```python
middleware=[trim_messages, compress_context, inject_base_info, inject_kb_info]
```

### 5.1 伪代码

```python
SUMMARY_MARKER = "[历史摘要]"

@before_model
async def compress_context(state: AgentState, runtime: Runtime) -> dict | None:
    cfg = config_loader.current()
    profile = cfg.active_llm_profile() or {}

    window = int(profile.get("contextWindow") or 262144)
    cc = profile.get("contextCompression") or {}
    if not cc.get("enabled", True):
        return None
    threshold  = float(cc.get("threshold", 0.85))
    keep_recent = int(cc.get("keepRecent", 20))
    reserve     = int(cc.get("reserveTokens", 4096))

    messages = state["messages"]
    budget = max(0, window - reserve)
    used = int(estimate_tokens(messages) * _calibration())
    if used < budget * threshold:
        return None                        # 未达阈值，放行

    head = messages[0]                     # 永远保留首条（工具清理/注入依赖它）
    tail = _safe_tail(messages, keep_recent)   # 见 5.2：避免拆散 tool_call 对
    middle = messages[1:-keep_recent]      # 待压缩区间
    if not middle:
        return None

    prev = _extract_prev_summary(middle)   # 已存在旧摘要则并入
    try:
        summary_text = await asyncio.to_thread(
            _summarize, profile, prev, middle
        )
    except Exception:
        logger.warning("上下文压缩失败，降级为硬裁剪", exc_info=True)
        return None                        # 交给 trim_messages 兜底

    summary_msg = SystemMessage(content=f"{SUMMARY_MARKER}\n{summary_text}")
    logger.info(
        "上下文压缩：%d -> %d 条，tokens≈%d -> %d (window=%d, threshold=%.2f)",
        len(messages), len(tail) + 2, used, estimate_tokens([head, summary_msg, *tail]),
        window, threshold,
    )
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), head, summary_msg, *tail]}
```

### 5.2 关键约束

| 约束 | 原因 | 做法 |
|------|------|------|
| **不能拆散 tool 调用对** | LangGraph 要求 `tool_call` 必有对应 `ToolMessage`，拆开会报错 | `_safe_tail` 从 `messages[-keep_recent]` 向前回溯，直到该消息**不是** `ToolMessage`（必要时向前扩容保留窗口） |
| **保留首条** | 现有实现一致；首条可能承载工具清理/元信息 | 强制 `head = messages[0]` |
| **摘要幂等** | 反复压缩不能叠成 N 条摘要 | 摘要以 `[历史摘要]` 标记落位；下次压缩先把旧摘要文本并入 `_summarize` 输入，产物仍只有一条 |
| **不污染主 chain** | 摘要调用不应进 checkpointer / 主对话历史 | 用**独立** `build_chat_llm(profile)` 实例做摘要（见 §六） |
| **不阻塞事件循环** | `simple_blocking_call` 是同步的 | 用 `asyncio.to_thread` 包装（与 `inject_kb_info` 里 `list_kbs_sync` 同款处理） |

---

## 六、摘要 LLM 调用

- **独立实例**：`llm = build_chat_llm(profile)`，`temperature` 取较低值（如 `0.2`），
  与主对话解耦，既不写入主 chain，也不受主对话 `temperature` 影响。
- **调用方式**：复用 `agent/llms.py::simple_blocking_call(llm, prompt)`。
- **Prompt 结构**（要求模型分节输出，减少遗漏）：

  ```
  你是对话记忆整理器。请把下面的历史对话压缩成简洁的中文摘要，分节输出：
  1) 事实与偏好：用户画像/称呼/环境等新增或修正的事实
  2) 任务与目标：正在进行的任务、已达成的结论
  3) 未完成事项：待办、被中断的步骤
  4) 关键引用：涉及的文件路径 / 知识库 ID / 提醒 ID 等可复用标识
  只保留可复用的信息，丢弃寒暄与中间推理过程。若已有旧摘要，请把它与新对话合并。
  ```

- **长度控制**：目标输出 `800~1200` token；超长则硬截断并告警，防止「摘要本身又把窗口塞满」。
- **成本**：一次压缩 = 一次额外 LLM 调用；因阈值 85% + 压缩后降到 ~50%，
  实际触发频率很低（长会话下大约每积累 ~40% 窗口触发一次）。

---

## 七、与现有 `trim_messages` 的协同

二者**互补**，同时保留：

| 中间件 | 判据 | 代价 | 处理 |
|--------|------|------|------|
| `trim_messages`（先执行） | 消息**条数** ≤ `memoryWindow` | 廉价（无 LLM 调用） | 硬丢最旧 |
| `compress_context`（后执行） | token ≤ `window × 0.85` | 较贵（一次 LLM 调用） | 摘要 + 保留近端 |

顺序理由：**先跑廉价的条数裁剪**——很多情况下条数裁剪后 token 已经达标，可**省掉一次摘要调用**；
只有「条数够但内容很长」（P1 场景）才真正触发压缩。

---

## 八、可观测性（可选）

1. **日志**：压缩时打印 `messages 数 / 估算 tokens / 窗口 / 阈值`（见 §5.1）。
2. **前端提示**（可选）：middleware 内无法直接 `hub.publish`，可经 `runtime.stream_writer`
   写 custom 事件：

   ```
   middleware ──stream_writer({"kind":"compacting"})──► runner._worker_stream(custom 分支)
        └─► ws_agent ──hub.publish("chat.compacting")──► useChatStore
             └─► ChatView 气泡显示「正在整理记忆…」
   ```

   需同步改动：`agent/middlewares.py` + `agent/runner.py` + `server/ws_agent.py` +
   `src/composables/useChatStore.js`（+ 可选 `ChatView.vue`）。

---

## 九、边界与风险

| # | 风险 | 说明 | 缓解 |
|---|------|------|------|
| R1 | 估算不准 | 中文 / 代码 / JSON 混排偏差大 | 阈值 15% 余量 + `usage_metadata` EMA 校准（§四 C） |
| R2 | 摘要有损 | LLM 漏掉关键事实 | 结构化 prompt（分节）+ 近端原文保留 + 标记可溯 |
| R3 | tool_call 对被拆散 | LangGraph 直接报错 | `_safe_tail` 边界回溯（§5.2） |
| R4 | 首条被摘要掉 | 工具清理 / 注入失效 | 强制保留 `messages[0]` |
| R5 | 压缩自身失败 | 阻塞整轮对话 | `try/except` → 降级为硬裁剪，返回 `None` |
| R6 | 反复抖动 | 每轮都触发压缩 | 压缩后目标 ~50% 窗口留足 headroom；可选「距上次压缩 N 轮」冷却 |
| R7 | 多模态图片 | 图片 token 难估 | 图片块按固定大额计（如 1000/张） |
| R8 | 摘要消息角色 | 误当用户输入 | 用 `SystemMessage` + `[历史摘要]` 标记，与 `inject_*` 的标记机制一致 |

---

## 十、落地步骤（实现阶段）

1. **配置**：`python/config_loader.py::DEFAULTS` 给 default profile 增补
   `contextCompression: {enabled, threshold, keepRecent, reserveTokens}`。
2. **中间件**：`python/agent/middlewares.py` 新增
   `estimate_tokens` / `_safe_tail` / `_summarize` / `compress_context` / `SUMMARY_MARKER`，
   并加入 `_token_calibration` EMA。
3. **装配**：`python/agent/engine.py` 的 `middleware=[...]` 在 `trim_messages` 之后插入 `compress_context`。
4. **校准接线**（可选）：`python/agent/runner.py` 的 `usage_metadata` 处回写校准系数。
5. **前端提示**（可选）：`runner.py` + `server/ws_agent.py` + `useChatStore.js` 打通 `chat.compacting`。
6. **设置页 UI**：`contextWindow` 输入框**已完成**（`src/views/Settings.vue`「模型连接」卡片，
   步进器 + 边界校验，随「保存设置」写入 `llm.profiles.<name>.contextWindow`）；
   压缩子参数（`enabled` / `threshold` / `keepRecent` / `reserveTokens`）的高级分组为**可选后续**。
7. **测试**：
   - 构造「单条超长消息」→ 验证 P1 场景能触发压缩；
   - 构造「大量短消息」→ 验证 `trim_messages` 先兜底；
   - 校验压缩后无 `tool_call` 孤对，模型继续正常作答；
   - 注入摘要调用失败 → 验证降级不中断对话。

---

## 附：与本次「temperature」改动的关系

- `temperature` 属**同一张卡片**（`llm.profiles.<name>`）的模型参数，已在前端「模型连接」
  落地（滑杆 0~2，默认 0.7），并由 `python/agent/llms.py::_resolve_temperature` 解析（浮点 + 范围保护）。
- `contextWindow` 已在前端「模型连接」卡片可配（步进器，默认 262144，范围 8192~1048576）；
  **后端逻辑本次仅设计** —— 待 §十 步骤 1~3 实现后，它才会真正参与上下文治理。
- 压缩子参数（`threshold` 等）用 `DEFAULTS` 内置默认，暂未在设置页暴露。