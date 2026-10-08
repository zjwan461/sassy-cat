# 流式 Markdown 渲染性能优化方案（分析 + 设计 + 实施记录）

> 目标范围：`src/components/MarkdownRenderer.vue` 在流式输出期间的核心渲染路径。
> 关联文件：`src/composables/useChatStore.js`、`src/views/ChatView.vue`。
> 状态：**P0 + P1 已实施**（见第 11 节实施记录）；P2 / P3 为可选演进，尚未实施。

---

## 1. 问题陈述

现状：`chat.delta` 每来一片增量，`MarkdownRenderer` 都会把**整条消息的累计正文**重新走一遍
`markdown-it` 解析 + 高亮/公式渲染，并用 `v-html` **整块替换** DOM。

表现（用户可感知）：

- 长回复、尤其是**含大代码块**的回复，逐字追加时掉帧、卡顿；
- 已渲染区域被整块重建导致：**文本选区丢失**、代码块/表格/Katex 的**横向滚动位置被重置**（视觉"抖动"）、
  正文中的图片**重新加载闪烁**；
- 自动跟随滚动与内容增长**不同帧**，最后一行会短暂被挤出视口再回弹。

---

## 2. 现状链路（每帧到底做了什么）

### 2.1 数据侧（`useChatStore.js`）

| 事件 | 代码位置 | 行为 |
|---|---|---|
| `chat.delta` | `useChatStore.js:220-237` | `m.content += p.text`；同时把增量按来源追加进 `m.segments`（同 agent 则 `last.text += p.text`） |
| `agent.reasoning` | `:238-250` | `m.reasoning += text`，并置 `thinking/reasoningOpen` |
| `agent.tool_args` | `:307-315` | 对活动工具步骤 `active.args = prettyArgs(...)`，**每个增量都 JSON.stringify/parse 一次全量参数** |

存储层本身是 O(Δ) 的追加，问题不在这里；但它构成了下游渲染的触发源。

### 2.2 视图侧

`ChatView.vue` 用 `MarkdownRenderer` 渲染 `m.content` 或逐个 `seg.text`
（`ChatView.vue:129 / 132 / 135`），并有一个"全量 reduce"监听：

```js
// ChatView.vue:562-574
watch(() => messages.value.reduce(
  (n, m) => n + (m.content?.length || 0) + (m.reasoning?.length || 0) + toolArgsLength(m), 0
), () => { scrollBottom(); nextTick(() => { followReasoning(); followToolArgs() }) })
```

### 2.3 渲染侧（`MarkdownRenderer.vue`）

```
props.content 变化
  └─ watch([content, done], scheduleRender, { flush:'post' })   // :183
       └─ scheduleRender()                                      // :160-166
            └─ doRender()                                       // :167-181
                 ├─ html.value = md.render(props.content)        // ⚠️ 全量重解析
                 │    └─ 每个 fence → highlight(code, lang)
                 │         └─ 未知语言走 hljs.highlightAuto()   // ⚠️ 最重的一处
                 │    └─ texmath → katex.renderToString(...)     // ⚠️ 每个公式重建
                 └─ nextTick(() => props.done && renderMermaidBlocks())
       └─ v-html="html"  → 整个子树 DOM 销毁重建                 // ⚠️ 选区/滚动/图片全丢
```

---

## 3. 瓶颈清单（按代价排序）

