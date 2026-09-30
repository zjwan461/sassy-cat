---
name: pelican-rider-animation
description: >
  生成"动物骑自行车/交通工具"的 2D 单文件 HTML 动画，并用无头冒烟测试 +
  运动学几何校验在交付前自证无误。触发场景：用户要求"画一个鹈鹕骑自行车的动画"、"pelican riding a
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

## 交付前必过的三道关（本技能的核心价值）

| 关卡 | 手段 | 抓什么 |
|---|---|---|
| 语法 | `node --check` | 拼写错、括号不配对 |
| 运行时 | `scripts/smoke_test.py` | ReferenceError、undefined、NaN 坐标、rAF 断链、交互崩溃 |
| 几何 | `scripts/check_rig_geometry.py` | 腿被拉直/脱臼、膝盖打结、踏板穿车轮、脚穿地 |

**三关没跑完，不要对用户说"做好了"。** 未经验证的动画等于没做。

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
const HIP  = {x: 400, y: 286};                 // 髋（腿根）—— 决定腿能否够到踏板
const HT   = {x: 566, y: 306};                 // 头管上端
const HB   = {x: 578, y: 344};                 // 头管下端
const GRIP = {x: 614, y: 290};                 // 把套（翅尖抓住处）
const CRANK_R = 30;                            // 曲柄长
const THIGH = 78, SHIN = 74;                   // 腿骨长
```

**几何自检口诀**：`HIP` 到五通的距离应约为 `THIGH + SHIN` 的 0.6~0.9 倍。太远则腿绷直，太近则膝盖折不动。用 Phase 3 的脚本量化，不要靠眼睛判断。

### Phase 1 · 写单文件 HTML（Canvas 2D 优先）

- **优先 Canvas 2D**，不要用纯 CSS 拼轮辐和踏板。CSS 方案里轮速与踏频无法真正联动，只能靠 `animation-duration` 假装同步，一加速就露馅。
- 单文件、零外部依赖、双击即看。
- 结构：`<canvas>` + 一个 `requestAnimationFrame` 循环 + `dt` 累积。
- 输出写到虚拟环境的 `/code/` 下。**先 `ls /code` 看有无同名旧文件，有则换名，不要覆盖用户已有成果。**

#### Canvas 绘制要点

**车轮**：辐条用循环画，转速必须由位移反推，而非独立计时器：

```js
wheelAngle = dist / R;   // 正确：纯滚动，视觉不打滑
// wheelAngle = t * 5;   // 错误：加速时与路面滚动脱节
```

**腿部 IK（本技能技术核心）**：脚固定在踏板圆上，用双骨反解膝盖。不要用两条独立旋转的矩形假装腿——踏板到前后极点时会明显穿帮。

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

**鹈鹕本体**：
- 身体：白/米白椭圆，`ellipse()` 即可，下缘加内阴影暗示体积
- **脖子用贝塞尔做 S 形**（`bezierCurveTo`），鹈鹕是长颈水鸟，不能是圆柱
- **喙要长、直、微微下钩**，亮橙/沙黄，长度接近头长
- **喉囊挂在喙下方**，比喙更深更饱和的橙色，用 `quadraticCurveTo` 做出"袋口敞开、底部饱满"——**这是鹈鹕的身份证，缺了它这图就不是鹈鹕**
- 眼睛：小圆 + 高光点，位于喙根稍后方
- 翅：搭在把套那侧不必画清腿，让翅尖自然遮住，省掉一堆穿模问题

**视差滚动**：所有背景层速度都从 `dist` 派生，倍率递变：远山 0.05 → 树林 0.35 → 近林 0.7 → 路边草 0.95 → 路面 1.0 → 镜头前失焦草 1.8。加速时各层自然拉开，比固定时长的 CSS 动画真实得多。

### Phase 2 · 无头冒烟测试（必做）

```bash
python scripts/smoke_test.py /code/你的文件.html
```

它用桩 DOM + 桩 Canvas 把 `<script>` 真跑起来，自动走完 11 个阶段（静置、冲刺、松开、暂停、恢复、重置、resize、大 dt、非整数 dt、长时静置），并逐帧检查有无 NaN/Infinity 传给 Canvas。

- 退出码 0 = 通过。出现 `❌` 必须回去修，不许带错误交付。
- 另有自定义按键需求时用 `--extra-js drive.js` 追加。
- **若报"没找到 script 块"**：说明写成了纯 CSS 动画页，意味着运行时与几何两关都失效，风险自负。
- 脚本需 `node` 在 PATH 中。

### Phase 3 · 几何校验（骑乘类必做）

```bash
python scripts/check_rig_geometry.py \
    --bb 470 381 --hip 400 286 --crank 30 --thigh 78 --shin 74 \
    --rear-hub 382 368 --front-hub 592 368 --wheel-r 62 --ground 430
```

不带参数时就用上面 Phase 0 那套默认几何。它按 0.1° 步长扫 3600 个曲柄角，输出踏板→髋距离 min/avg/max（对比腿总长）、膝内角范围、四类硬性违规计数（越出可达范围 / 折叠空间不足 / 插入车轮圆 / 穿到地面下），以及最大膝角是否超 172°（僵硬警告）。

**任何 ❌ 都要改几何重跑，不要靠"看起来还行"蒙过去。**

### Phase 4 · 打开给用户看（Windows / 本项目环境）

```
["cmd", "/c", "start", "", "/code/你的文件.html"]
```

`start` 后必须紧跟空标题 `""`，否则 cmd 会把路径当窗口标题，结果什么都没打开。

### Phase 5 · 汇报

老实报告实测数据，别只说"做好了"。列出：文件路径 + 大小、冒烟测试跑了多少帧、几何校验关键数值（距离范围 / 膝角范围 / 违规计数）。**验证结果就是你的证据。**

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

---

## 环境注意事项

- 本环境为 Windows，命令用 argv 数组：`["cmd", "/c", ...]`。
- 路径参数用虚拟路径（`/code/xxx.html`），不要传真实盘符路径。
- 临时文件放 `/tmp/`。
- 脚本用 `python` 调用，不要写绝对解释器路径。
- `scripts/*.py` 只依赖标准库，无需安装依赖。

---

## 输出示例

一次合格交付的汇报应长这样：

```
文件：/code/pelican-rider-2d.html（30.7 KB，单文件无依赖）

冒烟测试：11 个阶段 / 636 帧全部通过，Canvas NaN 调用 0 次
几何校验：踏板→髋距离 88~148px（腿总长 152px），膝角 70.7°~153.7°
          越界 0 次 · 穿轮 0 次 · 穿地 0 次

关键实现：双骨 IK 反解膝盖、轮速由 dist/R 派生、6 层视差
交互：空格/按住鼠标冲刺 · P 暂停 · R 重置里程
```

---

## 辅助参考

- `references/pelican_rig_checklist.md` —— 交付前逐项核对表
- `references/anatomy_notes.md` —— 鹈鹕解剖比例与配色速查
