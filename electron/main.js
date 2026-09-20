const { app, BrowserWindow, ipcMain, Tray, Menu, dialog, shell, powerMonitor, globalShortcut, Notification } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const dns = require('dns');
const PythonEnvChecker = require('./python-env-checker');
const { ConfigStore } = require('./config-store');

// Windows 下 Chromium 默认将 localhost 解析为 IPv6 ::1，
// 而 Python 服务通常只监听 IPv4 127.0.0.1，导致 fetch 失败。
// 强制优先使用 IPv4 解析。
dns.setDefaultResultOrder('ipv4first');

let mainWindow;
let setupWindow;
let petWindow = null;
let tray;
let pythonProcess = null;
let isRunning = false;
let envChecker = null;
let pythonPath = null;
let pythonStartTime = null;
let pythonStderrBuffer = '';
let pythonEverReady = false; // 本次启动是否收到过 [READY] 信号
let pythonStopping = false;  // 是否处于「主动停止」流程（抑制退出码非 0 的误报）

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
    // 快速提问快捷键变更 -> 热重注册并广播注册结果（Settings 页展示）
    if (Object.prototype.hasOwnProperty.call(diff, 'pet.quickAsk.shortcut')) {
      broadcastShortcutStatus(applyQuickAskShortcut());
    }
    // 桌宠开关变更 -> 即时创建/销毁桌宠窗口（无需重启），并刷新托盘（关闭时菜单项置灰）
    if (Object.prototype.hasOwnProperty.call(diff, 'pet.enabled')) {
      applyPetEnabled(diff['pet.enabled'] !== false);
      updateTrayMenu();
    }
    // 网络代理配置变更 -> 热更新 Electron 会话代理（Python 侧需重启服务进程生效）
    if (Object.keys(diff).some((k) => k.startsWith('network.proxy'))) {
      applyNetworkProxy().catch((e) => console.warn('[proxy] 应用失败:', e.message));
    }
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) {
        win.webContents.send('config:changed', { diff });
      }
    }
  });
}

// ---------- 网络代理（http / https） ----------
// 读取 network.proxy 配置；未启用或无地址时返回 null
function getProxyConfig() {
  const p = configStore ? configStore.merged.network?.proxy : null;
  if (!p || !p.enabled) return null;
  const http = String(p.http || '').trim();
  const https = String(p.https || '').trim() || http;
  if (!http && !https) return null;
  return { http, https, noProxy: String(p.noProxy || '').trim() };
}

// 将代理写入 Electron 默认会话（影响渲染进程与主进程 fetch）
async function applyNetworkProxy() {
  const { session } = require('electron');
  const p = getProxyConfig();
  if (!p) {
    // 禁用代理：使用 direct 模式直连
    await session.defaultSession.setProxy({ mode: 'direct' });
    console.log('[proxy] 已禁用代理（直连）');
    return;
  }
  const rules = [];
  if (p.http) rules.push(`http=${p.http}`);
  if (p.https) rules.push(`https=${p.https}`);
  await session.defaultSession.setProxy({
    mode: 'fixed_servers',
    proxyRules: rules.join(';'),
    proxyBypassRules: p.noProxy || '<local>',
  });
  console.log(`[proxy] 已应用代理: ${rules.join('; ')}${p.noProxy ? ` (绕过: ${p.noProxy})` : ''}`);
}

