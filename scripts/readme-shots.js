// 生成 README 用的「演示截图」：真实界面 + 注入的示例内容
// 目的：README 截图不能包含用户真实聊天记录 / 内部项目名，所以只在截图进程里替换文案，
// 不修改任何业务数据与源码。
//
// 用法：npx vite（另开）→ electron scripts/readme-shots.js
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const os = require('os')
const path = require('path')

app.setPath('userData', path.join(os.tmpdir(), 'sassy-readme-profile'))
app.disableHardwareAcceleration()

const BASE = process.env.SHOT_BASE || 'http://localhost:5173'
const W = 1440
const H = 900
const DELAY = 5000
const outDir = path.join(__dirname, '..', 'shots', 'readme-raw')

const DEMO_MD = `
<h3>《产品需求文档》重点</h3>
<p>从知识库检索到 3 个相关片段，整理如下：</p>
<ul>
  <li><strong>目标</strong>：把评审流程从线下搬到工作台，减少一轮来回</li>
  <li><strong>关键改动</strong>：新增评审看板、支持 @ 相关人、结论自动归档</li>
  <li><strong>风险</strong>：历史数据迁移量大，需要预留回滚窗口</li>
</ul>
<blockquote>建议评审会先对齐「迁移窗口」与「回滚方案」两件事。</blockquote>
<p>提醒已创建：<code>20 分钟后</code>（15:40）提醒你「产品评审会」。需要我把这份摘要复制一份吗？</p>
`

const CHAT_TITLES = [
  '产品评审准备', '需求文档精读', '周报润色', 'SQL 慢查询排查', '桌宠玩法',
  '旅行计划', '读书笔记整理', '接口联调记录', '前端重构讨论', '数据看板设计',
  '周会纪要', '文案润色', '部署排错', '语音朗读配置', '提醒事项清单',
  '简历修改', '播客选题', '邮件草稿', '菜谱推荐', '新对话',
]

const KB_CARDS = [
  { name: '产品文档', desc: '需求、评审与路线图都在这里', docs: '24', chunks: '186', time: '更新于 2026-11-05 18:20' },
  { name: '技术手册', desc: '部署、接口与排错笔记', docs: '12', chunks: '92', time: '更新于 2026-11-03 09:12' },
  { name: '读书笔记', desc: '读过的好文与摘录', docs: '8', chunks: '41', time: '更新于 2026-10-28 21:04' },
  { name: '竞品调研', desc: '同类产品的体验拆解与截图', docs: '15', chunks: '73', time: '更新于 2026-10-21 16:40' },
]

const SKILLS = [
  ['html-ppt', '用一套模板生成演示文稿：版式、图表与讲稿一次性出齐'],
  ['web-research', '多源检索并交叉验证，输出带引用的调研摘要'],
  ['pdf-reader', '解析 PDF 与扫描件，抽取表格、要点和引用'],
  ['code-review', '按团队规范审查 diff，指出风险与改进点'],
  ['data-viz', '把表格数据变成可读的图表与结论'],
  ['meeting-notes', '从纪要或转写文本中提炼待办与负责人'],
  ['sql-helper', '自然语言转 SQL，并解释执行计划'],
  ['doc-writer', '按大纲扩写技术文档与 README'],
  ['weather-skill', '查询天气与多日预报，出门前先看一眼'],
]

function chatInject() {
  return `(() => {
    const titles = ${JSON.stringify(CHAT_TITLES)}
    document.querySelectorAll('.conv-title').forEach((el, i) => {
      el.textContent = titles[i % titles.length]
    })

    const user = document.querySelector('.msg.user .msg-content')
    if (user) user.textContent = '帮我把知识库里的《产品需求文档》重点整理一下，20 分钟后提醒我开评审会。'

    const md = document.querySelector('.msg.assistant .markdown-body')
    if (md) md.innerHTML = ${JSON.stringify(DEMO_MD)}

    const rb = document.querySelector('.reasoning-block')
    if (rb) {
      rb.setAttribute('open', '')
      const rc = rb.querySelector('.reasoning-content')
      if (rc) rc.textContent = '先确认需求文档是否在知识库里…命中 3 个片段；再抽取目标、改动点与风险；最后挂一个 20 分钟后的提醒。'
    }

    const tw = document.querySelector('.tool-steps-wrapper')
    if (tw) {
      const count = tw.querySelector('.sum-count')
      if (count) count.textContent = '2'
      const steps = tw.querySelector('.tool-steps')
      if (steps) steps.innerHTML = '<div class="tool-step">检索知识库 <b>kb_search</b><span class="tool-done">✓</span></div><div class="tool-step">创建提醒 <b>create_reminder</b><span class="tool-done">✓</span></div>'
    }

    const usage = document.querySelector('.usage-block')
    if (usage) {
      const inline = usage.querySelector('.usage-inline')
      if (inline) inline.textContent = '总计 4,812 · 输入 4,120 · 输出 692'
      const vals = usage.querySelectorAll('.usage-value')
      const nums = ['4,120', '692', '4,812']
      vals.forEach((v, i) => { if (nums[i]) v.textContent = nums[i] })
    }

    const list = document.querySelector('.msg-list')
    if (list) list.scrollTop = 0
  })()`
}

