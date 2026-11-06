// 视觉回归截图脚本（仅开发期使用，不参与打包）
// 用 Electron 内置 Chromium 加载 Vite dev 页面，逐路由截图到 shots/<tag>/<name>.png
// 用法：$env:SHOT_ROUTES="dashboard,chat,kb"; electron scripts/shot.js <tag>
// 注意：路由列表走环境变量而不是命令行参数 —— Windows 下以 "/" 开头的参数会被 Chromium 当成开关吞掉。
//
// 采用离屏渲染（offscreen）而不是可见窗口：锁屏 / 远程桌面断开时，
// 可见窗口会拿不到 display surface（capturePage 报 "Current display surface not available"）。
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const os = require('os')
const path = require('path')

app.setPath('userData', path.join(os.tmpdir(), 'sassy-shot-profile'))
app.disableHardwareAcceleration()

const TAG = process.argv[2] || 'before'
const BASE = process.env.SHOT_BASE || 'http://localhost:5173'
const NAMES = (process.env.SHOT_ROUTES || 'dashboard,chat,kb,mcp,skills,logs,settings,about').split(',')
const DELAY = Number(process.env.SHOT_DELAY || 3000)
const W = Number(process.env.SHOT_W || 1440)
const H = Number(process.env.SHOT_H || 900)

const ROUTES = {
  dashboard: '/',
  chat: '/chat',
  kb: '/kb',
  kbdetail: '/kb/default',
  mcp: '/mcp',
  skills: '/skills',
  skilldetail: '/skills/comfyui-image-studio',
  logs: '/logs',
  settings: '/settings',
  about: '/about',
}

const outDir = path.join(__dirname, '..', 'shots', TAG)

async function main() {
  console.log('start', TAG, BASE, NAMES.join('|'))
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
  win.webContents.on('paint', (event, dirty, image) => {
    latest = image
  })

  for (const [i, name] of NAMES.entries()) {
    const route = ROUTES[name] || `/${name}`
    try {
      latest = null
      // 加查询参数强制整页重载：只改 hash 属于同文档 SPA 跳转，截图会抓到过渡中间态
      await win.loadURL(`${BASE}/?shot=${i}#${route}`)
      await new Promise((res) => setTimeout(res, DELAY))
      let img = latest
      if (!img || img.isEmpty()) img = await win.webContents.capturePage()
      fs.writeFileSync(path.join(outDir, `${name}.png`), img.toPNG())
      console.log('saved', name, img.getSize())
    } catch (e) {
      console.error('fail', name, e && e.message)
    }
  }
  app.quit()
}

app.whenReady().then(main).catch((e) => {
  console.error('fatal', e)
  app.quit()
})