// 生成 Python 子进程的代理环境变量（httpx/requests 等默认读取，重启服务后生效）
function buildProxyEnv() {
  const p = getProxyConfig();
  if (!p) return {};
  const env = {};
  const setPair = (name, value) => {
    env[name] = value;
    env[name.toLowerCase()] = value;
  };
  if (p.http) setPair('HTTP_PROXY', p.http);
  if (p.https) setPair('HTTPS_PROXY', p.https);
  if (p.noProxy) setPair('NO_PROXY', p.noProxy);
  return env;
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
  const defaults = { name: '优墨', version: '1.0.0' };
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

// ---------- 主窗口激活状态（供桌宠判断是否重复展示聊天气泡） ----------
// 「激活」= 可见、未最小化且获得焦点。桌宠据此决定：主窗口前台时不再用气泡
// 复述聊天内容（提醒类消息仍照常展示）。
function mainWindowActive() {
  return !!(mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible()
    && !mainWindow.isMinimized() && mainWindow.isFocused());
}

// 把主窗口激活状态同步给桌宠窗口（焦点/显隐/最小化变化时调用）
function notifyMainWindowState() {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.webContents.send('main-window-state', { active: mainWindowActive() });
  }
}

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

  // 主窗口激活状态变化（焦点 / 显隐 / 最小化）-> 同步给桌宠，用于抑制重复聊天气泡
  ['focus', 'blur', 'show', 'hide', 'minimize', 'restore'].forEach((ev) => {
    mainWindow.on(ev, notifyMainWindowState);
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
    pythonEverReady = true; // 标记已收到就绪信号
    pythonStopping = false;
    // [READY] 是服务真正就绪的可靠信号（uvicorn 已开始监听）：用它置运行标志，
    // 不再依赖易变的日志文案匹配（原先匹配的 "服务启动成功" 当前根本不会输出，
    // 导致 isRunning 恒为 false、退出/重启时都杀不掉进程）
    isRunning = true;
    updateTrayMenu();
    console.log('[main] agent ready, port =', agentInfo.port);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('status-update', { running: true });
    }
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
  // 以「是否存在子进程」为准（而非 isRunning）：服务未收到 [READY] 前 isRunning 仍为
  // false，只看它会在旧进程未退出时重复 spawn 出多个 Python 进程
  if (pythonProcess) {
    return { success: false, message: '服务已在运行中' };
  }

  // 重置错误输出缓冲
  pythonStderrBuffer = '';
  pythonStartTime = Date.now();
  pythonEverReady = false; // 重置就绪标记
  pythonStopping = false;  // 重置主动停止标记

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
    const userDataPath = app.getPath('userData');
    const userConfigPath = path.join(userDataPath, 'config.user.json');

    // --data-dir：会话元数据与 checkpoint 等用户数据的存放目录（Python 侧 paths.py 消费）
    pythonProcess = spawn(pyPath, [pythonScriptPath, '--config', userConfigPath, '--data-dir', userDataPath], {
      cwd: getAssetPath('.'),
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', ...buildProxyEnv() },
      stdio: ['ignore', 'pipe', 'pipe']
    });
    // 捕获本次进程引用：close/error 回调只应清理「自己」，否则重启时旧进程的事件
    // 会把已启动的新进程引用误置为 null，导致后续再也停不掉新进程
    const spawned = pythonProcess;

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

    spawned.stdout.on('data', (data) => {
      handleOutput(data.toString());
    });
    spawned.stderr.on('data', (data) => {
      const text = data.toString();
      // 收集 stderr 输出用于错误诊断
      pythonStderrBuffer += text;
      // 限制缓冲大小，防止内存溢出
      if (pythonStderrBuffer.length > 50000) {
        pythonStderrBuffer = pythonStderrBuffer.slice(-50000);
      }
      handleOutput(text);
    });

    spawned.on('error', (err) => {
      // 只有当本进程仍是当前跟踪的进程时才更新状态，避免影响已启动的新进程
      const isCurrent = pythonProcess === spawned;
      if (isCurrent) {
        pythonProcess = null;
        isRunning = false;
        updateTrayMenu();
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('status-update', { running: false });
        }
      }
      pushLog('error', `进程启动失败: ${err.message}`);
      // 主动停止（含 taskkill 竞态）或已被替换的旧进程，不弹「无法启动」错误框
      const intentionalStop = spawned.__intentionalStop === true || pythonStopping;
      if (isCurrent && !intentionalStop) {
        showPythonStartError(`无法启动 Python 进程: ${err.message}`, '');
      }
    });

    // close 事件在 exit 之后、所有 stdio 流关闭后触发，此时 stderr 数据已完整
    spawned.on('close', (code, signal) => {
      // 冲刷残留缓冲
      if (stdoutBuffer.trim()) {
        handleProtocolLine(stdoutBuffer.trim());
        stdoutBuffer = '';
      }
      
      // 仅当本进程仍是当前跟踪的进程时才更新运行状态并清空引用，
      // 避免重启时旧进程的 close 事件把已启动的新进程标记为「未运行」
      const isCurrent = pythonProcess === spawned;
      if (isCurrent) {
        pythonProcess = null;
        isRunning = false;
        updateTrayMenu();
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('status-update', { running: false });
        }
      }
      pushLog('info', `进程已退出 (code: ${code}, signal: ${signal})`);
      
      // 启动失败判定必须限定在「本进程」上：
      //   isCurrent        —— 被替换掉的旧进程，其 close 不应再触发失败提示；
      //   intentionalStop  —— 主动停止（taskkill 退出码非 0）不算失败。
      // 历史教训：重启时旧进程 close 会晚于新进程 spawn（此时 pythonEverReady /
      // pythonStopping 刚被重置），不加这两个限定就会误弹「Python 服务启动失败」。
      const intentionalStop = spawned.__intentionalStop === true || pythonStopping;
      const isStartupFailure = isCurrent && code !== 0 && code !== null && !pythonEverReady && !intentionalStop;
      
      if (isStartupFailure) {
        const errorMsg = `Python 服务启动失败 (退出码: ${code})`;
        const detailMsg = pythonStderrBuffer.trim() || '请检查 Python 环境和依赖是否完整。';
        pushLog('error', errorMsg);
        // 延迟弹出对话框，确保 UI 已就绪
        setTimeout(() => {
          showPythonStartError(errorMsg, detailMsg);
        }, 500);
      }
    });

    return { success: true, message: '服务启动中...' };
  } catch (error) {
    return { success: false, message: `启动失败: ${error.message}` };
  }
}

