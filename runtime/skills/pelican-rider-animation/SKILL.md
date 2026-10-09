---
name: pelican-rider-animation
description: >
  生成"动物骑自行车/交通工具"的 2D 单文件 HTML 动画（SVG 或 Canvas），并用
  无头冒烟测试 + 运动学几何校验 + 渲染层截图在交付前自证无误。触发场景：用户要求"画一个鹈鹕骑自行车的动画"、"pelican riding a
  bicycle"、"pelican on a bicycle"、pelican benchmark，或任何生物骑乘类 2D
  动画（SVG/Canvas/HTML）需求，尤其是要求"验证过""能跑起来"而非仅仅生成代码时。Use when the user asks
  for a pelican riding a bicycle, or any 2D animated HTML of an animal
  riding a vehicle, especially when they want it verified rather than just
  generated.
---

# 生物骑乘类 2D 动画 · 生成与自证

## 这个技能解决什么

「鹈鹕骑自行车」是 Simon Willison 的 LLM 基准提示词，原始形式为
`Generate an SVG of a pelican riding a bicycle`。它之所以能测推理能力，是因为同时考察两件事：

1. **空间关系推理** —— 车有轮子、车架、曲柄；鸟必须坐在座垫上、翅尖搭在把上、脚踩在踏板上，要素间相对位置要自洽。
2. **生物解剖还原** —— 鹈鹕的标志是又长又直的喙 + 下方巨大的喉囊。画成鸭子或海鸥即为失败。

**更关键：这不是一次生成任务，而是"生成 + 验证"任务。** 失败产出大多不是风格差，而是硬伤。因此本技能的核心不是画法，而是**先算几何、再动笔，画完必须跑无头验证**。

---

## 交付前必过的四道关（本技能的核心价值）

| 关卡 | 手段 | 抓什么 | 覆盖 |
|---|---|---|---|
| 1 结构完整性 | 扫一遍代码 | 括号不配对、漏闭合标签、`<script>` 块缺失 | 语法层面 |
| 2 运行时 | `scripts/smoke_test.py` | ReferenceError、undefined、**NaN 坐标（Canvas 与 SVG/DOM 属性两条路径）**、**图层 id 拼错导致静默少一层**、rAF 断链、交互崩溃 | 逻辑层面 |
| 3 几何 | `scripts/check_rig_geometry.py` | 腿被拉直/脱臼、膝盖打结、踏板穿车轮、脚穿地；**支持多腿分别校验** | 数学层面 |
| 4 渲染 | `scripts/screenshot.py` | 真实渲染是否出画面、是否随时间推进（卡第一帧/白屏）；**看得见"缺一条腿""少一层"这类前两关抓不到的问题** | 视觉层面 |

**四关没跑完，不要对用户说"做好了"。** 未经验证的动画等于没做。

关于第 1 关：曾把 `node --check` 列在这里，但它只查语法 —— 而本技能的产物是
**内联在 HTML 里的 `<script>`**，`node --check` 对它能跑通的脚本几乎不会报错（实测：故意注入除零、
拼错图层 id、髋坐标写成 `0/0` 三个缺陷，全部通过）。所以第 1 关降级为"自己扫一眼结构"，真正的把关交给第 2 关。

**第 4 关是可选但强烈建议**：本机没有 Chromium 系浏览器时会自动跳过（退出码 0，不阻断交付）。
见 Phase 4。

---

## 两条技术路线：先问用户要哪种

**用户的措辞决定路线，不要自作主张。** 提示词里说 "SVG" 就写 SVG；说 "Canvas" 或没指定才可自行选型。

| | Canvas 2D 路线 | SVG 路线 |
|---|---|---|
| 适用 | 大量粒子/渐变/逐像素效果；图层多、需要频繁重绘 | 提示词明确要求 SVG；图形简单、矢量感强；想用 CSS 做图层动画 |
| 绘制 | `ctx.*` | `setAttribute` 改 `<line>/<path>/<g transform>` |
| 动画循环 | 每帧整体重绘 | 每帧只改属性（性能好，SVG 元素常驻） |
| 本技能的各关 | 四关全适用 | 四关全适用（第 2 关已专门适配，见下） |