### P-1：`hljs.highlightAuto`（最严重的单点）
`MarkdownRenderer.vue:44-53`：语言未知时调用 `highlightAuto(code)`。`highlightAuto` 会依次尝试内置
~180 条语法并打分选取最优，代价约 O(n × G)。流式期间**语言标签往往还没出现**（首行 ``` 之后才写 `python`），
且代码块未闭合时**整块内容每帧重算**，叠加成 O(n² × G)。这是"带代码块就卡"的头号原因。

### P-2：全文重复解析 + 整块 DOM 替换 ⇒ O(n²) 与交互状态丢失
- `md.render(fullContent)` 每帧 O(n)，一段 10 KB 的回复累计约 O(n²)；
- `v-html` 换掉整棵子树：已完成块的横向滚动（`.md-code pre`、`.md-table-wrap`、`.katex-display`）归零、
  文本选区清空、`<img>` 重建触发重新加载 —— 全部集中在"已定稿、本不该再动"的区域。

### P-3：KaTeX 每帧重建
`texmath` 把每个公式渲染成大量 DOM 节点；每帧重跑一遍，成本高且会引起整行重排。
流式期间"未闭合的 `$`/`$$`"还会造成公式区在"字面量 ↔ 公式"之间来回跳。

### P-4：渲染节奏与滚动跟随错位
- `scheduleRender` 首次调用**同步**在 watcher 的 post flush 里渲染（`rafId === null` 分支），
  并未对齐帧；只有后续增量才被"每帧最多一次"合并 —— 节流行为不一致；
- `scrollBottom()` 在 `nextTick` 里执行，而真正的内容增长发生在**之后**的 rAF 渲染中
  （`doRender` 的 `html.value` 更新），于是"先滚到底 → 内容再长高"，出现未贴底的瞬间；
  同时 `onMsgListScroll` 会因程序化滚动把 `stickToBottom` 重算一次，边界场景会误判。
- 列表容器没有 `overflow-anchor` 策略，浏览器滚动锚定会额外调整 `scrollTop`。

### P-5：异常兜底把"局部"升级为"全局"
`doRender` 的 `catch` 会把 `html.value` 退化成 `escapeHtml(整段内容)`（`:169-173`）。
一旦 texmath / 高亮在某个字符上抛错，整条消息会瞬间变成纯文本 —— 破坏性远大于收益。

### P-6：疑似实现缺陷（需核对源码字节）
`MarkdownRenderer.vue:36-38` 的 `escapeHtml` 若确实是
`.replace(/&/g, '&').replace(/</g, '<')...`（把实体原样写回而非转义），则该函数实际是恒等变换。
它在文本节点里"碰巧能用"，但一旦用于属性就存在注入风险。**需先核对源文件真实字节**再决定修法。

### P-7：反应式触发面（次要，待 profiling 判定）
每个 delta 都会让 `messages` 的 reduce watcher 与 `ChatView` 模板中读取 `m.content` 的表达式失效，
父组件 render 函数每 delta 重跑一次（O(#messages)，props 相等时子组件 update 会被跳过）。
消息数不多时不是主因，但长会话下值得收敛（见 P3 可选方案）。

---

## 4. 设计目标与硬约束

**目标**
1. 单次增量的渲染成本与**消息总长度无关**，只与"仍可能变化的尾部"相关（O(Δ + tail)）。
2. 已定稿区域**永不重建**：滚动位置、选区、图片加载状态全保留。
3. 完成后（`done`）的最终 DOM 与"一次性整段渲染"**完全一致**（可作为强验收契约）。

**约束**
- 不改变 `useChatStore` 的事件语义与消息数据结构（保持多会话后台累积、按 msgId 归位等既有行为）。
- 不引入重量级依赖（不引入虚拟 DOM diff 库 / 不重写 markdown 管线）。
- 必须兼容：`dollars` 数学定界符、`breaks:true`、`linkify:true`、Mermaid 延迟渲染、子 agent `segments` 分段、TTS 增量。

---

## 5. 方案设计

### 5.1 总体思路：稳定前缀 + 活动尾部

把一条流式正文切成两段：

```
content = ── 稳定前缀（stable） ──┊── 活动尾部（live） ──
                                   ↑
                          最后一个「块安全」分界点
```

- **stable 区**：HTML 片段**只追加、不重写**（`insertAdjacentHTML('beforeend', chunkHtml)`）。
  每个块只在"定稿那一刻"渲染一次 ⇒ 全生命周期 O(n)，且已有 DOM 节点身份不变。
- **live 区**：只渲染 `content.slice(boundary)`（通常是最后一个段落 / 未闭合代码块），可用 `v-html` 覆盖。
  它随分界点前移而"搬家"到 stable：搬家时把 `[上次 boundary, 新 boundary)` 作为**完整块集合**渲染成 HTML 追加到 stable。

一次 `chat.delta` 的完整序列：

```
delta 到达 → ① 增量扫描（只扫新增片段，O(Δ)）更新状态机 & 候选分界点
           → ② 若产生新分界点：renderChunk(stable 未提交段) → stable.appendHtml(...) → 清空 live
           → ③ render(tail) → live.v-html 覆盖（tail 通常只有几百字符）
           → ④ emit('rendered') → 视图层在"渲染完成之后"做贴底跟随
