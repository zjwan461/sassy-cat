const { app, BrowserWindow, ipcMain, Tray, Menu, dialog, shell, powerMonitor } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const PythonEnvChecker = require('./python-env-checker');
const { ConfigStore } = require('./config-store');

let mainWindow;
let setupWindow;
let petWindow = null;
let tray;
let pythonProcess = null;
let isRunning = false;
let envChecker = null;
let pythonPath = null;

// Agent 服务信息（由 Python [READY] 信号解析得到）
let agentInfo = { ready: false, port: null };

// 双层配置存储（app ready 前 userData 不可用，延迟到 whenReady 初始化）
let configStore = null;

function initConfigStore() {
  const templatePath = getAssetPath('config.json');
  const userPath = path.join(app.getPath('userData'), 'config.user.json');
  configStore = new ConfigStore(templatePath, userPath);
  // 配置变更 -> 推送给所有窗口（Settings 页负责经 WS 发 config.invalidate 通知 Python 热重建）
  configStore.on('changed', ({ diff }) => {
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) {
        win.webContents.send('config:changed', { diff });
      }
    }
  });
}

// 获取资源路径（开发/打包环境兼容）
function getAssetPath(relativePath) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, relativePath);
  }
  return path.join(__dirname, '..', relativePath);
}

// 读取项目配置（config.json）
function loadAppConfig() {
  const defaults = { name: '臭屁猫', version: '1.0.0' };
  try {
    const configPath = getAssetPath('config.json');
    if (fs.existsSync(configPath)) {
      const raw = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
      return { ...defaults, ...(raw.app || {}) };
    }
  } catch (e) {
    // 解析失败使用默认值
  }
  return defaults;
}

const appConfig = loadAppConfig();

// 创建主窗口
function createWindow() {
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
  const windowWidth = Math.min(Math.floor(screenWidth * 0.7), 1200);
  const windowHeight = Math.min(Math.floor(screenHeight * 0.75), 800);

  mainWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    minWidth: 800,
    minHeight: 600,
    // 窗口底色与界面一致，避免页面渲染前的白色闪屏（渲染层有全屏 loading 兜底）
    backgroundColor: '#0f172a',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: getAssetPath('assets/icon.png'),
    show: false,
    title: appConfig.name
  });

  // 开发环境加载Vite开发服务器，生产环境加载打包后的文件
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
  
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.send('status-update', { running: isRunning });
    if (agentInfo.ready) {
      mainWindow.webContents.send('agent-ready', agentInfo);
    }
  });
}

// 创建系统托盘
function createTray() {
  const iconPath = getAssetPath('assets/tray-icon.png');
  
  if (!fs.existsSync(iconPath)) {
    console.warn('无法创建系统托盘，缺少图标文件');
    return;
  }

  tray = new Tray(iconPath);

  const contextMenu = Menu.buildFromTemplate(buildTrayTemplate());

  tray.setToolTip(appConfig.name);
  tray.setContextMenu(contextMenu);
  
  tray.on('click', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
    }
  });
}

// Python 协议行前缀（与 python/main.py 中 PROTOCOL_PREFIX 保持一致）
const PROTOCOL_PREFIX = '__PROTOCOL__ ';
// stdout 行缓冲
let stdoutBuffer = '';
// 最新监控数据缓存（供渲染进程挂载较晚时主动拉取，解决事件时序问题）
let latestMetrics = null;
let latestSysinfo = null;

// ---------- 日志中心（type=log 消息统一入口） ----------
// 环形缓冲上限，防止无限增长；渲染进程挂载较晚时经 get-logs 拉取历史
const LOG_BUFFER_MAX = 500;
let logBuffer = [];

// 推送一条结构化日志：写入缓冲并广播到所有窗口
function pushLog(level, text, ts) {
  const entry = { type: 'log', ts: ts || Date.now(), level: level || 'info', text: String(text ?? '') };
  logBuffer.push(entry);
  if (logBuffer.length > LOG_BUFFER_MAX) {
    logBuffer.splice(0, logBuffer.length - LOG_BUFFER_MAX);
  }
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) {
      win.webContents.send('log-update', entry);
    }
  }
}

