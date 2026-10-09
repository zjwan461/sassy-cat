/**
 * streamSplitter 行为测试（纯逻辑，零依赖）
 *
 * 运行方式（Node 会把 src/utils/streamSplitter.js 当作 ESM 载入）：
 *   node --experimental-default-type=module tests/stream_splitter.test.mjs
 *
 * 覆盖点：
 *   1. 分界点必须落在 markdown 的"块起始"上（空行之后的新块首行）
 *   2. 围栏代码块 / 块级数学区间内部不得出现分界点
 *   3. 列表 / 引用的 loose 容器内部不得被切开（空行两侧同类容器行）
 *   4. 空行一出现，分界点立即前移（不必等下一段内容到齐）—— 流式收益的前提
 *   5. 逐字符喂入（真实流式）与一次性喂入得到一致的分界点
 *   6. 分界点单调不减、且不超过当前源码长度
 */
import { createStreamSplitter } from '../src/utils/streamSplitter.js'

let passed = 0
const failures = []

function check(name, actual, expected) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a === e) {
    passed++
  } else {
    failures.push(`${name}\n    期望: ${e}\n    实际: ${a}`)
  }
}

function assert(name, cond, detail = '') {
  if (cond) passed++
  else failures.push(`${name}${detail ? '\n    ' + detail : ''}`)
}

/** 一次性喂入，返回最终分界点 */
function boundaryOf(src) {
  const s = createStreamSplitter()
  s.feed(src)
  return s.commitBoundary(src)
}

/** 逐字符喂入，返回每一步的分界点序列（模拟真实流式 delta） */
function boundaryTrail(src) {
  const s = createStreamSplitter()
  const trail = []
  for (let i = 1; i <= src.length; i++) {
    const partial = src.slice(0, i)
    s.feed(partial)
    trail.push(s.commitBoundary(partial))
  }
  return trail
}

// ---------- 1. 基本块边界 ----------
{
  const src = '第一段\n\n第二段'
  check('简单两段：分界点落在第二段起始', boundaryOf(src), src.indexOf('第二段'))
}

{
  const src = '# 标题\n\n正文一\n\n正文二'
  check('标题 + 两段：分界点推进到第二段前', boundaryOf(src), src.indexOf('正文二'))
}

{
  // 结尾正好是空行、且后面暂无内容：分界点后无字符可判定，保守不前移；
  // 后续内容一到，立即前移到位（此时整段前缀均已定稿）
  const src = '只有一段\n\n'
  check('尾部空行（暂无后续内容）：保守不前移', boundaryOf(src), 0)
  check('后续内容到达后前移到位', boundaryOf(src + 'X'), src.length)
}

{
  const src = '没有空行的单个段落，不应该有任何分界点'
  check('无空行：无分界点', boundaryOf(src), 0)
}

{
  // 连续空行会产生指向换行符的空候选，必须被丢弃且不阻断后续候选
  const src = 'a\n\n\n\nb'
  check('连续空行：只采纳真正的块起始', boundaryOf(src), src.indexOf('b'))
}

// ---------- 2. 围栏代码块内部不得切开 ----------
{
  const src = '说明：\n\n```python\nprint(1)\n\nprint(2)\n```\n\n结尾段'
  const b = boundaryOf(src)
  const fenceStart = src.indexOf('```')
  const fenceEnd = src.indexOf('```\n\n结尾段')
  assert('围栏内部空行不作为分界点', !(b > fenceStart && b < fenceEnd), `boundary=${b}`)
  check('围栏之后的新块可作为分界点', b, src.indexOf('结尾段'))
}

{
  const src = '```\ncode\n\nmore\n'
  check('未闭合围栏（含空行）无分界点', boundaryOf(src), 0)
}

{
  // ~~~ 与 ``` 不同符号，不能互相闭合
  const src = '~~~\nstill code\n```\n\n段落'
  check('不同符号围栏不闭合', boundaryOf(src), 0)
}

