# dsh 子代理设置项可视化 —— 实施方案（已落地）

> 目标：把 dsh（DeepSeek Harness）子代理当前**只在代码里读取、设置页无法配置**的参数，接进 `src/views/Settings.vue`，
> 打通 `config.user.json` ↔ `dsh_invoker.py` 的读取链路，并保证保存后**无需重启服务**即热生效。

---

## 1. 配置契约（顶层独立 `dsh` 块）

dsh 配置**独立于 `llm` / `agent` 配置档**，是顶层全局块，与设置页「dsh 子代理」卡片一一对应：

```jsonc
// config.user.json
"dsh": {
  "useMainLlm": true,          // 默认勾选：直接复用主 Agent 当前激活的 LLM 配置档
  "llm": {                     // useMainLlm=false 时才走这里的独立连接
    "baseUrl": "",
    "apiKey": "",
    "model": ""
  },
  "systemPrompt": "……",         // 默认值即内置 dsh 提示词（前端直接展示、可编辑）
  "maxTokens": 131072,          // dsh 输出上限；DashScope qwen 系只接受 [1,131072]
  "reasoningEffort": ""         // ""=不指定；off/low/high/max（仅 deepseek-official 适配器识别）
}
```

**默认提示词放在配置里**（而非仅作为代码常量）：`config.json` 模板层的 `dsh.systemPrompt` 就是完整提示词文本，
设置页打开即展示、可直接编辑；`dsh_invoker.DEFAULT_SYSTEM_PROMPT` 作为纯 Python 路径的兜底，
两处文本**必须保持一致**（已在两边加同步注释）。

### 1.1 读取优先级（含旧配置只读回退，不自动迁移）

```
连接参数 : useMainLlm=true  -> llm.profiles.<active>  {baseUrl, apiKey, model}
           useMainLlm=false -> dsh.llm
           -> FALLBACK_BASE_URL / FALLBACK_API_KEY / FALLBACK_MODEL
systemPrompt     : dsh.systemPrompt
                 -> agent.profiles.<active>.dshSystemPrompt   (旧)
                 -> agent.dshSystemPrompt                     (旧·顶层)
                 -> DEFAULT_SYSTEM_PROMPT
maxTokens        : dsh.maxTokens（缺失或等于内置默认时回退旧位置）
                 -> llm.profiles.<active>.extraParams.maxTokens (旧)
                 -> FALLBACK_MAX_TOKENS
reasoningEffort  : dsh.reasoningEffort
                 -> llm.profiles.<active>.extraParams.reasoningEffort (旧)
                 -> None
```

> `maxTokens` 的特殊处理：`config_loader.DEFAULTS` 会把它填成内置默认，导致合并后的配置里
> 「用户没配」与「用户显式配成默认值」不可区分。因此把**缺失或等于内置默认**一律视为未配置，
> 让升级前写在 `extraParams.maxTokens` 的旧值仍能生效；用户在设置页保存过一次后该键被显式落盘，之后按显式值优先。

---

## 2. 解决的三个硬缺口

1. **缺 UI**：`dshSystemPrompt` / `maxTokens` / `reasoningEffort` 原只能手改 JSON → 已有独立卡片。
2. **`extraParams` 泄漏**：该对象在 `agent/llms.py` 里被整体当 `extra_body` 传给**主 agent** 的
   ChatOpenAI/ChatDeepSeek —— 给 dsh 设的 `reasoningEffort` 会一并泄漏到主模型请求
   （非 deepseek-official 网关上可能直接 400）。新命名空间只解决「今后不再泄漏」，
   旧用户写在 `extraParams` 里的值仍会泄漏给主模型（不自动迁移，已在 UI hint 说明）。
3. **热重载缺口**：`subagent_tool._HARNESS` 是进程级单例，`ws_agent` 的 `config.invalidate`
   只重建主 agent，**不触碰 dsh harness** → 改完配置必须重启服务。已补 `invalidate_harness()`。

---

## 3. 落地清单

### 3.1 后端

| 文件 | 改动 |
| --- | --- |
| `python/config_loader.py` | `DEFAULTS` 新增顶层 `dsh` 块（含 `systemPrompt` 留空即用内置默认的说明） |
| `config.json`（模板层） | 新增顶层 `dsh` 块，`systemPrompt` 写入完整默认提示词（前端展示用） |
| `python/agent/tools/dsh/dsh_invoker.py` | 新增 `DSH_REASONING_EFFORTS` 白名单、`read_dsh_block()`；`load_llm_settings()` 改为「复用主 Agent / 独立连接」双分支 + 回退链 + 校验；模块 docstring 与默认提示词处补同步说明 |
| `python/agent/tools/subagent_tool.py` | 新增 `invalidate_harness()`（只置 `_HARNESS_STALE` 脏标记）与 `_get_harness()` 惰性重建；`_drop_harness()` 顺带清脏；注释写明「必须在 `_HARNESS_LOCK` 内调用」不变量 |
| `python/server/ws_agent.py` | `config.invalidate` 分支在 `holder.invalidate()` 后追加 `subagent_tool.invalidate_harness()`（try/except 兜底未安装 dsh 场景） |