// 解析主进程侧原始行的级别前缀（如 [ERROR] xxx / [INFO] xxx），无前缀按 info 处理
function pushRawLineAsLog(line) {
  const m = line.match(/^\[(ERROR|WARN(?:ING)?|INFO|DEBUG)\]\s*(.*)$/is);
  if (m) {
    const lv = m[1].toUpperCase();
    const level = lv.startsWith('ERROR') ? 'error' : lv.startsWith('WARN') ? 'warn' : lv.startsWith('DEBUG') ? 'debug' : 'info';
    pushLog(level, m[2]);
  } else {
    pushLog('info', line);
  }
}

// [READY] 信号：Python Agent 服务就绪（携带 WS 端口）
const READY_PREFIX = '[READY] ';

// 处理一行协议数据：解析 JSON 并转发到渲染进程
function handleProtocolLine(line) {
  if (line.startsWith(READY_PREFIX)) {
    try {
      agentInfo = { ready: true, port: JSON.parse(line.slice(READY_PREFIX.length)).port };
    } catch (e) {
      agentInfo = { ready: true, port: null };
    }
    console.log('[main] agent ready, port =', agentInfo.port);
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) {
        win.webContents.send('agent-ready', agentInfo);
      }
    }
    return true;
  }
  if (!line.startsWith(PROTOCOL_PREFIX)) {
    return false;
  }
  try {
    const payload = JSON.parse(line.slice(PROTOCOL_PREFIX.length));
    if (payload.type === 'metrics') {
      latestMetrics = payload;
    } else if (payload.type === 'sysinfo') {
      latestSysinfo = payload.data;
    } else if (payload.type === 'log') {
      // Python 端 logging 转发的结构化日志 -> 统一经 pushLog 缓冲并广播
      pushLog(payload.level, payload.text, payload.ts);
      return true;
    }
    if (!mainWindow || mainWindow.isDestroyed()) {
      return true;
    }
    if (payload.type === 'metrics') {
      mainWindow.webContents.send('metrics-update', payload);
    } else if (payload.type === 'sysinfo') {
      mainWindow.webContents.send('sysinfo-update', payload.data);
    }
  } catch (e) {
    console.warn('协议行解析失败:', e.message);
  }
  return true;
}

// 启动Python服务
function startPythonService() {
  if (isRunning) {
    return { success: false, message: '服务已在运行中' };
  }

  try {
    let pyPath = pythonPath;
    if (!pyPath) {
      if (app.isPackaged) {
        pyPath = path.join(process.resourcesPath, 'python_env', 'python.exe');
      } else {
        pyPath = 'python';
      }
    }

    const pythonScriptPath = getAssetPath('python/main.py');
    const userConfigPath = path.join(app.getPath('userData'), 'config.user.json');

    pythonProcess = spawn(pyPath, [pythonScriptPath, '--config', userConfigPath], {
      cwd: getAssetPath('.'),
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      stdio: ['ignore', 'pipe', 'pipe']
    });

    const handleOutput = (text) => {
      // 按行拆分，尝试解析协议数据
      stdoutBuffer += text;
      const lines = stdoutBuffer.split(/\r?\n/);
      // 最后一段可能不完整，留在缓冲区
      stdoutBuffer = lines.pop() || '';

      lines.forEach((line) => {
        if (!line.trim()) return;
        // 协议行不转发为日志
        if (handleProtocolLine(line)) {
          return;
        }
        // 服务运行状态检测（logging 行格式为 "[HH:MM:SS] 服务启动成功"）
        if (line.includes('服务启动成功')) {
          isRunning = true;
          updateTrayMenu();
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('status-update', { running: true });
          }
        }
        // Python logging 控制台行（[HH:MM:SS] ...）已由 ProtocolLogHandler 以
        // 结构化 log 协议行转发，跳过原始行避免重复展示
        if (/^\[\d{2}:\d{2}:\d{2}\]/.test(line)) {
          return;
        }
        // 其余非协议原始输出（print、uvicorn 日志等）转为结构化日志
        pushRawLineAsLog(line.trim());
      });
    };

    pythonProcess.stdout.on('data', (data) => {
      handleOutput(data.toString());
    });
    // 进程退出时冲刷残留缓冲
    pythonProcess.on('close', () => {
      if (stdoutBuffer.trim()) {
        handleProtocolLine(stdoutBuffer.trim());
        stdoutBuffer = '';
      }
    });

    pythonProcess.stderr.on('data', (data) => {
      handleOutput(data.toString());
    });

    pythonProcess.on('error', (err) => {
      isRunning = false;
      updateTrayMenu();
      if (mainWindow) {
        mainWindow.webContents.send('status-update', { running: false });
      }
      pushLog('error', `进程启动失败: ${err.message}`);
    });

    pythonProcess.on('exit', (code, signal) => {
      isRunning = false;
      pythonProcess = null;
      updateTrayMenu();
      if (mainWindow) {
        mainWindow.webContents.send('status-update', { running: false });
      }
      pushLog('info', `进程已退出 (code: ${code}, signal: ${signal})`);
    });

    return { success: true, message: '服务启动中...' };
  } catch (error) {
    return { success: false, message: `启动失败: ${error.message}` };
  }
}