// ---------- 3. 列表 / 引用的 loose 容器保护 ----------
{
  const src = '- 条目一\n\n- 条目二'
  check('列表 loose 容器不被切开', boundaryOf(src), 0)
}

{
  const src = '1. 一\n\n2. 二\n\n普通段落'
  // 前两个空行都是列表内部续接，只有列表结束后的段落才是安全分界点
  check('有序列表续接不被切开，列表后段落可切', boundaryOf(src), src.indexOf('普通段落'))
}

{
  const src = '> 引用一\n\n> 引用二'
  check('引用 loose 容器不被切开', boundaryOf(src), 0)
}

{
  const src = '- 条目\n\n普通段落\n\n- 新列表'
  // 列表 -> 段落、段落 -> 列表：容器类型不同，均可切
  check('容器类型不同时可正常切开', boundaryOf(src), src.indexOf('- 新列表'))
}

// ---------- 4. 块级数学区间 ----------
{
  const src = '$$\nx = 1\n\ny = 2\n$$\n\n段落'
  const b = boundaryOf(src)
  const mathEnd = src.indexOf('$$\n\n段落')
  assert('$$ 区间内部空行不作为分界点', b === 0 || b >= mathEnd, `boundary=${b}`)
  check('$$ 之后的段落可作为分界点', b, src.indexOf('段落'))
}

// ---------- 5. 空行一到，分界点立即前移（流式收益前提） ----------
{
  const s = createStreamSplitter()
  const head = '第一段\n\n'
  s.feed(head)
  // 分界点落在源码末尾：下一行内容未知（可能是同类容器续接），本帧先不生效
  check('空行刚到齐：保守不前移', s.commitBoundary(head), 0)
  const more = head + '第二'
  s.feed(more)
  check('下一行首字符到达后立即前移', s.commitBoundary(more), head.length)
}

// ---------- 6. 流式一致性 / 单调性 ----------
{
  const src = '# 报告\n\n第一段内容。\n\n```js\nconst a = 1\n\nconst b = 2\n```\n\n结论。\n\n- 列表\n\n- 续接\n\n收尾。'
  const whole = boundaryOf(src)
  const trail = boundaryTrail(src)
  const last = trail[trail.length - 1]

  check('逐字符与一次性喂入的分界点一致', last, whole)

  let monotonic = true
  let bounded = true
  for (let i = 1; i < trail.length; i++) {
    if (trail[i] < trail[i - 1]) monotonic = false
    if (trail[i] > i) bounded = false
  }
  assert('分界点单调不减', monotonic, JSON.stringify(trail))
  assert('分界点不超过当前长度', bounded, JSON.stringify(trail))

  // 分界点必须落在"块起始"上：下标为 0、等于长度，或前一个字符是换行
  const ok = whole === 0 || whole === src.length || src[whole - 1] === '\n'
  assert('分界点位于块起始（行首）', ok, `boundary=${whole} ctx=${JSON.stringify(src.slice(whole - 4, whole + 4))}`)

  // 列表续接之后的"收尾"段必须能被切出来
  check('列表 loose 之后的新块可切', whole, src.indexOf('收尾'))
}

// ---------- 7. reset 后可重复使用 ----------
{
  const s = createStreamSplitter()
  const src = 'a\n\nb'
  s.feed(src)
  check('首次使用', s.commitBoundary(src), src.indexOf('b'))
  s.reset()
  check('reset 后分界点归零', s.commitBoundary(src), 0)
  s.feed(src)
  check('reset 后重新扫描结果一致', s.commitBoundary(src), src.indexOf('b'))
}

// ---------- 输出 ----------
if (failures.length) {
  console.error(`\n✗ streamSplitter 测试失败 ${failures.length} 项（通过 ${passed} 项）\n`)
  for (const f of failures) console.error('  ✗ ' + f + '\n')
  process.exit(1)
}
console.log(`✓ streamSplitter 测试全部通过（${passed} 项断言）`)