```

### 5.2 分界点扫描：追加式 + 单调状态机（关键不变量）

`content` 只做**追加**，因此"某位置是否为块安全分界点"只依赖其**前缀**，判定不可逆：

> **不变量**：候选分界点集合随内容增长**单调增加**，永不失效 ⇒ 无需滞后（hysteresis），不会抖动。

扫描器（`StreamSplitter`）持有持久游标，**每帧只处理新增 suffix**：

```js
// 概念实现
state = { pos: 0, fence: null,   // 未闭合围栏的标记串（``` / ~~~）与长度
          math: false,            // 是否处于 $$...$$ 块中
          candidates: [],         // 块安全分界点（= 源码下标，指向块起始）
          committed: 0 }          // 已提交到 stable 的下标
feed(suffix)  // 只扫 suffix，边扫边推进 pos / fence / math，收集候选
```

判定"块安全分界点"的条件（空行位置 `i`，即 `\n\n` 之后为块起始）：

1. `fence === null && !math`（不在围栏/`$$` 块内）；
2. `i` 不是**未闭合结构**的中间点 —— 由 1 保证；
3. **列表/引用续接保护**：若 `content[i]` 之后的行以列表标记（`-`/`*`/`+`/`\d+.`）或 `>` 开头，
   且 `boundary` 前一个块也属于同类容器，则**回退到上一候选点**（宁可少切，不可切坏）。

> 说明：`\n\n` 在 markdown 语义里是"松列表/紧列表"的分界（`- a\n\n- b` 整体是一个 loose list），
> 按空行切分会渲染成两个 tight list，**间距略有差异**。这正是需要第 3 条保护 + 5.4 完成时全量对齐的原因。

### 5.3 分工与 CSS 影响

`MarkdownRenderer.vue` 模板改为两个容器：

```html
<div class="markdown-body" ref="rootRef" @click="onClick">
  <div class="md-stable" ref="stableRef"></div>   <!-- 只追加 -->
  <div class="md-live" v-show="liveHtml" v-html="liveHtml"></div> <!-- 尾段，整体覆盖 -->