### ⚠️ SVG 路线专项注意（血泪教训）

SVG 路线有一类**静默失败**：代码不报错、冒烟测试全绿、但画面是空的或缺件。原因和防线如下：

1. **属性里的 NaN 不会抛异常。** `g.setAttribute('transform', 'rotate(NaN 382 368)')` 浏览器照单全收，
   只是那个元素（连同子树）不渲染。分母写错一次，整个轮组就消失了。
   → 本技能的 `smoke_test.py` 已对 `setAttribute` / `setAttributeNS` 做三层检查：
   数值型入参非有限值、字符串入参含 `NaN`/`Infinity` 字面量。**这是早期版本最大的盲区，已修。**
2. **`getElementById` 拼错 id 不会报错**，返回 `null`，于是 `null.setAttribute` 才炸 —— 但如果你用了
   `const el = document.getElementById(id); if (el) {...}` 或可选链，就是**静默少一层**。
   → `smoke_test.py` 会收集脚本请求过的所有 id，与 HTML 里静态声明的 id 比对，多出来的即判失败。
3. **`<g transform="rotate(a cx cy)">` 的旋转中心必须显式给。** 只写 `rotate(a)` 会绕原点转，
   车轮会飞到画布外。所有旋转都要写全 `rotate(angle, cx, cy)`。
4. **`viewBox` 与 `preserveAspectRatio` 要配套。** 只设 `width/height` 不设 `viewBox`，缩放时画面会被裁切。
   推荐 `<svg viewBox="0 0 900 460" preserveAspectRatio="xMidYMid meet">`。
5. **`<line>` 的 `x1/y1/x2/y2` 是四个独立属性**，写 NaN 时只有那一条线消失（不像 canvas 整帧重绘），
   所以"少一条腿"这种 bug 在 SVG 里特别隐蔽 —— 必须靠第 2、4 关。
6. **文字/emoji 不要用来拼部件**，跨平台渲染差异大，且无法参与几何校验。

---

## 工作流

### Phase 0 · 先定几何，再画（顺序不能反）

不要边画边凑坐标，那必然导致腿够不着踏板、车架构件错位。先在 JS 顶部写一段**具名几何常量**，绘制全部引用它：

```js
/* ---- 世界几何（像素）---- */
const GROUND = 430;                            // 轮胎触地线
const R      = 62;                             // 车轮半径
const BBX = 470, BBY = 381;                    // 五通（中轴）
const RHUB = {x: BBX - 88,  y: GROUND - R};    // 后花鼓
const FHUB = {x: BBX + 122, y: GROUND - R};    // 前花鼓
const SEAT = {x: 404, y: 295};
const HIP_N = {x: 400, y: 286};                // 近侧髋（腿根）—— 决定腿能否够到踏板
const HIP_F = {x: 394, y: 291};                // 远侧髋：为做透视层次**故意偏移**
const HT   = {x: 566, y: 306};                 // 头管上端
const HB   = {x: 578, y: 344};                 // 头管下端
const GRIP = {x: 614, y: 290};                 // 把套（翅尖抓住处）
const CRANK_R = 30;                            // 曲柄长
const THIGH = 78, SHIN = 74;                   // 腿骨长
```

**几何自检口诀**：每条腿的 `HIP` 到五通的距离应约为 `THIGH + SHIN` 的 0.6~0.9 倍。太远则腿绷直，太近则膝盖折不动。用 Phase 3 的脚本量化，不要靠眼睛判断。

> **近侧/远侧两条腿一定要各传一次。** 远侧髋为了透视通常和近侧不同坐标，
> 早期版本的校验脚本只接受单个 `--hip`，等于**只验了一条腿**，另一条靠运气
> （实测：近侧髋 (400,286) 全绿，但若把远侧髋放到 (360,210) 就会 3600/3600 个
> 曲柄角全部越界、膝角全程 180° 绷直 —— 而旧脚本完全看不到）。现已支持多腿。

