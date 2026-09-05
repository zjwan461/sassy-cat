const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const { EventEmitter } = require('events');

/**
 * Python环境检查器
 * 负责检测、安装和配置Python运行环境
 */
class PythonEnvChecker extends EventEmitter {
  constructor(app, getAssetPath) {
    super();
    this.app = app;
    this.getAssetPath = getAssetPath;

    // 从项目根目录 config.json 读取 Python 版本配置，默认 3.11.9
    const config = this.loadConfig();
    this.pythonVersion = config.pythonVersion || '3.11.9';
    // 从完整版本号推导主次版本（如 '3.11.9' -> '3.11'）
    const versionParts = this.pythonVersion.split('.');
    this.pythonMajorMinor = `${versionParts[0]}.${versionParts[1]}`;

    this.venvPath = null;
    this.pythonPath = null;
    this.pipPath = null;
    this.embeddedPythonDir = null;
    this.usedEmbeddedEnv = false;
  }

  /**
   * 加载配置文件（config.json），不存在或解析失败时返回默认配置
   */
  loadConfig() {
    const defaultConfig = { pythonVersion: '3.11.9' };
    try {
      const configPath = path.join(this.getAssetPath('.'), 'config.json');
      if (fs.existsSync(configPath)) {
        const raw = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
        if (raw && typeof raw.pythonVersion === 'string' && /^\d+\.\d+(\.\d+)?$/.test(raw.pythonVersion.trim())) {
          return { ...defaultConfig, ...raw, pythonVersion: raw.pythonVersion.trim() };
        }
      }
    } catch (e) {
      // 配置解析失败时使用默认配置
    }
    return defaultConfig;
  }

  /**
   * python_env 目录是否存在（打包环境下为 resources/python_env）
   */
  embeddedEnvExists() {
    const embeddedDir = path.join(this.getProjectRoot(), 'python_env');
    return fs.existsSync(embeddedDir);
  }

  /**
   * 构造带修复建议的错误信息
   */
  buildErrorWithHint(rawMessage) {
    const lines = [rawMessage];
    if (this.usedEmbeddedEnv || this.embeddedEnvExists()) {
      lines.push('');
      lines.push('修复建议：请删除 python_env 文件夹后重启本程序，系统将自动重新配置环境。');
    }
    return lines.join('\n');
  }

  /**
   * 获取项目根目录
   */
  getProjectRoot() {
    return this.getAssetPath('.');
  }

  /**
   * 获取虚拟环境路径
   */
  getVenvPath() {
    if (!this.venvPath) {
      this.venvPath = path.join(this.getProjectRoot(), '.venv');
    }
    return this.venvPath;
  }

  /**
   * 获取Python解释器路径
   */
  getPythonPath() {
    if (!this.pythonPath) {
      if (this.embeddedPythonDir) {
        this.pythonPath = path.join(this.embeddedPythonDir, 'python.exe');
      } else {
        const venvPath = this.getVenvPath();
        if (process.platform === 'win32') {
          this.pythonPath = path.join(venvPath, 'Scripts', 'python.exe');
        } else {
          this.pythonPath = path.join(venvPath, 'bin', 'python');
        }
      }
    }
    return this.pythonPath;
  }

  /**
   * 获取pip路径
   */
  getPipPath() {
    if (!this.pipPath) {
      if (this.embeddedPythonDir) {
        if (process.platform === 'win32') {
          this.pipPath = path.join(this.embeddedPythonDir, 'Scripts', 'pip.exe');
        } else {
          this.pipPath = path.join(this.embeddedPythonDir, 'bin', 'pip');
        }
      } else {
        const venvPath = this.getVenvPath();
        if (process.platform === 'win32') {
          this.pipPath = path.join(venvPath, 'Scripts', 'pip.exe');
        } else {
          this.pipPath = path.join(venvPath, 'bin', 'pip');
        }
      }
    }
    return this.pipPath;
  }

