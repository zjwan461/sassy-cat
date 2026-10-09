/**
 * 流式 Markdown 分块扫描器（纯逻辑，无框架依赖）
 *
 * 用途：为「稳定前缀 + 活动尾部」增量渲染找出一串 **块安全分界点**
 * （源码下标，从它开始是 markdown 的一个新块），让渲染器把「已定稿的前缀」
 * 只渲染一次、只对「尾部」逐帧重渲染。
 *
 * 关键不变量
 * ----------
 * 1. 流式正文只做**追加**：某位置是否为合法分界点只取决于它的前缀，
 *    因此判定不可逆 —— 候选分界点集合随内容增长**单调增加**，永不失效，
 *    不需要滞后（hysteresis），也不会来回抖动。
 * 2. 扫描状态跨调用保持：`feed()` 只扫描新增片段（O(Δ)），已扫描部分不重复扫。
 * 3. 边界只前进不后退：`commitBoundary()` 返回的索引单调不减。
 *
 * 两段式判定
 * ----------
 * - `feed()`：遇到**空行**立即把"下一行起始"记为候选分界点。此刻后续内容可能
 *   还没到达，因此只做与后缀无关的部分（不在围栏/数学区间内）；
 * - `commitBoundary()`：真正采纳候选前，再用当前源码补做"下一行是否是
 *   同类容器的续接"判定（`- a` / `> b` / `1. c` 之间被空行隔开时，
 *   在 markdown 里仍属于同一个 loose 容器，硬切会改变渲染间距）。
 *
 * 注意：本扫描器是"尽力而为"的分块依据，渲染层在内容定稿（done）时会做一次整段重渲，
 * 以吸收分块带来的所有语义差异（另见 plans/streaming-markdown-render-perf-plan.md）。
 */

/** 缩进式代码块（4 空格起）判定 */
const INDENTED_RE = /^ {4,}/