// 停止Python服务
function stopPythonService() {
  if (!isRunning || !pythonProcess) {
    return { success: false, message: '服务未在运行' };
  }

  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t']);
    } else {
      pythonProcess.kill('SIGTERM');
    }
    
    isRunning = false;
    pythonProcess = null;
    updateTrayMenu();
    
    if (mainWindow) {
      mainWindow.webContents.send('status-update', { running: false });
    }
    pushLog('info', '服务已停止');
    
    return { success: true, message: '服务已停止' };
  } catch (error) {
    return { success: false, message: `停止失败: ${error.message}` };
  }
}

function buildTrayTemplate() {
  const petVisible = petWindow && !petWindow.isDestroyed() && petWindow.isVisible();
  return [
    { label: '显示主窗口', click: () => mainWindow && mainWindow.show() },
    {
      label: petVisible ? '隐藏桌宠' : '显示桌宠',
      click: () => {
        if (petVisible) {
          petWindow.hide();
        } else {
          createPetWindow();
        }
        updateTrayMenu();
      }
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        app.isQuitting = true;
        if (isRunning) {
          stopPythonService();
        }
        app.quit();
      }
    }
  ];
}

function updateTrayMenu() {
  if (tray) {
    const contextMenu = Menu.buildFromTemplate(buildTrayTemplate());
    tray.setContextMenu(contextMenu);
  }
}

// IPC处理程序
ipcMain.handle('get-status', () => {
  return { running: isRunning };
});

// 主动拉取最新监控数据/系统信息（缓存）
ipcMain.handle('get-metrics', () => {
  return latestMetrics;
});

ipcMain.handle('get-sysinfo', () => {
  return latestSysinfo;
});

// 拉取日志历史（渲染进程挂载晚于推送时的补偿）
ipcMain.handle('get-logs', () => {
  return logBuffer;
});

// 导出日志为文件（系统保存对话框）
ipcMain.handle('logs:export', async (event, logs) => {
  const parent = mainWindow && !mainWindow.isDestroyed() ? mainWindow : undefined;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  const { canceled, filePath } = await dialog.showSaveDialog(parent, {
    title: '导出日志',
    defaultPath: `sassy-cat-logs-${stamp}.log`,
    filters: [
      { name: '日志文件', extensions: ['log'] },
      { name: '文本文件', extensions: ['txt'] }
    ]
  });
  if (canceled || !filePath) {
    return { success: false, canceled: true };
  }
  try {
    const lines = (logs || []).map((l) => {
      const t = new Date(l.ts || Date.now());
      const hh = String(t.getHours()).padStart(2, '0');
      const mm = String(t.getMinutes()).padStart(2, '0');
      const ss = String(t.getSeconds()).padStart(2, '0');
      return `[${hh}:${mm}:${ss}] ${(l.level || 'info').toUpperCase().padEnd(5)} ${l.text}`;
    });
    fs.writeFileSync(filePath, lines.join('\r\n') + '\r\n', 'utf-8');
    return { success: true, filePath };
  } catch (e) {
    return { success: false, message: `写入失败: ${e.message}` };
  }
});