### Phase 1 · 写单文件 HTML

- 单文件、零外部依赖、双击即看。
- 结构：`<canvas>` 或 `<svg>` + 一个 `requestAnimationFrame` 循环 + `dt` 累积。
- 输出写到虚拟环境的 `/code/` 下。**先 `ls /code` 看有无同名旧文件，有则换名，不要覆盖用户已有成果。**

#### 车轮（两条路线通用）

辐条用循环画，转速必须由位移反推，而非独立计时器：

```js
wheelAngle = dist / R;   // 正确：纯滚动，视觉不打滑
// wheelAngle = t * 5;   // 错误：加速时与路面滚动脱节
```

#### 腿部 IK（本技能技术核心）

脚固定在踏板圆上，用双骨反解膝盖。不要用两条独立旋转的矩形假装腿——踏板到前后极点时会明显穿帮。

```js
function solveKnee(hip, foot, l1, l2, bendSign) {
  const dx = foot.x - hip.x, dy = foot.y - hip.y;
  let d = Math.hypot(dx, dy);
  d = Math.min(d, l1 + l2 - 0.01);              // 夹住，防 acos 出 NaN/直线腿
  d = Math.max(d, Math.abs(l1 - l2) + 0.01);
  const base = Math.atan2(dy, dx);
  const cosA = (d * d + l1 * l1 - l2 * l2) / (2 * d * l1);
  const a = Math.acos(Math.max(-1, Math.min(1, cosA)));
  return { x: hip.x + l1 * Math.cos(base + a * bendSign),
           y: hip.y + l1 * Math.sin(base + a * bendSign) };
}
```

膝角全程应保持在 **70°~155°**；接近 180° 即腿绷直，视觉僵硬。

#### 鹈鹕本体

- 身体：白/米白椭圆，下缘加内阴影暗示体积
- **脖子用贝塞尔做 S 形**（canvas `bezierCurveTo` / SVG `<path d="M...C...">`），鹈鹕是长颈水鸟，不能是圆柱
- **喙要长、直、微微下钩**，亮橙/沙黄，长度接近头长
- **喉囊挂在喙下方**，比喙更深更饱和的橙色，做出"袋口敞开、底部饱满"——**这是鹈鹕的身份证，缺了它这图就不是鹈鹕**
- 眼睛：小圆 + 高光点，位于喙根稍后方
- 翅：搭在把套那侧不必画清腿，让翅尖自然遮住，省掉一堆穿模问题

#### 视差滚动

所有背景层速度都从 `dist` 派生，倍率递变：远山 0.05 → 树林 0.35 → 近林 0.7 → 路边草 0.95 → 路面 1.0 → 镜头前失焦草 1.8。加速时各层自然拉开，比固定时长的 CSS 动画真实得多。

> SVG 路线的图层用 `<g id="layerHills">` 之类分组，脚本里 `getElementById` 取引用后每帧只改 `transform`。
> **id 命名要和 HTML 里完全一致 —— 第 2 关会检查这个。**

### Phase 2 · 无头冒烟测试（必做）

```bash
python scripts/smoke_test.py /code/你的文件.html
# 需要自定义按键/交互时：
python scripts/smoke_test.py /code/你的文件.html --extra-js /tmp/drive.js
```

它用桩 DOM + 桩 Canvas 把 `<script>` 真跑起来，自动走完 11 个阶段（静置、冲刺、松开、暂停、恢复、重置、resize、大 dt、非整数 dt、长时静置），并检查：

- 有没有异常、rAF 有没有断链；
- **非有限数值（NaN/Infinity）计数** —— Canvas 调用参数 **和** `setAttribute` 参数两条路径合并统计，且会抓字符串里的 `NaN`/`Infinity` 字面量（SVG 的 `transform="rotate(NaN ...)"` 就靠这个）；
- **id 完整性** —— 脚本 `getElementById` 请求过的 id，是否都在 HTML 里静态声明过。