**校验与降级**：`maxTokens` 非正整数或不可解析 → 回退 131072 + warning；
`reasoningEffort` 不在白名单 → 降级为 `None` + warning（非法枚举会让 dsh `initialize` 直接失败）。
两个分支都绝不把非法值透传给 dsh。

### 3.2 Electron

| 文件 | 改动 |
| --- | --- |
| `electron/config-store.js` | `maskSecrets` 增加 `dsh.llm.apiKey` 掩码（`***` + 末 3 位）；新增 `getTemplate()`（模板层深拷贝，只读） |
| `electron/main.js` | 新增 IPC `config:get-raw-dsh-key`（取未掩码的 dsh 独立 apiKey）、`config:get-template`（取模板层默认值） |
| `electron/preload.js` | 暴露 `getRawDshKey`、`getConfigTemplate` |

### 3.3 前端（`src/views/Settings.vue`）

新增**独立卡片「dsh 子代理（DeepSeek Harness）」**（放在 Agent 配置卡片之后，用 `.card.wide` 占满整行，
不依赖 `nth-child(1)(2)` 那条位置规则）：

- `复用主 Agent 的 LLM` 复选框（默认勾选），hint 实时显示当前生效的连接（`mainLlmSummary`）；
  **勾选时下方 Base URL / API Key / 模型名称三项整组隐藏**（值仍随保存一起落盘，不丢失）。
- `系统提示词` textarea：打开即显示配置中的默认提示词；hint 给出字数与 `{shell_guidance}` 变量说明；
  `恢复默认提示词` 按钮从**模板层**（`getConfigTemplate`）取内置文本还原（因为用户层会覆盖它，从合并视图取不回来）。
- `最大输出 tokens`：复用 `.stepper`，范围 1~131072。
- `推理强度（reasoningEffort）`：下拉（不指定 / off / low / high / max），hint 说明仅 dsh 适配器识别、与主 Agent「额外参数」互不影响。

脚本侧：`form` 增加 7 个 `dsh*` 字段；`loadConfig()` 读取 `cfg.dsh.*` 并拉取模板层默认提示词；
`saveAll()` 追加 `dsh.useMainLlm / dsh.llm.baseUrl / dsh.llm.model / dsh.systemPrompt / dsh.maxTokens / dsh.reasoningEffort`
六条 patch，以及非掩码时写入 `dsh.llm.apiKey` 的条件 patch；
`send('config.invalidate', { paths: ['llm','agent','rag','dsh'] })` 触发 Step 3.1 的 harness 失效。

---

## 4. 验证

`tests/tmp_dsh_settings_probe.py`（临时探测，用完可删；启动时把 `SASSY_CAT_DATA_DIR` 指到临时目录并清掉
`LLM_*` 环境变量，避免污染真实用户数据）覆盖 22 项断言，全部通过：

1. 无用户配置：复用主 Agent LLM、内置提示词、`maxTokens=131072`、不传 `reasoningEffort`；
2. `useMainLlm` 缺省 / true / false 三态；
3. 顶层 `maxTokens` / `reasoningEffort` 生效；
4. 旧位置只读回退 + 新位置优先；
5. 非法值降级（非数字 / 负值 / 数字字符串 / 白名单外 effort）；
6. `invalidate_harness()` 后 `_get_harness()` 确实重建（monkeypatch `build_harness` 计数）。

另有两项一致性校验：
- `config.json` 的 `dsh.systemPrompt` 与 `dsh_invoker.DEFAULT_SYSTEM_PROMPT.strip()` **逐字节一致**（845 字）；
- `Settings.vue` 经 `@vue/compiler-sfc` 解析 + 编译（script / template）通过，新增字段全部接入模板。

> 注：`npm run build` 在 `pet/pet.html` 内联 CSS 处失败，属**既存问题**（与本改动无关），
> 构建流程根本走不到 `.vue` 编译，故改用 SFC 编译器直接校验。

---

## 5. 风险与已知取舍

1. **默认提示词双份维护**：`config.json` 与 `dsh_invoker.DEFAULT_SYSTEM_PROMPT` 各存一份（JSON 不支持注释，
   同步说明写在 Python 侧与 `config_loader` 注释里）。用户保存过一次后配置层胜出，漂移只影响「从未保存过」的安装。
2. **`_get_harness()` 的锁不变量**：若将来新增不经 `_HARNESS_LOCK` 的调用点，惰性重建会引入竞态，已在注释中声明。
3. **旧用户 `extraParams` 泄漏仍在**：只保证今后不再泄漏，不做自动迁移。
4. **`maxTokens` 不再进 `extraParams`**：若用户此前依赖它同时给主模型设上限，改 dsh 专用后主模型会失去该上限（UI hint 已说明）。

---

## 6. 可选扩展（未做）

- 打字机 / 工具结果截断参数（`_TYPEWRITER_*`、`_TOOL_RESULT_MAX_CHARS`）入配置；
- dsh 提示词最终版预览（新增 WS `dsh.prompt.preview`，后端复用 `load_llm_settings()`）；
- `测试 dsh` 连接自检按钮（起一次最小 harness 调用并回显）。