// ---------- 配置系统 IPC ----------
ipcMain.handle('config:get', () => {
  if (!configStore) return { success: false, message: '配置未初始化' };
  return { success: true, config: configStore.getMasked() };
});

ipcMain.handle('config:set', (event, { path: cfgPath, value }) => {
  if (!configStore) return { success: false, message: '配置未初始化' };
  return configStore.setByDotted(cfgPath, value);
});

ipcMain.handle('config:set-many', (event, patches) => {
  if (!configStore) return { success: false, message: '配置未初始化' };
  return configStore.applyPatches(patches);
});

// 用户原始输入（未掩码）的 apiKey 需单独获取用于展示编辑：渲染层聚焦输入框时调用
ipcMain.handle('config:get-raw-profile-key', (event, profileName) => {
  if (!configStore) return { success: false };
  const profiles = configStore.merged.llm?.profiles || {};
  return { success: true, apiKey: profiles[profileName]?.apiKey || '' };
});

// Agent 服务就绪信息（WS 端口等）
ipcMain.handle('get-agent-info', () => {
  return agentInfo;
});

// 重启 Python Agent 服务（配置兜底生效手段）
ipcMain.handle('agent:restart', () => {
  if (pythonProcess) {
    stopPythonService();
    setTimeout(() => startPythonService(), 800);
    return { success: true, message: '服务重启中…' };
  }
  return startPythonService();
});

// 用系统默认浏览器打开外部链接（仅允许 http/https）
ipcMain.handle('open-external', async (event, url) => {
  if (typeof url === 'string' && /^https?:\/\//i.test(url)) {
    await shell.openExternal(url);
    return { success: true };
  }
  return { success: false, message: '无效的链接地址' };
});

// 环境检查失败时，用户主动退出程序
ipcMain.handle('quit-app', () => {
  app.isQuitting = true;
  app.quit();
  return { success: true };
});

// 创建环境检查窗口
function createSetupWindow() {
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();

  setupWindow = new BrowserWindow({
    width: 580,
    height: 680,
    resizable: false,
    frame: false,
    transparent: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    icon: getAssetPath('assets/icon.png'),
    title: '环境检查'
  });
  // 开发环境加载Vite开发服务器的setup页面（多页应用需带 .html 后缀）
  if (process.env.NODE_ENV === 'development') {
    setupWindow.loadURL('http://localhost:5173/setup.html');
  } else {
    setupWindow.loadFile(path.join(__dirname, '..', 'dist', 'setup.html'));
  }
  setupWindow.center();

  // 渲染进程错误日志，便于排查页面加载问题
  setupWindow.webContents.on('console-message', (event, level, message) => {
    if (level >= 2) {
      console.log('[SetupRenderer]', message);
    }
  });
  setupWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    console.log('[SetupWindow] 页面加载失败:', errorCode, errorDescription);
  });
}