- 退出码 0 = 通过。出现 `❌` 必须回去修，不许带错误交付。
- **若报"没找到 `<script>` 块"**：说明写成了纯 CSS 动画页。这意味着第 2、3 关全部失效、第 4 关只能证明"有画面"，
  是四关里最弱的一种形态。**要么改成 JS 驱动（推荐），要么在汇报里明确告知用户"此页为纯 CSS 动画，未做运行时与几何验证"。**
- 脚本需 `node` 在 PATH 中；找不到会明确报错，不会假装通过。

### Phase 3 · 几何校验（骑乘类必做）

```bash
python scripts/check_rig_geometry.py \
    --bb 470 381 \
    --hip 400 286 --hip 394 291 \
    --hip-label 近侧腿 --hip-label 远侧腿 \
    --crank 30 --thigh 78 --shin 74 \
    --rear-hub 382 368 --front-hub 592 368 --wheel-r 62 --ground 430
```

- **`--hip` 可重复传参**，每条腿出一份独立报告并分别判红；`--hip-label` 按顺序给名字（可选）。
  只传一条腿时，结尾会提示"另一条腿没有被校验"。
- 不带任何参数时用 Phase 0 那套默认几何（`--hip 400 286`，向后兼容旧写法）。
- 它按 0.1° 步长扫 3600 个曲柄角，输出踏板→髋距离 min/avg/max（对比腿总长）、膝内角范围、
  四类硬性违规计数（越出可达范围 / 折叠空间不足 / 插入车轮圆 / 穿到地面下），以及最大膝角是否超 172°（僵硬警告）。

**任何 ❌ 都要改几何重跑，不要靠"看起来还行"蒙过去。**

### Phase 4 · 渲染层截图（可选，能跑就跑）

```bash
python scripts/screenshot.py /code/你的文件.html
# 常用可选项：
python scripts/screenshot.py /code/你的文件.html --width 900 --height 460 --outdir /tmp/shots
python scripts/screenshot.py /code/你的文件.html --times 200 1300 5200   # 多时间点
```

- **不写死浏览器路径**：按 环境变量（`PELICAN_BROWSER` / `CHROME_PATH` / `PUPPETEER_EXECUTABLE_PATH` / `BROWSER`）
  → PATH 可执行名 → 各平台常见安装位置（Windows / macOS / Linux）三层探测。这样技能换台电脑也能跑。
- **找不到浏览器就优雅跳过（退出码 0）**，并打印如何指定，不阻断交付。
- 默认在 3 个时间点各截一帧，**若三帧字节完全一致即判失败** —— 说明画面卡在第一帧或整页空白。
  时间点默认 `200/1300/5200` ms 且刻意拉开跨度：循环动画有车轮周期相位，两个恰好相差整数圈的时间点会撞车（实测 300ms/1800ms 就撞了）。
- **截图通过 ≠ 画得像。** 它只能证明"渲染出来了、且在动"。**务必亲自看一眼图**（或用 read_file 读图）确认要素齐全：
  两个轮子有辐条 / 鸟坐在座垫上 / 长喙 + 喉囊 / 翅尖搭把套。
- 实测有效性：`dist / R` 改成 `dist / (R - 62)`（全坐标 NaN）后，**第 2 关会报 1272 次 NaN 并失败**，
  而第 4 关仍"通过"（画面有背景、在动）—— 也就是说**它抓到的是"轮子没辐条、背景缺层"这类形态问题，
  与第 2 关互补，不能互相替代**。

### Phase 5 · 打开给用户看（Windows / 本项目环境）

```
["cmd", "/c", "start", "", "/code/你的文件.html"]
```

`start` 后必须紧跟空标题 `""`，否则 cmd 会把路径当窗口标题，结果什么都没打开。

### Phase 6 · 汇报