</div>
```

CSS 连带处理（`.markdown-body` 是非 scoped 的，改动需谨慎）：

- 现有 `.markdown-body > *:first-child { margin-top: 0 }` 会作用到新的容器 `div` 上而失效，
  需改为 `.md-stable > :first-child { margin-top: 0 }` / `.md-live > :last-child { margin-bottom: 0 }`；
- **外边距折叠可保留**：两个容器都是无 padding/border 的普通 div，子元素 margin 会透过容器边界折叠，
  因此相邻块间距与单容器渲染一致（需在验收里做像素级比对）；
- `.md-live` 为空时必须真正不占高度（`v-show` + 空串源码，避免 `v-html` 产生空白文本节点撑出一行）。

### 5.4 完成时全量对齐（强契约，强烈建议保留）

`props.done` 变为 `true` 时：**丢弃分块结果，用整段源码一次性渲染并替换**（此时不再有性能压力）。

好处：
- 彻底消除一切分块语义偏差（loose list、跨块引用式链接 `[x][1]`、表格续行等）；
- 与 Mermaid 的"完成后才渲染"路径天然合并（现状 `fence` 规则在 `done` 时才输出 `.md-mermaid`，本就需要一次全量重渲）；
- 给出一份可回归的验收标准：`done` 后的 DOM 必须等于 `md.render(fullContent)`。

### 5.5 未闭合代码块：DOM 原地追加

"尾部 = 单个未闭合 fence"是最坏路径（tail 可能上千字符）。此时不做 `v-html` 覆盖，而是：

```js
// tail 已是「未闭合 fence」形态：只把新增文本追加到既有节点
codeEl.appendChild(document.createTextNode(deltaText))
```

- 成本 O(Δ)，`<pre>` 元素身份不变 ⇒ **横向滚动位置与选区都不再丢失**；
- 流式期间该块以纯转义文本展示（`data-streaming="1"`），**定稿时再高亮一次**（与 5.1 的搬家动作天然一致）。

### 5.6 渲染节奏与滚动跟随（P-4 修复）

- `scheduleRender` 统一走 `rAF`（首帧也走），并对齐最小间隔（建议 40–60 ms）：
  文本追加在 15–20 fps 下已足够顺滑，能直接砍掉大量无效渲染；
- `document.hidden` 时**只累积不渲染**，`visibilitychange` 回到前台做一次补渲染（store 侧数据不丢，无副作用）；
- 把"内容变化 → 贴底"从"全量 reduce watcher + nextTick"改为**渲染完成信号**：
  `MarkdownRenderer` 渲染完毕 `emit('rendered')`（或视图层用 `watch(..., {flush:'post'})` + 双 rAF），
  贴底动作排在渲染之后；
- 贴底实现建议改为**底部哨兵**（列表末尾放 1px 锚点，`stickToBottom` 时 `anchor.scrollIntoView()`），
  并对 `.msg-list` 设 `overflow-anchor: none`，消除浏览器滚动锚定带来的二次位移；
- `stickToBottom` 只在**用户主动滚动**时更新（wheel/touch/keydown），程序化滚动不改写状态。

---

## 6. 分层落地（建议顺序）

### P0 — 快速止血（低风险，独立可发布）
1. **去掉 `highlightAuto`**：`lang` 命中白名单才 `hljs.highlight`，否则 `escapeHtml`。
   （可只注册 agent 常用语法：`python/js/ts/json/bash/html/css/sql/yaml/markdown`）
2. **流式期间不高亮**：live 区/未闭合 fence 一律纯转义，定稿后再高亮。
3. 渲染调度统一 rAF + 最小间隔；`document.hidden` 时跳过渲染。
4. 贴底动作移到渲染之后（哨兵 + `overflow-anchor: none`）。
5. 兜底降级范围收窄（仅在**当前待渲染片段**上退化，不再整条消息变纯文本）。
6. 核对并修正 `escapeHtml` 的真实转义行为（P-6）。

> 预期：单点消除最重的 CPU 尖峰；代码块/长回复卡顿显著缓解。**不解决**"整块 DOM 重建导致滚动/选区丢失"。

### P1 — 稳定前缀增量渲染（核心收益，5.1–5.5）
- 新增 `StreamSplitter`（追加式扫描状态机 + 列表续接保护）；
- `MarkdownRenderer` 改双容器，stable 只追加、live 只覆盖；
- 未闭合代码块走 DOM 原地追加；
- `done` 全量对齐契约。

> 预期：单帧成本与消息总长解耦；已定稿区域不再被重建，选区/滚动/图片稳定。

### P2 — 块级 DOM 原地更新（可选，进一步收敛）
把 live 区升级为"顶层块列表 + 逐块 diff"：块源码串相同则复用节点，仅最后一个变化的块做
`innerHTML` 原位更新（`<pre>` 场景下更新 `code` 的文本节点，可保住 `pre` 的 `scrollLeft`）。
代价：需要一层轻量块 hash 与节点 key 管理；收益在"长段落/长表格持续增长"的场景才明显。

### P3 — 反应式触发面收敛（可选，视 profiling）
让 `MarkdownRenderer` 直接订阅 store（传 `msgId` + getter）而非接收 `content` prop，
这样 narrow 到"只有渲染器本身"被失效，父组件 render / 消息列表 patch 每 delta 不再重跑。
需权衡：会略微破坏"纯 props 组件"的简洁性，建议先用 DevTools 量化父组件 patch 占比再决定。

---

## 7. 备选方案与取舍

| 方案 | 做法 | 优点 | 缺点 / 风险 | 结论 |
|---|---|---|---|---|
| A. 稳定前缀双容器 | 本文 5.1 | 改动集中在一个组件；成本 O(Δ+tail)；语义偏差可用 `done` 全量对齐兜住 | 需处理列表续接、CSS margin 折叠 | **推荐** |
| B. 块列表 + 逐块 diff | 本文 5.2(块级) | 不变量更强，能保住尾块滚动/选区 | 实现复杂度高，收益边际 | 作为 P2 演进 |
| C. 虚拟滚动只渲染可视消息 | 列表层虚拟化 | 顺带解决长会话 | 不解决"单条消息内部 O(n²)"；改动面大（`ChatView` 滚动逻辑耦合） | 与本主题正交，另行立项 |
| D. 降到 Web Worker 渲染 | 主线程外解析 | 主线程完全不受影响 | 需传回 HTML 仍要写 DOM；katex/hljs 需在 worker 内；复杂度极高 | 不推荐 |
| E. 用 `content-visibility`/`contain` 等 CSS 手段 | 纯 CSS | 零风险 | 只缓解布局/绘制，解析与 DOM 重建照旧 | 可作为配套微优化 |

---

## 8. 度量与验收

**基线（建议先测）**
构造固定语料并回放：~10 KB 正文 + 3 KB Python 代码块 + 8 个公式 + 2 张表格 + 1 个 mermaid，
按 30 次/秒 逐字符喂入，采集：

- `md.render` 单次耗时（P50/P95）、单帧 JS 总时长、长任务（>50 ms）计数、FPS；
- 交互指标：已定稿代码块的 `scrollLeft` 是否被重置、文档选区是否在流式中丢失、
  `scrollHeight - scrollTop - clientHeight` 是否始终稳定（贴底不抖）。

**验收标准**
1. 单次增量渲染耗时 **不随消息长度增长**（同一语料从 2 KB 增长到 20 KB，P95 基本持平）；
2. 流式全程 **0 个 >50 ms 长任务**；
3. 已定稿区域：`scrollLeft` 不变、图片不重载、选区保留；
4. `done` 后的 DOM **等价于** `md.render(fullContent)`（归一化空白后比对）；
5. TTS、Mermaid、中断确认卡、工具参数跟随、历史回填消息渲染均无回归。

**可测性改造（建议）**
- 给根节点加 `data-render-mode="full|incremental"` 便于调试；
- 把 `StreamSplitter` 抽成纯函数模块（不依赖 Vue），配一组语料单测：
  「分界点必须落在块边界」+「分块渲染结果在 `done` 时与整段一致」。

---

## 9. 实施步骤（实施阶段执行，本轮不做）

1. **P0**：高亮降级 → 调度改造 → 贴底改造 → 兜底收窄 → `escapeHtml` 核实修正；用第 8 节基线复测。
2. **P1-a**：抽 `StreamSplitter`（纯逻辑）并补单测；在 `MarkdownRenderer` 内接入，加 `data-render-mode` 便于回滚比对。
3. **P1-b**：双容器 + stable 追加 + live 覆盖 + 未闭合 fence 原地追加。
4. **P1-c**：`done` 全量对齐契约 + Mermaid 合并路径。
5. **P2/P3**：按 8 节的 profiling 结果决定是否推进。
6. 回归清单见第 8.4 条；每步都可 `git revert` 单点回滚（P0/P1 解耦，互不依赖）。

---

## 10. 需你决策/确认的点

1. **UX 取舍**：流式期间未闭合代码块**不高亮**（定稿瞬间补高亮），是否接受？
   （不接受的替代方案：仍用 `hljs.highlight` 但**限定语言白名单**，只是保留每帧重算成本。）
2. 是否接受 `done` 时"整段重渲一次"带来的**极小视觉重排**（现状 Mermaid 已是此行为）？
3. 是否允许在 `MarkdownRenderer` 内新增两个容器 `div` 并调整 `.markdown-body` 的非 scoped CSS 选择器？
4. P-6（`escapeHtml`）需要我核对源文件真实字节后给出结论吗？
5. 是否需要我把第 8 节的性能基线脚本（合成增量回放）一并设计出来，便于实施前后对比？

---

## 11. 实施记录（P0 + P1 已落地）

### 11.1 改动清单

- `src/utils/streamSplitter.js`（新增）：追加式分块扫描器。持久游标 + 单调状态机，`feed()` 只扫新增片段（O(Δ)）；候选分界点在空行处立即记录，采纳前再做"列表/引用 loose 容器""缩进式代码块""是否接收完整"三项审定。
- `src/components/MarkdownRenderer.vue`：双容器（`.md-stable` 只追加 / `.md-live` 覆盖尾部）；未闭合代码块走 DOM 原地追加文本节点；rAF + 最小间隔节流；页面隐藏时只累积不渲染；`done` 时整段重渲并 `emit('rendered')`；高亮白名单化（去掉 `highlightAuto`）；`escapeHtml` 改为复用 markdown-it 自带实现。
- `src/views/ChatView.vue`：三处 `MarkdownRenderer` 接 `@rendered`，贴底改由"渲染完成"驱动（同帧内、绘制前）；`.msg-list` 加 `overflow-anchor: none`；用 `expectedScrollTop` 识别程序化滚动，避免自动贴底吞掉用户上翻意图。
- `tests/stream_splitter.test.mjs`（新增）：扫描器行为测试，26 项断言。
- `tests/incremental_render_equivalence.test.mjs`（新增）：等价性测试，43 项断言。语料覆盖普通段落、围栏代码块（含空行）、未闭合围栏、紧/松列表、有序列表 + 引用、表格、缩进式代码块、块级数学、混合长文，喂入粒度 step=3 与 step=17。

### 11.2 验证方式与结果

```
node --experimental-default-type=module tests/stream_splitter.test.mjs
node --experimental-default-type=module tests/incremental_render_equivalence.test.mjs
npx vite build
```

当前结果：26 + 43 项断言全部通过；`vite build` 成功（2832 modules，无新增告警）；另已运行时校验 `md.utils.escapeHtml` 存在且转义正确。

### 11.3 实施过程中发现并修复的缺陷

1. `escapeHtml` 实际是恒等变换（把实体原样写回），未高亮的代码块里出现 `<script>` 等会被当作真实 HTML 注入 —— 改为复用 markdown-it 自带实现，顺带避免手写实体表。
2. 首次渲染绕过 rAF：原 `scheduleRender` 首次同步渲染、后续才走 rAF，节流行为不一致 —— 统一为 rAF + 最小间隔，且隐藏页只累积不渲染。
3. 分界点生成过晚：候选点原先要等"下一行收到换行"才产生，段落文本迟迟无法定稿 —— 改为空行一处立即记录。
4. 采纳过早（测试捕获）：分界点恰落在源码末尾时会基于"未知内容"直接采纳，可能把 loose 列表切成两个紧列表 —— 改为落点后至少 1 个字符才判定。
5. 基于不完整行的误判（等价性测试捕获）：缩进式代码块 `    code` 只收到 2 个空格时被判为普通段落，一个 `<pre>` 被切成两个 —— 引入 `defer`（延后判定）语义，并利用"内容只追加、行前缀不可改写"精确框定不确定范围，同时补入缩进式代码块保护。

> 注：写入工具链会把 diff 里的 HTML 实体序列解码成对应字符，因此不要靠手写实体来构造转义字符串 —— 直接用现成实现（本次即改为 `md.utils.escapeHtml`）。

### 11.4 尚未覆盖 / 已知取舍

- 流式期间未闭合代码块不做语法高亮（定稿瞬间补高亮）；已定稿的分块会即时高亮一次（全生命周期 O(n)）。
- 跨块引用式链接（`[x][1]`）在流式期间可能不解析，`done` 后正确（已注释说明）。
- `done` 时会整段重渲一次（与 Mermaid 的"完成才画图"路径天然合并），有极小重排。
- 尾部异常长（模型长时间不输出空行，整段是一个超长段落）时渲染间隔自动放宽到 200 ms，仍是 O(尾长)/帧 的退化路径。
- live 区（当前尾部）仍会被整块覆盖，其内部选区会丢失；stable 区已完全不受影响。
- P2（块级 DOM diff）、P3（渲染器改为自订阅 store，收窄父组件重渲染）未实施，视 profiling 结论再定。

### 11.5 待人工验证（需真实窗口）

滚动跟随是否仍有抖动、代码块横向滚动位置在流式期间是否稳定、Mermaid 定稿渲染、TTS 增量朗读、中断确认卡、工具参数区自动跟随、历史回填消息渲染、多会话切换后台累积。