// 从 Python traceback 中提取关键错误信息并生成友好提示
function parsePythonError(stderr) {
  if (!stderr) return { title: 'Python 服务启动失败', hint: '请检查 Python 环境和依赖是否完整。' };

  const lines = stderr.split(/\r?\n/);
  // 找最后一行非空行（通常是错误类型和消息）
  let lastLine = '';
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i].trim()) {
      lastLine = lines[i].trim();
      break;
    }
  }

  // 常见错误的友好映射
  const friendlyHints = [
    {
      match: /DLL load failed.*找不到指定的模块/i,
      title: '缺少 VC++ 运行环境',
      hint: '请安装 Microsoft Visual C++ Redistributable 2015-2022。\n下载地址: https://aka.ms/vs/17/release/vc_redist.x64.exe'
    },
    {
      match: /ModuleNotFoundError.*No module named '([^']+)'/i,
      title: '缺少 Python 依赖',
      hint: (m) => `缺少模块: ${m[1]}\n请在终端中运行: pip install ${m[1]}`
    },
    {
      match: /ImportError.*cannot import name '([^']+)'/i,
      title: 'Python 依赖导入失败',
      hint: (m) => `无法导入: ${m[1]}\n请检查依赖版本是否兼容。`
    },
    {
      match: /PermissionError/i,
      title: '权限不足',
      hint: '请以管理员身份运行程序。'
    },
    {
      match: /FileNotFoundError/i,
      title: '文件未找到',
      hint: '请检查程序安装路径是否完整。'
    },
    {
      match: /ConnectionRefusedError|ECONNREFUSED/i,
      title: '无法连接服务',
      hint: '请检查网络设置或防火墙配置。'
    },
  ];

  for (const rule of friendlyHints) {
    const m = lastLine.match(rule.match);
    if (m) {
      const hint = typeof rule.hint === 'function' ? rule.hint(m) : rule.hint;
      return { title: rule.title, hint };
    }
  }

  // 未匹配到已知模式，显示最后一行错误
  return {
    title: 'Python 服务启动失败',
    hint: lastLine || '请检查 Python 环境和依赖是否完整。'
  };
}

// 显示 Python 启动错误对话框
function showPythonStartError(title, detail) {
  console.error('[Python Error]', title, detail);

  // 尝试在主窗口显示错误（如果窗口已创建）
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('python-start-error', { title, detail });
  }

  // 从 traceback 中提取友好的错误提示
  const { title: friendlyTitle, hint: friendlyHint } = parsePythonError(detail);

  // 优先使用异步 showMessageBox（模态对话框，带父窗口关联）
  const parent = (mainWindow && !mainWindow.isDestroyed()) ? mainWindow : undefined;
  dialog.showMessageBox(parent, {
    type: 'error',
    title: friendlyTitle,
    message: friendlyTitle,
    detail: friendlyHint,
    buttons: ['确定']
  }).catch(() => {
    // 异步调用失败时回退到 showErrorBox
    dialog.showErrorBox(friendlyTitle, friendlyHint);
  });
}

