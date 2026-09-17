# 语音朗读（TTS）功能方案

> **版本**: v1（架构设计定稿）
> **范围**: 两个阶段
> - **Phase 1**：Electron + Web Speech API（系统语音，无需 GPU）—— 本期实施
> - **Phase 2**：本地 GPU TTS（N 卡 ≥8GB，模型待定，先以 ChatTTS 验证）—— 后续实施

---

## 一、现状分析

### 1.1 相关代码位置
| 模块 | 文件 | 说明 |
|------|------|------|
| 聊天页 | `src/views/ChatView.vue` | 消息流 + 复制按钮（`.msg-actions`） |
| 设置页 | `src/views/Settings.vue` | 卡片式设置，`saveAll()` 批量落盘 |
| 聊天状态 | `src/composables/useChatStore.js` | 模块级单例，订阅 WS 流式事件（`chat.delta` / `chat.completed` / `chat.user` 等） |
| 配置 | `config.json`（模板）+ `electron/config-store.js` | 双层配置，支持点路径读写（`voice.*` 可直接新增） |
| 主进程 | `electron/main.js` / `preload.js` | Phase 1 无需改动（Web Speech 在渲染进程内可用） |
| GPU 采集 | `python/monitor/gpu.py` | NVML → PDH → PowerShell 三级降级，供 Phase 2 显存检测复用 |

### 1.2 现状缺口
- 无任何语音朗读能力；AI 回复仅支持手动复制。
- 配置模板无 `voice` 段，需新增。
- 无 TTS 服务/引擎抽象层。

---

## 二、目标

### 2.1 Phase 1（本期）
1. AI 回复气泡下提供「朗读」按钮（复制按钮旁），支持播放/停止/切换。
2. 设置页新增「语音朗读（TTS）」卡片：
   - 语音方案下拉（当前仅 **Web Speech API**，注明无需 GPU；预留本地 TTS 占位）
   - 「启用语音朗读」总开关
   - 「AI 自动朗读」开关
   - 中文语音选择（含试听）+ 语速 / 音调调节
3. 支持中文播放（依赖系统中文语音包）。

### 2.2 Phase 2（后续）
- 基于 GPU 资源：N 卡 ≥8GB 显存时启用本地 TTS 模型，功能与 Phase 1 一致，仅引擎不同。
- 模型选择未定：先以 **ChatTTS** 验证（对话式 TTS，口语自然、情感丰富，契合傲娇猫娘人设），备选 **CosyVoice2**（Apache 2.0，可商用）。

### 2.3 非目标
- 不改动现有聊天/复制/会话逻辑。
- Phase 1 不做本地 TTS。
- 不做语音识别（ASR）。

---

## 三、已确认的产品决策

| 决策点 | 结论 |
|--------|------|
| 播读文本处理 | **剥离 Markdown 符号 + 跳过代码块**（朗读最自然） |
| 深度思考（reasoning） | **不朗读**，只读最终回复正文 |
| 自动朗读触发时机 | **流式播放缓冲**：正文累积 ≥10 字且成句后才开播（抗 LLM 网络波动；播放会话不中断、结束补读） |
| Phase 2 模型 | **暂不定**，Phase 1 完成后评估；先用 ChatTTS 验证 |

---

## 四、关键技术决策

### 4.1 配置结构（新增 `voice` 段）

```json
// config.json 模板新增
"voice": {
  "enabled": false,        // 语音功能总开关（默认关闭，避免突兀）
  "engine": "web-speech",  // 语音方案：web-speech（Phase 1）；local（Phase 2）
  "autoRead": false,       // AI 自动朗读开关
  "voiceName": "",         // 选中的中文语音名（Web Speech 的 voice.name）
  "rate": 1.0,             // 语速（0.1~2）
  "pitch": 1.0             // 音调（0~2）
}
```
- 读写走既有 `configStore.setByDotted / applyPatches`，**无需改 Electron 主进程与 preload**。
- `config-store` 对未知路径自动建对象，落盘到 `config.user.json`，安全兼容升级。

### 4.2 引擎抽象（useTTS 单例）

```javascript
// 形态：引擎接口
interface TtsEngine {
  init(): void                        // 枚举语音/初始化
  speak(text, opts?): void            // 朗读（手动）
  stop(): void                        // 停止
  getVoices(): Array<{ name, lang, localService }>
  // Phase 2 local 引擎实现同一接口（内部走 HTTP 生成音频再播放）
}
```