export function createStreamSplitter() {
  let pos = 0 // 已扫描到的源码下标
  let lineStart = 0 // 当前（未完成）行的起始下标
  let fence = null // 未闭合围栏：{ char: '`' | '~', len: number }
  let math = false // 是否位于块级数学区间内
  let lastNonBlank = '' // 最近一个非空行（用于容器的续接判定）
  let candidates = [] // 候选分界点：[{ pos, prevKind }]
  let cursor = 0 // 下一个待审的候选下标
  let accepted = 0 // 已采纳的最大分界点（单调递增）

  function reset() {
    pos = 0
    lineStart = 0
    fence = null
    math = false
    lastNonBlank = ''
    candidates = []
    cursor = 0
    accepted = 0
  }

  /** 该行是否为与 marker 同符号、长度不短于 marker 的闭合围栏行 */
  function isFenceCloseLine(line, marker) {
    const t = line.trim()
    if (!t || t[0] !== marker.char) return false
    if (t.length < marker.len) return false
    return t === marker.char.repeat(t.length)
  }

  /**
   * 行所属容器类型：列表 / 引用；普通行返回 null。
   * 允许"标记符后为空"的形态（如刚收到的 `-`），以便对**尚未接收完整**的
   * 下一行保守判为容器行 —— 宁可不切，也不切错。
   */
  function containerKind(line) {
    const t = (line || '').trimStart()
    if (!t) return null
    if (t[0] === '>') return 'quote'
    if (/^([-*+]|\d+[.)])(\s|$)/.test(t)) return 'list'
    return null
  }

  function handleLine(line, lineEndIndex) {
    const t = line.trim()

    // 围栏代码块内部：只等闭合行
    if (fence) {
      if (isFenceCloseLine(line, fence)) fence = null
      return
    }

    // 块级数学区间：$$...$$ / \[...\]
    if (math) {
      if (t === '$$' || t.endsWith('$$') || t.endsWith('\\]')) math = false
      return
    }

    // 空行 ⇒ 下一行（若存在）就是块起始，立即记录候选分界点
    if (t === '') {
      candidates.push({
        pos: lineEndIndex + 1,
        prevKind: containerKind(lastNonBlank),
        prevIndented: INDENTED_RE.test(lastNonBlank),
      })
      return
    }

    if (t.startsWith('$$')) {
      if (!(t.length > 2 && t.endsWith('$$'))) math = true
      lastNonBlank = line
      return
    }
    if (t.startsWith('\\[')) {
      if (!t.endsWith('\\]')) math = true
      lastNonBlank = line
      return
    }

    // 围栏开始行（最多允许 3 个前导空格，与 markdown-it 一致）
    const m = /^ {0,3}(`{3,}|~{3,})/.exec(line)
    if (m) {
      fence = { char: m[1][0], len: m[1].length }
      lastNonBlank = line
      return
    }

    lastNonBlank = line
  }

  /**
   * 追加扫描：只处理 src 中尚未扫描的部分（O(Δ)）
   * @param {string} src 完整的累计源码
   */
  function feed(src) {
    let i = pos
    let ls = lineStart
    while (i < src.length) {
      if (src[i] !== '\n') {
        i++
        continue
      }
      handleLine(src.slice(ls, i).replace(/\r$/, ''), i)
      i++
      ls = i
    }
    lineStart = ls
    pos = src.length
  }

  /**
   * 取 src 中从 start 开始的一行。
   * complete=false 表示该行仍在接收中（还没有换行），其内容仍可能增长。
   */
  function lineRaw(src, start) {
    const end = src.indexOf('\n', start)
    const complete = end !== -1
    const raw = (complete ? src.slice(start, end) : src.slice(start)).replace(/\r$/, '')
    return { raw, complete }
  }

  /**
   * 该行（可能只是前缀）是否**仍有可能**演变成列表/引用容器行。
   * 内容只做追加、行前缀不可改写，因此只要首字符已确定不是标记符开头，就永远不会是容器行。
   */
  function couldBecomeContainer(raw) {
    const t = raw.trimStart()
    if (t === '') return true // 还只收到空白
    if (/^[>*+-]$/.test(t)) return true // 单个标记符，后面可能接空格
    if (/^\d+$/.test(t)) return true // 纯数字，后面可能出现 `.` / `)`
    return containerKind(t) !== null
  }

  /**
   * 审定一个候选分界点，返回 'accept' | 'reject' | 'defer'。
   *
   * 采纳不可撤销，而分界点后面的那一行可能还在接收中，此时只有在**确定安全**
   * 时才给结论，否则 defer 留到下一帧。借助"内容只追加、行前缀不可改写"这一点，
   * 不确定性可以精确框定为两类：
   *   - 缩进式代码块：还只收到空白，之后可能凑够 4 个空格（`    code`）；
   *   - 列表/引用续接：前缀仍可能长成同类标记（`-` 可能变 `- x`，`1` 可能变 `1. `）。
   *
   * - 候选指向真实内容（连续空行会产生指向换行符的空候选）⇒ reject
   * - 缩进式代码块（4 空格）内部 ⇒ reject
   * - 与上一个非空行同属列表/引用容器 ⇒ 同一 loose 容器，reject
   */
  function evaluateBoundary(src, c, prevKind, prevIndented) {
    const { raw, complete } = lineRaw(src, c)
    if (complete && raw.trim() === '') return 'reject'

    if (prevIndented) {
      if (INDENTED_RE.test(raw)) return 'reject'
      if (!complete && raw.trim() === '') return 'defer' // 可能凑够 4 个空格
    }

    if (!prevKind) return 'accept'
    if (containerKind(raw) === prevKind) return 'reject'
    if (!complete && couldBecomeContainer(raw)) return 'defer'
    return 'accept'
  }

  /**
   /**
    * 取当前可用的最大分界点（单调不减，且严格小于源码长度）。
    *
    * 分界点**落点后面至少要有 1 个字符**才做判定：空行刚到齐的那一帧，
    * 下一行内容还是未知的；等首字符到达即可判定，代价只是多渲染一小段尾部。
    *
    * 已定论的候选不会重复审（cursor 只前进）；遇到 defer 立即停止 ——
    * 候选按位置升序排列，某个候选的下一行尚未接收完整，则其后所有候选
    * 的下一行同样不完整，都要等下一帧。因此本方法基本是 O(1)。
    * @param {string} src 完整的累计源码
    * @returns {number} 已定稿前缀的长度（严格小于 src.length）
    */
   function commitBoundary(src) {
     while (cursor < candidates.length) {
       const { pos: c, prevKind, prevIndented } = candidates[cursor]
       if (c >= src.length) break // 分界点后面还没有内容，等下一帧再判定
       const verdict = evaluateBoundary(src, c, prevKind, prevIndented)
       if (verdict === 'defer') break
       if (verdict === 'accept') accepted = c
       cursor++
     }
     return accepted
   }
  return {
    reset,
    feed,
    commitBoundary,
    get boundary() {
      return accepted
    },
    get insideFence() {
      return !!fence
    },
    get insideMath() {
      return math
    },
  }
}