// 停止Python服务
// 返回 Promise：进程真正退出（或 5s 兜底超时）后 resolve，供重启流程串行等待。
// 判定条件改用「是否存在子进程」，不再依赖 isRunning（服务未就绪时它为 false，
// 旧逻辑会直接 return，导致旧进程残留）。
function stopPythonService() {
  if (!pythonProcess) {
    isRunning = false;
    return Promise.resolve({ success: false, message: '服务未在运行' });
  }

  const proc = pythonProcess;
  pythonStopping = true;         // 全局标记（兼作兼容兜底）
  // 进程级标记：即使重启流程随后把全局 pythonStopping 重置，旧进程的 close
  // 事件也不会被误判为「启动失败」
  proc.__intentionalStop = true;
  pythonProcess = null;
  isRunning = false;
  updateTrayMenu();
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('status-update', { running: false });
  }
  pushLog('info', '正在停止服务…');

  // 等待进程真正退出，避免新进程启动时端口仍被旧进程占用（否则回退到随机端口）
  const exited = new Promise((resolve) => {
    let settled = false;
    const done = () => { if (!settled) { settled = true; resolve(); } };
    proc.once('close', done);
    proc.once('exit', done);
    setTimeout(done, 5000); // 兜底：最多等待 5s，避免调用方被长时间挂起
  });

  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', proc.pid, '/f', '/t']);
    } else {
      proc.kill('SIGTERM');
    }
  } catch (error) {
    pushLog('error', `停止服务失败: ${error.message}`);
    return Promise.resolve({ success: false, message: `停止失败: ${error.message}` });
  }

  return exited.then(() => {
    pushLog('info', '服务已停止');
    return { success: true, message: '服务已停止' };
  });
}