模块级单例 `src/composables/useTTS.js`（与 `useChatStore` 同模式，跨 tab 存活）：
- **中文语音枚举**：过滤 `lang` 以 `zh` 开头的系统语音；监听 `voiceschanged`（Electron/Windows 下首次 `getVoices()` 可能为空）；按配置 `voiceName` 匹配，无则回退到任意中文语音，再无则用默认语音并提示。
- **文本预处理**：`stripForSpeech(text)`：
  - 剔除围栏代码块（```` ``` ```` 与 `~~~` 包裹内容）与行内代码 `` `code` ``
  - 剥离 Markdown 标记：`#` 标题符、`**`/`*` 粗斜体、`-`/`1.` 列表符、`[text](url)` 取 `text`、`![alt](url)` 取 `alt`、`>` 引用符、表格分隔线等
  - 扁平化换行为单空格；按句/段切分（规避 Chromium 长文本截断 bug）

### 4.3 流式播放缓冲（LLM 网络波动抗抖）

收到正文片段后**不立即读**，而是累积到**播放缓冲**，满足门槛后再连续播放，
避免 LLM 网络波动（端到端停顿、零星字词到达）导致「读两句就被打断、再从头」的卡顿体验。

```javascript
// 常量
const BUFFER_MIN = 10        // 播放门槛：正文累积 ≥10 字才开播（Phase 1 内置于单例，后续可暴露到设置）
const FLUSH_AFTER_MS = 1500  // 尾流兜底：距最后一次 delta 超时且有内容则强制冲刷

// 状态
let pending = ''            // 播放缓冲：本轮尚未朗读的正文
let started = false         // 本轮是否已进入播放会话（门槛只约束首次启动）
let lastDeltaAt = 0         // 最后一次收到 delta 的时间戳（尾流兜底）
let activeMsgId = null      // 模块级当前朗读消息 id（跨 tab）
let speaking = ref('')      // 当前朗读的 msgId（响应式，供 UI 高亮）

// 算法
onDelta(msgId, text) {
  if (!voice.enabled || !voice.autoRead) return
  if (activeMsgId && activeMsgId !== msgId) { stop(); activeMsgId = msgId; started = false }
  else if (!activeMsgId) activeMsgId = msgId
  pending += stripForSpeech(text)          // 仅正文，跳过代码块
  lastDeltaAt = Date.now()
  // 门槛：未开播且缓冲不足 → 继续静默等待（避免零星字词开播即断）
  if (!started && pending.length < BUFFER_MIN) return
  started = true
  flushCompleteSentences()
}
flushCompleteSentences() {
  while (能切出完整句子) {                 // 按 。！？…\n 等边界切句
    speechSynthesis.speak(makeUtterance(sentence))
  }
}
onStreamEnd(msgId, fullText) {            // chat.completed：冲刷残留缓冲（不足一句也强制播）
  flushCompleteSentences()
  if (pending) { speak(pending); pending = '' }
}
// 尾流兜底：网络卡顿后恢复但总差几个字 < 门槛 → 超时强制播剩余，杜绝「尾巴永不读」
尾流定时器(() => {
  if (started && pending && Date.now() - lastDeltaAt > FLUSH_AFTER_MS) {
    flushCompleteSentences()
    if (pending) { speak(pending); pending = '' }
  }
})
onNewUserTurn() { stop() }                // chat.user：新消息打断上一轮
```

> 播放语义：
> - **播放会话一旦开启不中断**：开播后新 delta 持续追加到 `pending` 并切句入队，**不重复触发门槛** → LLM 停顿期间已入队句子照常播完，天然抗抖动。
> - **门槛只约束首次启动**：正文累计 ≥10 字且至少出现一个完整句子才发声，避免「你好，你」这类半截开头。
> - **结束必补全**：`chat.completed` / 尾流超时都会把不足一句的残余强制播出，杜绝「最后几个字永远不读」。
> - 若实测切句停顿明显，可回退为「完整生成后朗读」（保留开关语义，不影响 Phase 1 交付）。
> - 自动朗读默认**关闭**，用户开启后才订阅生效；订阅挂在模块级（`ensureStarted` 同生命周期），切换 tab 不丢失。

### 4.4 手动朗读（气泡按钮）
- `speakOnce(msg)`：取 `msg.content` → `stripForSpeech` → 分段依次入队。
- 交互规则：
  - 该消息正在播放 → 点击停止
  - 其他消息在播放 → 切换至本条（先 stop 再播）
  - 未在播放 → 从头播
