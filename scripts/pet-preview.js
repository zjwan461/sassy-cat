// 桌宠视觉预览：按 ?state=&mood=&action=&hovered= 逐项截图（开发期工具）
// 用法：$env:PET_STATES="idle,sleep"; electron scripts/pet-preview.js
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const os = require('os')
const path = require('path')

app.setPath('userData', path.join(os.tmpdir(), 'sassy-pet-preview'))
app.disableHardwareAcceleration()

const BASE = 'http://localhost:5173/pet/pet.html'
const OUT = path.join(__dirname, '..', 'shots', 'pet-preview')
const CASES = (process.env.PET_STATES || [
  'state=idle',
  'state=idle&hovered=1',
  'state=idle&action=stretch',
  'state=idle&action=groom',
  'state=idle&action=yawn',
  'state=sleep',
  'state=talk',
  'state=think',
  'state=remind',
  'state=idle&mood=happy',
  'state=idle&mood=annoyed',
  'state=idle&mood=dizzy',
  'state=idle&mood=purring',
].join(',')).split(',')

async function main() {
  fs.mkdirSync(OUT, { recursive: true })
  const win = new BrowserWindow({
    width: 840,
    height: 720,
    show: false,
    transparent: true,
    frame: false,
    backgroundColor: '#00000000',
    webPreferences: { offscreen: true },
  })
  win.webContents.setFrameRate(30)
  let latest = null
  win.webContents.on('paint', (e, d, image) => { latest = image })

  for (const c of CASES) {
    latest = null
    await win.loadURL(`${BASE}?${c}&_=${Date.now()}`)
    await new Promise((r) => setTimeout(r, 1600))
    const img = latest || await win.webContents.capturePage()
    const name = c.replace(/[&=]/g, '-')
    fs.writeFileSync(path.join(OUT, `${name}.png`), img.toPNG())
    console.log('saved', name)
  }
  app.quit()
}

app.whenReady().then(main).catch((e) => { console.error(e); app.quit() })