function buildTrayTemplate() {
  // 设置中关闭桌宠时托盘项置灰：显隐统一由「设置 > 桌宠 > 启用桌宠」控制，避免语义冲突
  const petEnabled = !configStore || configStore.merged.pet?.enabled !== false;
  const petVisible = petEnabled && petWindow && !petWindow.isDestroyed() && petWindow.isVisible();
  return [
    { label: '显示主窗口', click: () => mainWindow && mainWindow.show() },
    {
      // 「显示桌宠」持久开启（写 pet.enabled，与设置页联动）；「隐藏桌宠」仅临时隐藏不改设置
      label: !petEnabled ? '桌宠已关闭（于设置中开启）' : (petVisible ? '隐藏桌宠' : '显示桌宠'),
      enabled: petEnabled,
      click: () => {
        if (petVisible) {
          petWindow.hide();
        } else {
          if (configStore) configStore.setByDotted('pet.enabled', true);
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
        if (pythonProcess) {
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

// 当前快速提问快捷键注册状态（Settings 页加载时查询）
ipcMain.handle('shortcut:status', () => {
  return { success: true, shortcut: registeredQuickAsk || '', message: '' };
});

// 重启 Python Agent 服务（配置兜底生效手段）
ipcMain.handle('agent:restart', async () => {
  // 先等旧进程真正退出，再启动新进程：固定 setTimeout 无法保证 kill 已完成，
  // 会造成新旧进程并存（端口回退、checkpoint/DB 文件锁冲突）
  if (pythonProcess) {
    await stopPythonService();
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
// ---------- HTML 预览：落盘 + 应用内 Electron 窗口打开 ----------
// 预览目录：开发环境用项目 runtime/preview（agent sandbox 工作区）；
// 打包后 resources 可能只读，回退到 userData/preview
function getPreviewDir() {
  const base = app.isPackaged ? app.getPath('userData') : getAssetPath('runtime');
  const dir = path.join(base, 'preview');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// 预览窗口（单例复用：再次预览时同一窗口加载新内容）
let htmlPreviewWindow = null;

// 渲染进程把 markdown 中的 html 代码块内容发过来：写入临时 .html 文件，
// 在应用内独立 BrowserWindow 中打开（file:// 协议，脚本、样式完整可运行，
// 不注入 preload、禁用 node，与主应用隔离）
ipcMain.handle('html-preview:open', async (event, html) => {
  if (typeof html !== 'string' || !html.trim()) {
    return { success: false, message: '预览内容为空' };
  }
  try {
    const dir = getPreviewDir();
    const file = path.join(dir, `preview-${Date.now()}.html`);
    fs.writeFileSync(file, html, 'utf-8');

    if (htmlPreviewWindow && !htmlPreviewWindow.isDestroyed()) {
      await htmlPreviewWindow.loadFile(file);
      if (!htmlPreviewWindow.isVisible()) htmlPreviewWindow.show();
      htmlPreviewWindow.focus();
      return { success: true, filePath: file };
    }

    htmlPreviewWindow = new BrowserWindow({
      width: 1000,
      height: 720,
      minWidth: 400,
      minHeight: 300,
      backgroundColor: '#ffffff',
      title: 'HTML 预览',
      icon: getAssetPath('assets/icon.png'),
      autoHideMenuBar: true,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        // 不注入任何 preload，预览页面与主应用完全隔离
      },
    });
    htmlPreviewWindow.on('closed', () => { htmlPreviewWindow = null; });
    // 预览页内的外链跳转交回系统浏览器，避免占用预览窗口
    htmlPreviewWindow.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https?:\/\//i.test(url)) {
        shell.openExternal(url);
      }
      return { action: 'deny' };
    });
    await htmlPreviewWindow.loadFile(file);
    return { success: true, filePath: file };
  } catch (e) {
    return { success: false, message: e.message };
  }
});

// 测试 LLM 连接（主进程发起，无 CORS 限制）
ipcMain.handle('test-llm-connection', async (event, params) => {
  const { baseUrl, apiKey, model } = params || {};
  if (!baseUrl || !apiKey || !model) {
    return { ok: false, error: '请填写完整的 Base URL、API Key 和模型名称' };
  }
  // Windows 下 Chromium fetch 可能将 localhost 解析为 IPv6 ::1，
  // 而 Python 服务通常只监听 127.0.0.1，兜底替换为 IPv4 地址。
  const safeUrl = baseUrl.replace(/\/$/, '').replace(/\/\/localhost(:|\/|$)/i, '//127.0.0.1$1');
  const url = `${safeUrl}/chat/completions`;
  const startTime = Date.now();
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'Hi' }],
        max_tokens: 10,
      }),
    });
    const latencyMs = Date.now() - startTime;
    if (!resp.ok) {
      const errText = await resp.text();
      return { ok: false, error: `HTTP ${resp.status}: ${errText.slice(0, 120)}` };
    }
    const data = await resp.json();
    const reply = data.choices?.[0]?.message?.content || 'OK';
    return { ok: true, latencyMs, reply: reply.slice(0, 80) };
  } catch (e) {
    const latencyMs = Date.now() - startTime;
    return { ok: false, error: `${e.message}` };
  }
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
// ---------- 桌宠快速提问全局快捷键 ----------
// 当前已成功注册的 accelerator（null 表示未注册/已禁用）
let registeredQuickAsk = null;

// 注册（或重新注册）快速提问全局快捷键，返回 { success, message }
function applyQuickAskShortcut() {
  const sc = String((configStore && configStore.merged.pet?.quickAsk?.shortcut) || '').trim();
  if (registeredQuickAsk) {
    globalShortcut.unregister(registeredQuickAsk);
    registeredQuickAsk = null;
  }
  if (!sc) {
    return { success: true, message: '', shortcut: '' }; // 空串 = 禁用
  }
  try {
    const ok = globalShortcut.register(sc, triggerQuickAsk);
    if (!ok) throw new Error('快捷键可能已被其他程序占用');
    registeredQuickAsk = sc;
    return { success: true, message: '', shortcut: sc };
  } catch (e) {
    pushLog('warn', `快速提问快捷键注册失败（${sc}）: ${e.message}`);
    return { success: false, message: e.message, shortcut: sc };
  }
}

// 快捷键触发：唤起桌宠窗口并切换快速输入框
function triggerQuickAsk() {
  // 桌宠已在设置中关闭：静默忽略（尊重用户设置）
  if (configStore && configStore.merged.pet?.enabled === false) return;
  if (!petWindow || petWindow.isDestroyed()) {
    createPetWindow();
    // 窗口刚创建时渲染层尚未就绪，等加载完成后再通知打开输入框
    if (petWindow) {
      petWindow.webContents.once('did-finish-load', () => {
        if (petWindow && !petWindow.isDestroyed()) {
          petWindow.webContents.send('pet:quick-ask');
        }
      });
    }
    return;
  }
  if (!petWindow.isVisible()) {
    petWindow.show();
  }
  petWindow.focus(); // 确保渲染层 input.focus() 能立即生效
  petWindow.webContents.send('pet:quick-ask');
}

// 广播快捷键注册状态到所有窗口（Settings 页据此提示成功/失败）
function broadcastShortcutStatus(result) {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) {
      win.webContents.send('shortcut-status', result);
    }
  }
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
  // 桌宠页面加载完成后同步一次主窗口激活状态（渲染层也会主动查询，双保险）
  petWindow.webContents.on('did-finish-load', notifyMainWindowState);
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