老实报告实测数据，别只说"做好了"。列出：文件路径 + 大小、冒烟测试跑了多少帧、非有限值计数、
id 检查结论、几何校验关键数值（每条腿的距离范围 / 膝角范围 / 违规计数）、截图结论（或"本机无浏览器已跳过"）。
**验证结果就是你的证据。** 哪一关没跑、哪一关跳过了，都要明说。

---

## 经典失败模式清单（生成时逐个对照）

1. 🚫 **鸟悬浮在车上** —— 身体没落在座垫上，中间有缝。用 `SEAT` 常量对齐身体下缘。
2. 🚫 **脚够不到踏板 / 腿是两根直棍** —— 没做 IK。用 Phase 3 卡。
3. 🚫 **轮子没有辐条或辐条不转** —— 辐条是"自行车"最强的视觉符号，不能省。
4. 🚫 **喙太短，看着像鸭子** —— 鹈鹕的喙要长且直，是识别关键。
5. 🚫 **没有喉囊** —— 鹈鹕唯一的身份证。
6. 🚫 **翅膀位置不对** —— 应搭在把手上，不是从背后平伸像要飞走。
7. 🚫 **轮子转速与路面滚动不同步** —— 必须由 `dist / R` 派生。
8. 🚫 **踏频与轮速脱钩** —— 轮速 = 踏频 × 传动比（自行车约 2.5~3）：`wheelAngle = crank * GEAR` 与 `dist / R` 要一致。
9. 🚫 **切标签页回来后动画瞬移** —— `dt` 必须夹住（`Math.min(dt, 0.05)`）。
10. 🚫 **车架构件是散的** —— 五通、花鼓、头管、座管要按几何连线，不是各画各的。
11. 🚫 **（SVG 专有）画面静默缺件** —— 分母为零导致 `rotate(NaN ...)`、id 拼错导致 `getElementById` 返回 null。
    **这类 bug 不报错，考试时看代码看不出来，必须靠 Phase 2 的 NaN 计数与 id 检查。**
12. 🚫 **（通用）`resize` 回调里回写 `window` 属性** —— 例如 `window.innerWidth = e.innerWidth`。
    非严格模式下静默无事，一旦是 `'use strict'` 就抛 `TypeError`，且只在用户拖窗口时才炸。
    resize 回调只读事件、不要给 window 赋值。

---

## 环境注意事项

- 本环境为 Windows，命令用 argv 数组：`["cmd", "/c", ...]`。
- 路径参数用虚拟路径（`/code/xxx.html`），不要传真实盘符路径。
- 临时文件放 `/tmp/`。
- 脚本用 `python` 调用，不要写绝对解释器路径。
- `scripts/*.py` 只依赖标准库，无需安装依赖（`smoke_test.py` 需 `node` 在 PATH）。
- 用 `read_file` 直接读截图 PNG 可以"看图"，这是第 4 关的人工确认手段。

---

## 输出示例

一次合格交付的汇报应长这样（SVG 路线）：

```
文件：/code/pelican-rider-svg2.html（约 24 KB，单文件无依赖，SVG + rAF）

冒烟测试：11 个阶段 / 636 帧全部通过
          非有限值(NaN/Infinity) 0 次；脚本请求 10 个 id，全部存在（无静默缺层）
几何校验：近侧腿 距离 88.0~148.0px / 膝角 70.7°~153.7° / 违规 0 项
          远侧腿 距离 87.8~147.8px / 膝角 70.5°~153.0° / 违规 0 项
          （腿总长 152px）
渲染截图：3 个时间点(200/1300/5200ms)均成功，画面随时间变化 ✅
          人工看图确认：双轮有辐条、鸟坐座垫上、长喙 + 喉囊、翅尖搭把套 ✅

关键实现：双骨 IK 反解膝盖、轮速由 dist/R 派生（SVG transform）、6 层视差
交互：空格/按住鼠标冲刺 · P 暂停 · R 重置里程
```

---

## 辅助参考

- `references/pelican_rig_checklist.md` —— 交付前逐项核对表
- `references/anatomy_notes.md` —— 鹈鹕解剖比例与配色速查