// 运行环境检查
function runEnvCheck() {
  return new Promise((resolve) => {
    envChecker = new PythonEnvChecker(app, getAssetPath);

    // 转发事件到setup窗口
    envChecker.on('step', (stepName) => {
      if (setupWindow && !setupWindow.isDestroyed()) {
        setupWindow.webContents.send('env-check-step', { step: stepName });
      }
    });

    envChecker.on('step-done', (stepName) => {
      if (setupWindow && !setupWindow.isDestroyed()) {
        setupWindow.webContents.send('env-check-step-done', { step: stepName });
      }
    });

    envChecker.on('log', (message) => {
      if (setupWindow && !setupWindow.isDestroyed()) {
        setupWindow.webContents.send('env-check-log', { message });
      }
    });

    envChecker.on('progress', (message) => {
      if (setupWindow && !setupWindow.isDestroyed()) {
        setupWindow.webContents.send('env-check-progress', { message });
      }
    });

    envChecker.on('complete', (result) => {
      if (setupWindow && !setupWindow.isDestroyed()) {
        setupWindow.webContents.send('env-check-complete', result);
      }
    });

    envChecker.on('error', (message) => {
      if (setupWindow && !setupWindow.isDestroyed()) {
        setupWindow.webContents.send('env-check-error', { message });
      }
    });

    // IPC: 重试
    ipcMain.removeAllListeners('env-check-retry');
    ipcMain.on('env-check-retry', async () => {
      const result = await envChecker.checkAndSetup();
      resolve(result);
    });

    // IPC: setup页面准备关闭
    ipcMain.removeAllListeners('setup-ready-to-close');
    ipcMain.on('setup-ready-to-close', () => {
      if (setupWindow && !setupWindow.isDestroyed()) {
        setupWindow.close();
        setupWindow = null;
      }

      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.show();
      }

      createTray();
    });

    // 等待渲染进程通知"已准备好"后再开始检查
    // 使用 on 而非 once，确保即使 setup-ready 提前发送也能捕获
    let checkStarted = false;
    ipcMain.on('setup-ready', () => {
      if (checkStarted) return;
      checkStarted = true;
      setTimeout(() => {
        envChecker.checkAndSetup().then(resolve);
      }, 200);
    });
  });
}
// ---------- 桌宠窗口（设计稿 5 节） ----------
const PET_W = 220;
const PET_H = 150;

function createPetWindow() {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.show();
    return;
  }
  const { screen } = require('electron');
  const pos = configStore ? configStore.merged.pet?.position : null;
  const primary = screen.getPrimaryDisplay().workArea;
  const x = Number.isFinite(pos?.x) ? Math.min(pos.x, primary.x + primary.width - PET_W) : primary.x + primary.width - PET_W - 40;
  const y = Number.isFinite(pos?.y) ? Math.min(pos.y, primary.y + primary.height - PET_H) : primary.y + primary.height - PET_H - 10;

  petWindow = new BrowserWindow({
    width: PET_W,
    height: PET_H,
    x, y,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'pet-preload.js')
    }
  });
  // 默认鼠标穿透（forward 让渲染层仍能收到 mousemove 做命中检测）
  petWindow.setIgnoreMouseEvents(true, { forward: true });

  if (process.env.NODE_ENV === 'development') {
    petWindow.loadURL('http://localhost:5173/pet/pet.html');
  } else {
    petWindow.loadFile(path.join(__dirname, '..', 'dist', 'pet', 'pet.html'));
  }
  // 移动（拖动/走动）后防抖持久化位置
  let posTimer = null;
  petWindow.on('moved', () => {
    clearTimeout(posTimer);
    posTimer = setTimeout(() => savePetPosition(), 600);
  });
  // 窗口显隐状态变化时同步刷新托盘菜单（如桌宠右键“隐藏”经 pet:hide 隐藏窗口）
  petWindow.on('hide', () => updateTrayMenu());
  petWindow.on('show', () => updateTrayMenu());
  petWindow.on('closed', () => { petWindow = null; updateTrayMenu(); });
}

function savePetPosition() {
  if (!petWindow || petWindow.isDestroyed() || !configStore) return;
  const [x, y] = petWindow.getPosition();
  const [w, h] = petWindow.getSize();
  // 换算回基准尺寸（220x150）下的左上角：气泡/输入框展开会让窗口变高变宽并上移，
  // 直接保存会导致下次启动时桌宠本体位置漂移
  configStore.setByDotted('pet.position', {
    x: Math.round(x + (w - PET_W) / 2),
    y: y + (h - PET_H)
  });
}

// 拖动节流：16ms 合并一次
let moveAccum = { dx: 0, dy: 0 }, moveTimer = null;

ipcMain.handle('pet:set-interactive', (event, interactive) => {
  if (!petWindow || petWindow.isDestroyed()) return { success: false };
  petWindow.setIgnoreMouseEvents(!interactive, { forward: true });
  return { success: true };
});

ipcMain.on('pet:move-delta', (event, { dx, dy }) => {
  if (!petWindow || petWindow.isDestroyed()) return;
  moveAccum.dx += dx; moveAccum.dy += dy;
  if (moveTimer) return;
  moveTimer = setTimeout(() => {
    moveTimer = null;
    if (!petWindow || petWindow.isDestroyed()) return;
    const [x, y] = petWindow.getPosition();
    petWindow.setPosition(Math.round(x + moveAccum.dx), Math.round(y + moveAccum.dy));
    moveAccum = { dx: 0, dy: 0 };
  }, 16);
});