ipcMain.handle('pet:set-interactive', (event, interactive) => {
  if (!petWindow || petWindow.isDestroyed()) return { success: false };
  petWindow.setIgnoreMouseEvents(!interactive, { forward: true });
  return { success: true };
});

// 相对移动窗口（拖动/走动）：移动后按窗口所在显示器工作区钳制，
// 保证桌宠（含展开的气泡/输入框）完整留在屏幕内，不会跑到桌面外
ipcMain.on('pet:move-delta', (event, { dx, dy }) => {
  if (!petWindow || petWindow.isDestroyed()) return;
  const { screen } = require('electron');
  const [x, y] = petWindow.getPosition();
  const [w, h] = petWindow.getSize();
  const nx = Math.round(x + dx);
  const ny = Math.round(y + dy);
  // 以移动后的窗口中心为准，取最近的显示器工作区（含任务栏避让，支持多屏）
  const wa = screen.getDisplayNearestPoint({
    x: Math.round(nx + w / 2),
    y: Math.round(ny + h / 2)
  }).workArea;
  const clampedX = Math.min(wa.x + wa.width - w, Math.max(wa.x, nx));
  const clampedY = Math.min(wa.y + wa.height - h, Math.max(wa.y, ny));
  petWindow.setPosition(clampedX, clampedY);
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
  let newX = Math.round(x + (w - newW) / 2);
  let newY = y + (h - newH); // 底边固定
  const { screen } = require('electron');
  const wa = screen.getDisplayMatching({ x, y, width: w, height: h }).workArea;
  const bottom = y + h;
  if (newY < wa.y) newY = wa.y;
  // 水平方向同样钳制到工作区内，避免桌宠靠在屏幕边缘时气泡/输入框扩宽被推出屏外
  newX = Math.min(wa.x + wa.width - newW, Math.max(wa.x, newX));
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

// 桌宠渲染层挂载时主动查询一次主窗口激活状态（与事件推送互为兜底）
ipcMain.handle('pet:main-window-active', () => mainWindowActive());

// ---------- 桌宠开关热生效 ----------
// pet.enabled: true -> 创建/显示桌宠窗口；false -> 销毁窗口（避免隐藏窗口后台残留 WS 连接）
function applyPetEnabled(enabled) {
  if (enabled) {
    createPetWindow();
  } else if (petWindow && !petWindow.isDestroyed()) {
    petWindow.destroy();
    petWindow = null;
    updateTrayMenu();
  }
}

// ---------- 系统通知（桌宠不可见时的提醒兜底） ----------
// 由主进程统一裁决：桌宠窗口存在且实际可见 -> 气泡负责展示，丢弃请求；
// 否则（设置关闭 / 临时隐藏）-> 弹系统原生通知。
// 调用方（主窗口渲染层收到 proactive.reminder / proactive.message 时）无需关心桌宠状态。
ipcMain.handle('notify:show', (event, { title, body }) => {
  const petVisible = petWindow && !petWindow.isDestroyed() && petWindow.isVisible() && !petWindow.isMinimized();
  if (petVisible) return { success: true, suppressed: true };
  if (!Notification.isSupported()) return { success: false, message: '系统不支持通知' };
  const notif = new Notification({
    title: String(title || appConfig.name),
    body: String(body || ''),
    icon: getAssetPath('assets/icon.png'),
  });
  // 点击通知唤起主窗口，方便回到聊天
  notif.on('click', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (!mainWindow.isVisible()) mainWindow.show();
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  notif.show();
  return { success: true, suppressed: false };
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

  // 应用网络代理配置（http/https，来自 network.proxy）
  await applyNetworkProxy().catch((e) => console.warn('[proxy] 初始应用失败:', e.message));

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
    // 注册快速提问全局快捷键（配置来自 pet.quickAsk.shortcut）
    applyQuickAskShortcut();
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
    if (pythonProcess) {
      stopPythonService();
    }
    app.quit();
  }
});

app.on('before-quit', async () => {
  app.isQuitting = true;
  globalShortcut.unregisterAll();
  if (pythonProcess) {
    stopPythonService();
  }
});