- 播放中的按钮切换为「停止」图标并高亮（复用 `speaking` ref 双向绑定）。

---

## 五、Phase 1 实施清单

### 5.1 config.json 模板
- 新增 `voice` 段（见 4.1）。

### 5.2 新增 `src/composables/useTTS.js`
模块级单例，导出：
```javascript
export function useTTS() {
  return {
    ttsState,        // { enabled, autoRead, engine, voiceName, rate, pitch, zhVoices, ready }
    speaking,        // ref<string|null> 当前朗读 msgId
    loadConfig,      // 读取 voice 配置（经 electronAPI.getConfig）
    saveConfig,      // 写 voice 配置
    listZhVoices,    // 枚举中文语音（触发 voiceschanged）
    playMessage,     // 手动：playMessage(msgId, text)：播放/停止/切换
    stop,            // 停止
    testVoice,       // 设置页试听：testVoice(voiceName?, text?)
  }
}
```
- 内部自动订阅：`chat.delta` / `chat.completed` / `chat.user`（autoRead 开启时）。
- Web Speech 封装：`speechSynthesis.speak / cancel / pause / resume`；`utterance.onend / onerror` 清理 `speaking`。
- 流式播放缓冲：`BUFFER_MIN=10` 开播门槛 + `FLUSH_AFTER_MS=1500` 尾流兜底（常量先内置于单例，后续可暴露到设置）。

### 5.3 ChatView.vue
- `.msg-actions` 中、复制按钮左侧新增朗读按钮：
  - 图标：🔊（未播）/ 停止方块（播放中，高亮色）
  - 仅助手消息、非流式且 `m.content` 非空时显示（与复制按钮同条件）
- 绑定 `playMessage(m.id, m.content)`；状态取自 `speaking`。

### 5.4 Settings.vue 新增「语音朗读（TTS）」卡片
| 控件 | 说明 |
|------|------|
| 语音方案下拉 | 「Web Speech API（系统语音 · 无需 GPU）」；预留 disabled 项「本地 TTS（N 卡 8GB+，敬请期待）」 |
| 启用语音朗读 | 复选框 `voice.enabled` |
| AI 自动朗读 | 复选框 `voice.autoRead`（依赖 enabled，未启用时置灰） |
| 中文语音下拉 | 列出系统中文语音（名称 + 是否在线/本地 + 语言），无中文语音时提示“未检测到中文语音，请安装语言包（Win10/11 自带 Huihui/Kangkang/Yaoyao）” |
| 试听按钮 | 朗读固定样例句「喵～本喵就是这么可爱！」 |
| 语速 / 音调 | 滑杆 rate(0.5~2.0, 步进0.1) / pitch(0.5~2.0, 步进0.1) |

- 添加到 `saveAll()` 的 patches 中；`onMounted` 时 `loadConfig` 填充。
- 卡片位置：放在「网络代理」与「闲置提醒」之间。

### 5.5 样式与交互细节
- 朗读按钮沿用 `.action-btn` 风格（30×30 无边框图标按钮，hover 浅底），与复制按钮一致。
- 播放中：图标亮色（如 `#34d399`）且显示停止图标。
- 下拉无中文语音时：显示提示文本 + 系统语音链接（`shell.openExternal` 微软语言包页面，可选）。

---

## 六、Phase 2 初步计划（后续细化确认）

### 6.1 前置能力
- **GPU 检测**：复用 `python/monitor/gpu.py` 的 NVML 数据（vendor=NVIDIA 且 `memTotalGB >= 8`），经 WS `metrics-update` 或新增专用查询接口暴露给前端。
- **模型下载**：复用 `python/agent/rag/model_download.py` 的镜像下载逻辑（不可直连走 hf-mirror），新增 TTS 模型下载入口与状态（写配置 `voice.local.modelDownloaded`）。

### 6.2 候选模型
| 模型 | 优点 | 注意 |
|------|------|------|
| **ChatTTS**（首选验证） | 对话式 TTS，口语自然、情感/停顿丰富，贴合傲娇猫娘 | 开源为研究/非商用协议；显存需求与 8GB 匹配 |
| CosyVoice2 | Apache 2.0，可商用，中文质量高 | 需对照验证 8GB 显存下的速度 |
| GPT-SoVITS | 可克隆音色 | 配置较重，暂缓 |

### 6.3 服务端
- Python 新增 TTS 服务模块（模型懒加载、单例持有）。
- 新增接口：WS 事件或 HTTP `POST /tts`（入参文本/语音/语速等 → 返回音频 base64 或临时文件路径）。
- 音频格式统一 `wav/pcm`，前端 `AudioContext` 或 `<audio>` 播放。

