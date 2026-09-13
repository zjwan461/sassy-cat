/**
 * 双层配置存储（设计稿 3.1 节）
 *  - 模板层: resources/config.json（只读默认值，随应用发布/升级覆盖）
 *  - 用户层: userData/config.user.json（可写，原子写，存全部用户配置）
 *
 * 对外暴露合并视图；写入只落用户层；支持点路径局部更新与变更订阅。
 */
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function deepMerge(base, override) {
  const result = { ...base };
  for (const [key, value] of Object.entries(override || {})) {
    if (isPlainObject(value) && isPlainObject(result[key])) {
      result[key] = deepMerge(result[key], value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

function setByPath(obj, dottedPath, value) {
  const parts = dottedPath.split('.');
  let node = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    if (!isPlainObject(node[p])) node[p] = {};
    node = node[p];
  }
  node[parts[parts.length - 1]] = value;
}

function getByPath(obj, dottedPath) {
  return dottedPath.split('.').reduce((acc, key) => (acc == null ? undefined : acc[key]), obj);
}

/** apiKey 等敏感字段掩码：仅保留末 3 位 */
function maskSecrets(data) {
  const clone = JSON.parse(JSON.stringify(data));
  const profiles = clone?.llm?.profiles;
  if (isPlainObject(profiles)) {
    for (const p of Object.values(profiles)) {
      if (typeof p.apiKey === 'string' && p.apiKey.length > 0) {
        const tail = p.apiKey.slice(-3);
        p.apiKey = `***${tail}`;
        p.apiKeyMasked = true;
      }
    }
  }
  const ragKey = clone?.rag?.embeddingModel?.apiKey;
  if (typeof ragKey === 'string' && ragKey.length > 0) {
    clone.rag.embeddingModel.apiKey = `***${ragKey.slice(-3)}`;
    clone.rag.embeddingModel.apiKeyMasked = true;
  }
  return clone;
}

class ConfigStore extends EventEmitter {
  /**
   * @param {string} templatePath 模板 config.json 路径
   * @param {string} userPath     用户 config.user.json 路径
   */
  constructor(templatePath, userPath) {
    super();
    this.templatePath = templatePath;
    this.userPath = userPath;
    this.template = {};
    this.user = {};
    this.load();
  }

  load() {
    try {
      if (fs.existsSync(this.templatePath)) {
        this.template = JSON.parse(fs.readFileSync(this.templatePath, 'utf-8'));
      }
    } catch (e) {
      console.warn('[config-store] 模板解析失败:', e.message);
    }
    try {
      if (fs.existsSync(this.userPath)) {
        this.user = JSON.parse(fs.readFileSync(this.userPath, 'utf-8'));
      }
    } catch (e) {
      console.warn('[config-store] 用户配置解析失败，使用空配置:', e.message);
      this.user = {};
    }
  }

  get merged() {
    return deepMerge(this.template, this.user);
  }

  /** 读取合并后的完整配置（敏感字段掩码后返回给渲染层展示） */
  getMasked() {
    return maskSecrets(this.merged);
  }

  /**
   * 局部更新（点路径）。value 为 undefined 时删除该键。
   * 返回 { success, diff } 或 { success:false, message }
   */
  setByDotted(pathDotted, value) {
    if (!pathDotted || typeof pathDotted !== 'string') {
      return { success: false, message: '无效的配置路径' };
    }
    try {
      setByPath(this.user, pathDotted, value);
      this._persist();
      const diff = {};
      diff[pathDotted] = value;
      this.emit('changed', { diff, config: this.merged });
      return { success: true };
    } catch (e) {
      return { success: false, message: e.message };
    }
  }

  /** 批量更新：patches = [{ path, value }]，单次写入落盘 */
  applyPatches(patches) {
    try {
      for (const { path: p, value } of patches || []) {
        setByPath(this.user, p, value);
      }
      this._persist();
      const diff = {};
      for (const { path: p, value } of patches || []) diff[p] = value;
      this.emit('changed', { diff, config: this.merged });
      return { success: true };
    } catch (e) {
      return { success: false, message: e.message };
    }
  }

  /** 原子写：临时文件 + rename */
  _persist() {
    const dir = path.dirname(this.userPath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const tmp = this.userPath + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(this.user, null, 2), 'utf-8');
    fs.renameSync(tmp, this.userPath);
  }
}

module.exports = { ConfigStore, deepMerge, getByPath, setByPath, maskSecrets };