  /**
   * 检查虚拟环境是否存在
   */
  checkVenvExists() {
    // 优先检查嵌入式Python是否已配置
    const embeddedDir = path.join(this.getProjectRoot(), 'python_env');
    const embeddedPython = path.join(embeddedDir, 'python.exe');
    
    if (fs.existsSync(embeddedPython)) {
      this.emit('log', `✅ 嵌入式Python已存在: ${embeddedDir}`);
      this.embeddedPythonDir = embeddedDir;
      this.pythonPath = embeddedPython;
      this.usedEmbeddedEnv = true;
      return true;
    }

    const venvPath = this.getVenvPath();
    const pythonPath = this.getPythonPath();
    
    this.emit('log', `检查虚拟环境: ${venvPath}`);
    
    if (fs.existsSync(venvPath) && fs.existsSync(pythonPath)) {
      this.emit('log', '✅ 虚拟环境已存在');
      return true;
    }
    
    this.emit('log', '❌ 虚拟环境不存在');
    return false;
  }

  /**
   * 检查依赖是否已安装
   */
  checkDependenciesInstalled() {
    return new Promise((resolve) => {
      const pythonPath = this.getPythonPath();
      const requirementsPath = this.getAssetPath('requirements.txt');
      
      this.emit('log', '检查依赖安装状态...');
      
      if (!fs.existsSync(requirementsPath)) {
        this.emit('log', '❌ requirements.txt 不存在');
        resolve(false);
        return;
      }

      const requirements = fs.readFileSync(requirementsPath, 'utf-8')
        .split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('#'));

      if (requirements.length === 0) {
        this.emit('log', '✅ requirements.txt 为空，无需安装依赖');
        resolve(true);
        return;
      }

      const pipProcess = spawn(pythonPath, ['-m', 'pip', 'list', '--format=freeze'], {
        cwd: this.getProjectRoot(),
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
      });

      let installedPackages = '';
      let errorOutput = '';

      pipProcess.stdout.on('data', (data) => {
        installedPackages += data.toString();
      });

      pipProcess.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      pipProcess.on('close', (code) => {
        if (code !== 0) {
          this.emit('log', `❌ pip list 执行失败: ${errorOutput}`);
          resolve(false);
          return;
        }

        const installed = new Map();
        const lines = installedPackages.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
        
        lines.forEach(line => {
          const match = line.match(/^([a-zA-Z0-9][a-zA-Z0-9._-]*)([><=!~]+.+)?$/);
          if (match) {
            const pkgName = match[1].toLowerCase().replace(/[-.]/g, '_');
            installed.set(pkgName, match[2] || '');
          }
        });

        this.emit('log', `[DEBUG] 已安装包数量: ${installed.size}`);
        this.emit('log', `[DEBUG] 需要检查: ${requirements.join(', ')}`);

        let allInstalled = true;
        for (const req of requirements) {
          const match = req.match(/^([a-zA-Z0-9][a-zA-Z0-9._-]*)([><=!~]=?.+)?$/);
          if (!match) {
            this.emit('log', `⚠️ 无法解析需求: "${req}"`);
            continue;
          }
          
          const rawName = match[1];
          const normalized = rawName.toLowerCase().replace(/[-.]/g, '_');
          
          const found = installed.has(normalized);
          
          if (found) {
            this.emit('log', `✅ 已安装: ${rawName}`);
          } else {
            this.emit('log', `❌ 缺少依赖: ${rawName}`);
            allInstalled = false;
          }
        }

        resolve(allInstalled);
      });

      pipProcess.on('error', (err) => {
        this.emit('log', `❌ pip list 执行错误: ${err.message}`);
        resolve(false);
      });
    });
  }

  /**
   * 安装依赖
   */
  installDependencies() {
    return new Promise((resolve, reject) => {
      const pythonPath = this.getPythonPath();
      const requirementsPath = this.getAssetPath('requirements.txt');

      this.emit('log', '开始安装依赖...');
      this.emit('progress', '正在安装Python依赖...');

      const pipProcess = spawn(pythonPath, ['-m', 'pip', 'install', '-r', requirementsPath], {
        cwd: this.getProjectRoot(),
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
      });

      let output = '';
      let errorOutput = '';

      pipProcess.stdout.on('data', (data) => {
        const text = data.toString();
        output += text;
        this.emit('log', text);
      });

      pipProcess.stderr.on('data', (data) => {
        const text = data.toString();
        errorOutput += text;
        this.emit('log', text);
      });

      pipProcess.on('close', (code) => {
        if (code === 0) {
          this.emit('log', '✅ 依赖安装成功');
          resolve(true);
        } else {
          this.emit('log', `❌ 依赖安装失败 (code: ${code})`);
          reject(new Error(`依赖安装失败: ${errorOutput}`));
        }
      });

      pipProcess.on('error', (err) => {
        this.emit('log', `❌ pip install 执行错误: ${err.message}`);
        reject(err);
      });
    });
  }

  /**
   * 检查系统Python是否存在
   */
  checkSystemPython() {
    return new Promise((resolve) => {
      this.emit('log', `检查系统Python ${this.pythonMajorMinor}...`);

      const commands = process.platform === 'win32'
        ? ['python', 'python3', 'py']
        : [`python${this.pythonMajorMinor}`, 'python3', 'python'];

      let found = false;
      let pythonCommand = null;

      const checkNext = (index) => {
        if (index >= commands.length) {
          resolve({ found: false, command: null, version: null });
          return;
        }

        const cmd = commands[index];
        const args = ['--version'];
        
        const proc = spawn(cmd, args, {
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });

        let versionOutput = '';

        proc.stdout.on('data', (data) => {
          versionOutput += data.toString();
        });

        proc.stderr.on('data', (data) => {
          versionOutput += data.toString();
        });

        proc.on('close', (code) => {
          if (code === 0) {
            const match = versionOutput.match(/Python\s+(\d+\.\d+)/);
            if (match) {
              const majorMinor = match[1];
              // 接受 3.10 及以上版本
              const [, major, minor] = majorMinor.match(/(\d+)\.(\d+)/);
              if (parseInt(major) >= 3 && parseInt(minor) >= 10) {
                this.emit('log', `✅ 找到Python ${majorMinor}: ${cmd}`);
                resolve({ found: true, command: cmd, version: majorMinor });
                return;
              }
            }
          }
          checkNext(index + 1);
        });

        proc.on('error', () => {
          checkNext(index + 1);
        });
      };

      checkNext(0);
    });
  }

  /**
   * 创建虚拟环境
   */
  createVenv(pythonCommand = 'python') {
    return new Promise((resolve, reject) => {
      const venvPath = this.getVenvPath();
      
      this.emit('log', `创建虚拟环境: ${venvPath}`);
      this.emit('progress', '正在创建Python虚拟环境...');

      const proc = spawn(pythonCommand, ['-m', 'venv', venvPath], {
        cwd: this.getProjectRoot(),
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
      });

      let output = '';
      let errorOutput = '';

      proc.stdout.on('data', (data) => {
        const text = data.toString();
        output += text;
        this.emit('log', text);
      });

      proc.stderr.on('data', (data) => {
        const text = data.toString();
        errorOutput += text;
        this.emit('log', text);
      });

      proc.on('close', (code) => {
        if (code === 0) {
          this.emit('log', '✅ 虚拟环境创建成功');
          resolve(true);
        } else {
          this.emit('log', `❌ 虚拟环境创建失败 (code: ${code})`);
          reject(new Error(`虚拟环境创建失败: ${errorOutput}`));
        }
      });

      proc.on('error', (err) => {
        this.emit('log', `❌ venv 执行错误: ${err.message}`);
        reject(err);
      });
    });
  }

  /**
   * 下载Python嵌入式版本
   */
  downloadPython() {
    return new Promise((resolve, reject) => {
      const pythonDir = path.join(this.getProjectRoot(), 'python_env');
      const pythonZipPath = path.join(pythonDir, `python-${this.pythonVersion}-embed-amd64.zip`);
      
      const downloadUrl = `https://www.python.org/ftp/python/${this.pythonVersion}/python-${this.pythonVersion}-embed-amd64.zip`;
      
      this.emit('log', `准备下载Python ${this.pythonVersion}...`);
      this.emit('progress', `正在下载Python ${this.pythonVersion}...`);

      if (!fs.existsSync(pythonDir)) {
        fs.mkdirSync(pythonDir, { recursive: true });
      }

      const file = fs.createWriteStream(pythonZipPath);
      const protocol = downloadUrl.startsWith('https') ? https : http;

      const request = protocol.get(downloadUrl, (response) => {
        if (response.statusCode !== 200) {
          reject(new Error(`下载失败: HTTP ${response.statusCode}`));
          return;
        }

        const totalSize = parseInt(response.headers['content-length'], 10);
        let downloadedSize = 0;

        response.on('data', (chunk) => {
          downloadedSize += chunk.length;
          const percent = ((downloadedSize / totalSize) * 100).toFixed(1);
          this.emit('progress', `下载进度: ${percent}%`);
        });

        response.pipe(file);

        file.on('finish', () => {
          file.close();
          this.emit('log', '✅ Python下载完成');
          resolve({ zipPath: pythonZipPath, extractDir: pythonDir });
        });
      });

      request.on('error', (err) => {
        fs.unlink(pythonZipPath, () => {});
        reject(new Error(`下载失败: ${err.message}`));
      });

      request.setTimeout(300000, () => {
        request.destroy();
        fs.unlink(pythonZipPath, () => {});
        reject(new Error('下载超时'));
      });
    });
  }

  /**
   * 解压Python
   */
  async extractPython(zipPath, extractDir) {
    this.emit('log', '解压Python...');
    this.emit('progress', '正在解压Python...');

    return new Promise((resolve, reject) => {
      const proc = spawn('powershell', [
        '-Command',
        `Expand-Archive -Path "${zipPath}" -DestinationPath "${extractDir}" -Force`
      ], {
        cwd: this.getProjectRoot()
      });

      let errorOutput = '';

      proc.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      proc.on('close', (code) => {
        if (code === 0) {
          fs.unlink(zipPath, () => {});
          this.emit('log', '✅ Python解压完成');
          resolve(true);
        } else {
          reject(new Error(`解压失败: ${errorOutput}`));
        }
      });

      proc.on('error', (err) => {
        reject(err);
      });
    });
  }

  /**
   * 配置嵌入式Python以支持pip
   */
  async configureEmbeddedPython(pythonDir) {
    this.emit('log', '配置嵌入式Python...');
    this.emit('progress', '正在配置Python环境...');

    const pthFile = path.join(pythonDir, `python${this.pythonMajorMinor.replace('.', '')}._pth`);
    
    if (fs.existsSync(pthFile)) {
      let content = fs.readFileSync(pthFile, 'utf-8');
      content = content.replace('#import site', 'import site');
      fs.writeFileSync(pthFile, content);
      this.emit('log', '✅ 已启用site模块');
    }

    const getPipPath = path.join(pythonDir, 'get-pip.py');
    const getPipUrl = 'https://bootstrap.pypa.io/get-pip.py';

    return new Promise((resolve, reject) => {
      const file = fs.createWriteStream(getPipPath);
      const protocol = getPipUrl.startsWith('https') ? https : http;

      const request = protocol.get(getPipUrl, (response) => {
        if (response.statusCode !== 200) {
          reject(new Error(`下载get-pip.py失败: HTTP ${response.statusCode}`));
          return;
        }

        response.pipe(file);

        file.on('finish', () => {
          file.close();
          this.emit('log', '✅ get-pip.py下载完成');
          
          const pythonExe = path.join(pythonDir, 'python.exe');
          const proc = spawn(pythonExe, [getPipPath], {
            cwd: pythonDir,
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
          });

          let output = '';
          let errorOutput = '';

          proc.stdout.on('data', (data) => {
            output += data.toString();
            this.emit('log', data.toString());
          });

          proc.stderr.on('data', (data) => {
            errorOutput += data.toString();
            this.emit('log', data.toString());
          });

          proc.on('close', (code) => {
            fs.unlink(getPipPath, () => {});
            
            if (code === 0) {
              this.emit('log', '✅ pip安装完成');
              resolve(true);
            } else {
              reject(new Error(`pip安装失败: ${errorOutput}`));
            }
          });

          proc.on('error', (err) => {
            reject(err);
          });
        });
      });

      request.on('error', (err) => {
        fs.unlink(getPipPath, () => {});
        reject(new Error(`下载get-pip.py失败: ${err.message}`));
      });
    });
  }

  /**
   * 延迟函数，确保UI有时间更新
   */
  async delay(ms = 100) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * 主检查流程
   */
  async checkAndSetup() {
    try {
      // 步骤1: 检查虚拟环境
      this.emit('step', '检查虚拟环境');
      await this.delay(300);
      
      const venvExists = this.checkVenvExists();

      if (venvExists) {
        await this.delay(500);
        this.emit('step-done', '检查虚拟环境');
        await this.delay(300);

        // 步骤2: 检查依赖
        this.emit('step', '检查依赖安装');
        await this.delay(300);
        
        const depsInstalled = await this.checkDependenciesInstalled();
        
        if (!depsInstalled) {
          await this.installDependencies();
        }
        
        await this.delay(500);
        this.emit('step-done', '检查依赖安装');
        await this.delay(300);
        
        this.emit('complete', { success: true, pythonPath: this.getPythonPath() });
        return { success: true, pythonPath: this.getPythonPath() };
      }

      await this.delay(500);
      this.emit('step-done', '检查虚拟环境');
      await this.delay(300);

      // 步骤3: 检查系统Python
      this.emit('step', '检查Python');
      await this.delay(300);
      
      const pythonCheck = await this.checkSystemPython();

      if (pythonCheck.found) {
        await this.delay(500);
        this.emit('step-done', '检查Python');
        await this.delay(300);

        // 创建虚拟环境
        this.emit('step', '创建虚拟环境');
        await this.delay(300);
        await this.createVenv(pythonCheck.command);
        await this.delay(500);
        this.emit('step-done', '创建虚拟环境');
        await this.delay(300);
        
        // 安装依赖
        this.emit('step', '安装依赖');
        await this.delay(300);
        await this.installDependencies();
        await this.delay(500);
        this.emit('step-done', '安装依赖');
        await this.delay(300);
        
        this.emit('complete', { success: true, pythonPath: this.getPythonPath() });
        return { success: true, pythonPath: this.getPythonPath() };
      }

      await this.delay(500);
      this.emit('step-done', '检查Python');
      await this.delay(300);

      // 步骤4: 下载Python
      this.emit('step', '下载Python');
      await this.delay(300);
      const { zipPath, extractDir } = await this.downloadPython();
      await this.delay(500);
      this.emit('step-done', '下载Python');
      await this.delay(300);
      
      // 解压Python
      this.emit('step', '解压Python');
      await this.delay(300);
      await this.extractPython(zipPath, extractDir);
      await this.delay(500);
      this.emit('step-done', '解压Python');
      await this.delay(300);
      
      // 配置嵌入式Python
      this.emit('step', '配置Python环境');
      await this.delay(300);
      await this.configureEmbeddedPython(extractDir);
      await this.delay(500);
      this.emit('step-done', '配置Python环境');
      await this.delay(300);
      
      this.embeddedPythonDir = extractDir;
      this.pythonPath = path.join(extractDir, 'python.exe');
      this.usedEmbeddedEnv = true;
      
      this.emit('log', '✅ 使用嵌入式Python（跳过虚拟环境创建）');
      await this.delay(300);
      
      // 安装依赖
      this.emit('step', '安装依赖');
      await this.delay(300);
      await this.installDependencies();
      await this.delay(500);
      this.emit('step-done', '安装依赖');
      await this.delay(300);
      
      this.emit('complete', { success: true, pythonPath: this.getPythonPath() });
      return { success: true, pythonPath: this.getPythonPath() };
    } catch (error) {
      const message = this.buildErrorWithHint(error.message);
      this.emit('log', `❌ ${message}`);
      this.emit('error', message);
      return { success: false, error: message };
    }
  }
}

module.exports = PythonEnvChecker;