ipcMain.handle('pet:get-position', () => {
  if (!petWindow || petWindow.isDestroyed()) return null;
  const [x, y] = petWindow.getPosition();
  return { x, y };
});

// 支持 { height, width } 或数字（兼容旧调用）；以窗口底边中心为锚点向上/两侧扩展，
// 并钳制到所在显示器工作区顶部，避免气泡展开时窗口超出屏幕
ipcMain.handle('pet:resize', (event, opts) => {
  if (!petWindow || petWindow.isDestroyed()) return { success: false };
  const height = typeof opts === 'number' ? opts : (opts && opts.height) || PET_H;
  const width = (opts && typeof opts === 'object' && opts.width) || 0;
  const [w, h] = petWindow.getSize();
  const [x, y] = petWindow.getPosition();
  const newW = Math.max(PET_W, Math.round(width || w));
  const newH = Math.max(PET_H, Math.round(height));
  const newX = Math.round(x + (w - newW) / 2);
  let newY = y + (h - newH); // 底边固定
  const { screen } = require('electron');
  const wa = screen.getDisplayMatching({ x, y, width: w, height: h }).workArea;
  const bottom = y + h;
  if (newY < wa.y) newY = wa.y;
  const finalH = Math.max(PET_H, bottom - newY);
  petWindow.setBounds({ x: newX, y: newY, width: newW, height: finalH });
  return { success: true };
});

ipcMain.handle('pet:show-chat', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (!mainWindow.isVisible()) mainWindow.show();
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
    mainWindow.webContents.send('navigate-chat');
  }
  return { success: true };
});

ipcMain.handle('pet:hide', () => {
  if (petWindow && !petWindow.isDestroyed()) petWindow.hide();
  return { success: true };
});

ipcMain.handle('pet:popup-menu', (event, items) => {
  if (!petWindow || petWindow.isDestroyed()) return { success: false };
  const template = (items || []).map((it) => ({
    label: it.label,
    click: () => petWindow.webContents.send('pet:menu-action', { action: it.action })
  }));
  if (template.length) {
    Menu.buildFromTemplate(template).popup({ window: petWindow });
  }
  return { success: true };
});

// 应用生命周期
app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);

  // 初始化配置存储（依赖 userData 路径）
  initConfigStore();

  // OS 级用户活动信号 -> 广播到各渲染窗口（渲染层经 WS 转发 client.event:user_activity）
  const pingActivity = (event) => {
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) {
        win.webContents.send('activity-ping', { event, ts: Date.now() });
      }
    }
  };
  powerMonitor.on('unlock-screen', () => pingActivity('unlock-screen'));
  powerMonitor.on('lock-screen', () => pingActivity('lock-screen'));
  powerMonitor.on('resume', () => pingActivity('activity'));

  // 先创建并显示环境检查窗口
  createSetupWindow();

  // 运行环境检查
  const result = await runEnvCheck();

  if (result.success) {
    pythonPath = result.pythonPath;
    // 环境检查通过后，创建主窗口
    createWindow();
    // 显示主窗口
    if (mainWindow) {
      mainWindow.show();
    }
    // 自动启动监控采集服务（供仪表盘展示真实数据）
    startPythonService();
    // 创建桌宠窗口
    if (configStore.merged.pet?.enabled !== false) {
      createPetWindow();
    }
  } else {
    if (setupWindow && !setupWindow.isDestroyed()) {
      // 窗口已经显示错误信息，等待用户操作
    } else {
      dialog.showErrorBox('环境配置失败', `Python 环境配置失败:\n${result.error}\n\n应用程序无法启动。`);
      app.quit();
    }
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0 && pythonPath) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (isRunning) {
      stopPythonService();
    }
    app.quit();
  }
});

app.on('before-quit', async () => {
  app.isQuitting = true;
  if (isRunning) {
    stopPythonService();
  }
});
