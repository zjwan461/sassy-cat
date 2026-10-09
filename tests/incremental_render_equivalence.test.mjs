/**
 * 「分块渲染 ≡ 整段渲染」等价性测试
 *
 * 运行方式：
 *   node --experimental-default-type=module tests/incremental_render_equivalence.test.mjs
 *   （需已安装依赖：node_modules/markdown-it）
 *
 * 思路：用与 MarkdownRenderer.vue 完全相同的引擎逻辑（splitter 找分界点，
 * 已定稿的块各渲染一次、尾部逐帧重渲染），逐小段喂入语料，最后比较
 * 「分块拼接出来的 HTML」与「整段一次性渲染的 HTML」是否逐字节相同。
 *
 * 这是分块方案最重要的安全网：一旦分界点落在非块边界上
 * （松/紧列表、缩进代码块、表格、围栏代码块等），这里会立刻失败。
 */
import MarkdownIt from 'markdown-it'
import { createStreamSplitter } from '../src/utils/streamSplitter.js'

let passed = 0
const failures = []

function assertEq(name, actual, expected) {
  if (actual === expected) passed++
  else {
    failures.push(`${name}\n    期望: ${JSON.stringify(expected)}\n    实际: ${JSON.stringify(actual)}`)
  }
}

function assert(name, cond, detail = '') {
  if (cond) passed++
  else failures.push(`${name}${detail ? '\n    ' + detail : ''}`)
}

// 与 MarkdownRenderer.vue 的基础配置保持一致（自定义 fence/表格/链接规则不影响块切分）
function makeMd() {
  return new MarkdownIt({ html: false, linkify: true, breaks: true })
}

/**
 * 模拟 MarkdownRenderer 的增量渲染引擎：
 * 逐 step 个字符喂入，按分界点把已定稿的内容渲染一次并"追加"，尾部每帧重渲染。
 * @returns {{ html: string, maxTail: number }}
 */
function renderIncrementally(md, src, step) {
  const splitter = createStreamSplitter()
  let committed = 0
  let html = ''
  let maxTail = 0
  for (let i = step; ; i += step) {
    const partial = src.slice(0, Math.min(i, src.length))
    splitter.feed(partial)
    const boundary = splitter.commitBoundary(partial)
    if (boundary > committed) {
      html += md.render(partial.slice(committed, boundary)) // 定稿块：只渲染一次
      committed = boundary
    }
    const tail = partial.slice(committed)
    maxTail = Math.max(maxTail, tail.length)
    const tailHtml = md.render(tail) // 尾部：每帧重渲染（覆盖）
    if (Math.min(i, src.length) >= src.length) {
      html += tailHtml
      break
    }
  }
  return { html, maxTail }
}

// ---------- 语料 ----------
const FIXTURES = [
  {
    name: '普通多段落',
    src: '# 标题\n\n第一段，包含 **加粗** 与 `行内代码`。\n\n第二段，含链接 https://example.com/a。\n\n第三段收尾。',
  },
  {
    name: '围栏代码块（内部含空行）',
    src: '先说明：\n\n```python\ndef f():\n    x = 1\n\n    return x\n```\n\n然后继续说明。',
  },
  {
    name: '未闭合围栏代码块',
    src: '开始：\n\n```js\nconst a = 1\n\nconst b = 2\n',
  },
  {
    name: '紧列表（无空行）',
    src: '列表如下：\n\n- 一\n- 二\n- 三\n\n结束。',
  },
  {
    name: '松列表（空行分隔，不可切）',
    src: '列表如下：\n\n- 一\n\n- 二\n\n结束。',
  },
  {
    name: '有序列表 + 引用',
    src: '步骤：\n\n1. 第一步\n\n2. 第二步\n\n> 注意：这里是引用。\n\n完。',
  },
  {
    name: '表格',
    src: '数据如下：\n\n| 列 A | 列 B |\n| --- | --- |\n| 1 | 2 |\n\n表后说明。',
  },
  {
    name: '缩进式代码块（内部含空行，不可切）',
    src: '说明：\n\n    code line 1\n\n    code line 2\n\n结束。',
  },
  {
    name: '块级数学',
    src: '公式：\n\n$$\nx = 1\n\ny = 2\n$$\n\n解释。',
  },
  {
    name: '标题层级 + 长文混合',
    src: '# 一\n\n## 二\n\ntext a\n\n### 三\n\ntext b\n\n- x\n\n- y\n\ntail.',
  },
]

// ---------- 断言 ----------
for (const { name, src } of FIXTURES) {
  const md = makeMd()
  const full = md.render(src)
  for (const step of [3, 17]) {
    const { html, maxTail } = renderIncrementally(makeMd(), src, step)
    assertEq(`分块渲染等价于整段渲染：${name}（step=${step}）`, html, full)
    assert(`尾部长度受控：${name}（step=${step}）`, maxTail < src.length, `maxTail=${maxTail} len=${src.length}`)
  }
}

// 松列表必须整体保持为「一个」列表（不能被切成两个紧列表）
{
  const src = '列表如下：\n\n- 一\n\n- 二\n\n结束。'
  const { html } = renderIncrementally(makeMd(), src, 3)
  assertEq('松列表保持单个 <ul>', (html.match(/<ul>/g) || []).length, 1)
}

// 分块确实发生了（否则等价性是无意义的自我满足）
{
  const src = '一。\n\n二。\n\n三。\n\n四。\n\n五。'
  const { html, maxTail } = renderIncrementally(makeMd(), src, 3)
  assertEq('分块渲染结果正确', html, makeMd().render(src))
  assert('分块后尾部始终很小', maxTail <= 6, `maxTail=${maxTail}`)
}

// ---------- 输出 ----------
if (failures.length) {
  console.error(`\n✗ 等价性测试失败 ${failures.length} 项（通过 ${passed} 项）\n`)
  for (const f of failures) console.error('  ✗ ' + f + '\n')
  process.exit(1)
}
console.log(`✓ 等价性测试全部通过（${passed} 项断言）`)