function kbInject() {
  return `(() => {
    const cards = ${JSON.stringify(KB_CARDS)}
    const grid = document.querySelector('.kb-grid')
    const first = document.querySelector('.kb-card')
    if (!grid || !first) return
    grid.innerHTML = ''
    cards.forEach((c, idx) => {
      const el = first.cloneNode(true)
      el.removeAttribute('style')
      const badge = el.querySelector('.card-badge')
      if (badge) badge.remove()
      const name = el.querySelector('.card-name')
      if (name) name.textContent = c.name
      const desc = el.querySelector('.card-desc')
      if (desc) desc.textContent = c.desc
      const meta = el.querySelector('.card-meta')
      if (meta) {
        const nums = meta.querySelectorAll('.meta-num')
        if (nums[0]) nums[0].textContent = c.docs
        if (nums[1]) nums[1].textContent = c.chunks
      }
      const time = el.querySelector('.card-time')
      if (time) time.textContent = c.time
      grid.appendChild(el)
    })
  })()`
}

function skillsInject() {
  return `(() => {
    const data = ${JSON.stringify(SKILLS)}
    const cards = document.querySelectorAll('.skill-card')
    cards.forEach((el, i) => {
      const d = data[i]
      if (!d) return
      const name = el.querySelector('.card-name')
      if (name) name.textContent = d[0]
      const desc = el.querySelector('.card-desc')
      if (desc) desc.textContent = d[1]
      const actions = el.querySelectorAll('.card-actions button')
      actions.forEach(b => { b.removeAttribute('title') })
    })
  })()`
}

const PAGES = [
  { name: 'dashboard', route: '/', wait: 3500 },
  { name: 'chat', route: '/chat', wait: DELAY, inject: chatInject },
  { name: 'kb', route: '/kb', wait: 4000, inject: kbInject },
  { name: 'skills', route: '/skills', wait: 4000, inject: skillsInject },
  { name: 'settings', route: '/settings', wait: 4000 },
  { name: 'about', route: '/about', wait: 3000 },
]

async function main() {
  fs.mkdirSync(outDir, { recursive: true })
  const win = new BrowserWindow({
    width: W,
    height: H,
    show: false,
    backgroundColor: '#090c11',
    webPreferences: { offscreen: true },
  })
  win.webContents.setFrameRate(30)
  let latest = null
  win.webContents.on('paint', (e, dirty, image) => { latest = image })

  for (const [i, page] of PAGES.entries()) {
    try {
      latest = null
      await win.loadURL(`${BASE}/?readme=${i}#${page.route}`)
      await new Promise((r) => setTimeout(r, page.wait))
      if (page.inject) {
        await win.webContents.executeJavaScript(page.inject())
        await new Promise((r) => setTimeout(r, 800))
      }
      let img = latest
      if (!img || img.isEmpty()) img = await win.webContents.capturePage()
      fs.writeFileSync(path.join(outDir, `${page.name}.png`), img.toPNG())
      console.log('saved', page.name)
    } catch (e) {
      console.error('fail', page.name, e && e.message)
    }
  }

  // 桌宠：单独开一个透明窗口，2× 缩放截取，供 make-readme-images.py 合成「桌宠海报」
  try {
    const petWin = new BrowserWindow({
      width: 840,
      height: 720,
      show: false,
      transparent: true,
      frame: false,
      backgroundColor: '#00000000',
      webPreferences: { offscreen: true },
    })
    petWin.webContents.setFrameRate(30)
    let petLatest = null
    petWin.webContents.on('paint', (e, dirty, image) => { petLatest = image })
    await petWin.loadURL(`${BASE}/pet/pet.html`)
    await new Promise((r) => setTimeout(r, 1500))
    petWin.webContents.setZoomFactor(2)
    await new Promise((r) => setTimeout(r, 2500))
    let img = petLatest
    if (!img || img.isEmpty()) img = await petWin.webContents.capturePage()
    fs.writeFileSync(path.join(outDir, 'pet.png'), img.toPNG())
    petWin.destroy()
    console.log('saved pet')
  } catch (e) {
    console.error('fail pet', e && e.message)
  }

  app.quit()
}

app.whenReady().then(main).catch((e) => { console.error('fatal', e); app.quit() })