### 6.4 前端接入
- 引擎抽象层新增 `local` 引擎实现（`speak` 内部：请求 → 播放）。
- `voice.engine` 切换联动：设置页语音方案下拉出现第二项；下方「中文语音」改为「音色」相关项（具体待 Phase 2 细化）。

---

## 七、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Web Speech 在 Electron/Windows 初次 `getVoices()` 为空 | 语音列表空白/无法选中 | 监听 `voiceschanged` 再枚举；设置页重试提示 |
| 系统无中文语音包 | 中文朗读失败或怪音 | 回退任意 zh 语音；设置页明确提示安装语言包 |
| Chromium 长文本截断 | 长回复读一半停 | 按句/段切分入队（分段朗读） |
| LLM 网络波动（端到端停顿/零星字词） | 反复开播、断断续续 | 播放缓冲门槛（≥10 字开播）+ 播放会话不中断 + 尾流超时补读 |
| 结束前残余不足一句 | 「最后几个字永不读」 | chat.completed / 尾流超时强制冲刷残余 |
| 流式切句有轻微停顿 | 听感一般 | 缓冲分句播放接受轻微顿挫；可选回退完整后朗读 |
| 自动朗读误伤（工具步骤/中断卡） | 读不相关内容 | 仅订阅正文 `chat.delta`/`chat.completed`，`chat.user` 打断 |
| Phase 2 显存判定不准 | 8GB 临界机上 OOM/卡顿 | 检测叠加“模型显存建议”提示；用户可手动关闭 |
| 播放与复制/停止按钮状态不同步 | UI 错乱 | `speaking` 用模块级 ref，所有视图共享 |

---

## 八、文件结构（Phase 1 变更）

```
config.json                        # 修改：新增 voice 段
src/
├── composables/
│   └── useTTS.js                  # 新增：TTS 引擎单例（Web Speech + 预留 local 接口）
└── views/
    ├── ChatView.vue               # 修改：消息操作条加朗读按钮
    └── Settings.vue               # 修改：新增「语音朗读（TTS）」卡片
```

---

## 九、验收标准

### 9.1 Phase 1
- [ ] 助手消息气泡下出现朗读按钮（复制按钮左侧），流式期间隐藏
- [ ] 点击按钮：未播→播放；播放中→停止；其他消息在播→切换；按钮高亮与停止图标正确
- [ ] 中文播报正常（有中文语音包时），无中文语音时设置页有明确提示
- [ ] 设置页各控件读写 `voice.*` 配置，保存后热生效（无需重启）
- [ ] 「AI 自动朗读」开启后：正文累积 ≥10 字且成句后才开播；开播后 LLM 停顿不打断播放；新用户消息打断上一轮；回复结束（completed / 尾流超时）补齐剩余文字
- [ ] 只朗读最终正文，跳过代码块与 Markdown 符号，不读深度思考
- [ ] 切换 tab 后播放状态不丢失（模块级单例）且可继续停止
- [ ] 语速/音调设置实时生效
- [ ] 语音方案下拉含本地 TTS 占位项（disabled），并注明无需 GPU

### 9.2 Phase 2（后续）
- [ ] N 卡 ≥8GB 检测正确，低于阈值时本地 TTS 选项置灰并提示
- [ ] 模型可一键下载（走镜像），下载状态持久化
- [ ] `engine=local` 时音频生成与播放流畅，与 Phase 1 功能等价
- [ ] 语音方案切换（web-speech ↔ local）UI 联动正确

---

## 十、测试计划（Phase 1）

- **语音枚举**：Windows 有无中文字库两种情形下 `listZhVoices` 结果正确、无不崩溃。
- **文本预处理**：`stripForSpeech` 对（代码块、行内代码、标题、列表、链接、粗斜体、表格）输出正确。
- **分段朗读**：长文本（>2000 字）切句入队不截断、onend 链式播放。
- **流式自动朗读**：开播门槛（<10 字不开播）、开播后 LLM 停顿不打断、尾流超时补读、`onStreamEnd` 补读、`chat.user` 打断竞态（边读边发新消息）、模拟 LLM 断续 token 到达验证无反复开播。
- **状态同步**：`speaking` 与按钮图标/高亮一致；手动停止后无幽灵朗读。
- **配置落盘**：保存→重启应用后设置保留；旧版本升级（无 voice 段）不报错。