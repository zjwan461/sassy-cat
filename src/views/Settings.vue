<template>
  <div class="page settings-page">
    <header class="page-header">
      <h1 class="page-title">设置</h1>
      <p class="page-subtitle">模型连接与人设配置，保存后热生效</p>
    </header>

    <!-- 全局操作 -->
    <div class="global-actions">
      <button class="btn primary" @click="saveAll">保存设置</button>
      <button class="btn warn" @click="restartAgent">重启服务进程</button>
    </div>

    <div class="settings-grid">
    <!-- 模型连接 -->
    <section class="card">
      <div class="card-header">模型连接</div>
      <div class="card-body form">
        <div class="field">
          <label>配置档</label>
          <div class="profile-row">
            <select :value="activeProfile" @change="switchProfile($event.target.value)">
              <option v-for="(p, name) in profiles" :key="name" :value="name">{{ p.label || name }}</option>
            </select>
            <button class="btn" @click="showAddProfile = true" title="新增配置档">＋ 新增</button>
            <button class="btn warn" @click="deleteProfile" :disabled="activeProfile === 'default'" title="删除当前配置档（default 不可删除）"> 删除</button>
          </div>
        </div>
        <div class="field">
          <label>Provider</label>
          <select v-model="form.provider">
            <option value="openai">OpenAI‑Compatible</option>
            <option value="deepseek">DeepSeek-Compatible</option>
          </select>
          <span class="hint">OpenAI: reasoning 放在 content 中；DeepSeek: reasoning 放在 reasoning_content 中</span>
        </div>
        <div class="field">
          <label>Base URL</label>
          <input v-model="form.baseUrl" placeholder="http://localhost:8080/v1" />
        </div>
        <div class="field">
          <label>API Key</label>
          <div class="key-row">
            <input v-model="form.apiKey" :type="showKey ? 'text' : 'password'" placeholder="sk-..." @focus="revealKey" />
            <button class="mini" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button>
          </div>
        </div>
        <div class="field">
          <label>模型名称</label>
          <input v-model="form.model" placeholder="Qwen3.6-35B" />
        </div>
        <div class="field">
          <label>额外参数（JSON）</label>
          <textarea v-model="form.extraParamsText" rows="3" class="mono" @input="validateExtra"></textarea>
          <span class="hint" :class="{ bad: extraError }">{{ extraError || '例如 {"temperature": 0.7}' }}</span>
        </div>
        <div class="actions">
          <button class="btn" @click="testConnection" :disabled="testing">{{ testing ? '测试中…' : '测试连接' }}</button>
          <span v-if="testResult" :class="testResult.ok ? 'ok' : 'bad-text'">{{ testResult.text }}</span>
        </div>
      </div>
    </section>

    <!-- Agent 配置 -->
    <section class="card">
      <div class="card-header">Agent 配置</div>
      <div class="card-body form">
        <div class="field">
          <label>配置档</label>
          <div class="profile-row">
            <select :value="activeAgentProfile" @change="switchAgentProfile($event.target.value)">
              <option v-for="(p, name) in agentProfiles" :key="name" :value="name">{{ p.label || name }}</option>
            </select>
            <button class="btn" @click="showAddAgentProfile = true" title="新增 Agent 配置档">＋ 新增</button>
            <button class="btn warn" @click="deleteAgentProfile" :disabled="activeAgentProfile === 'default'" title="删除当前 Agent 配置档（default 不可删除）"> 删除</button>
          </div>
        </div>
        <div class="field">
          <label>人设提示词（可编辑，留空使用默认傲娇猫咪人设）</label>
          <textarea v-model="form.persona" rows="10" class="mono persona"
            placeholder="你是「臭屁猫」……（支持 {app_name} {time} {os_user} 变量）"></textarea>
          <span class="hint">{{ form.persona.length }} 字</span>
        </div>
        <div class="field">
          <label>记忆窗口（条）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('memoryWindow', -1, 2, 500)" :disabled="form.memoryWindow <= 2">−</button>
            <input type="number" v-model.number="form.memoryWindow" min="2" max="500" class="step-input"
              @blur="clamp('memoryWindow', 2, 500, 50)" />
            <button type="button" class="step-btn" @click="step('memoryWindow', 1, 2, 500)" :disabled="form.memoryWindow >= 500">+</button>
          </div>
          <span class="hint">对话上下文保留的最近消息条数，超出后自动裁剪（默认 50）</span>
        </div>
        <div class="field">
          <label>递归上限（步）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('recursionLimit', -1, 1, 200)" :disabled="form.recursionLimit <= 1">−</button>
            <input type="number" v-model.number="form.recursionLimit" min="1" max="200" class="step-input"
              @blur="clamp('recursionLimit', 1, 200, 50)" />
            <button type="button" class="step-btn" @click="step('recursionLimit', 1, 1, 200)" :disabled="form.recursionLimit >= 200">+</button>
          </div>
          <span class="hint">单轮对话 Agent 可执行的最大步数（含工具调用），过小会提前中断（默认 50）</span>
        </div>
        <div class="actions">
          <button class="btn" @click="togglePreview">{{ preview ? '隐藏完整提示词' : '预览完整提示词' }}</button>
          <button class="btn" @click="resetPersona">恢复默认人设</button>
        </div>
        <pre v-if="preview" class="preview-box">{{ preview }}</pre>
      </div>
    </section>

    <!-- 闲置提醒 -->
    <section class="card">
      <div class="card-header">闲置提醒</div>
      <div class="card-body form inline">
        <label class="check"><input type="checkbox" v-model="form.idleEnabled" /> 启用</label>
        <label>闲置阈值（分钟）<input type="number" v-model.number="form.idleThreshold" min="1" class="num" /></label>
        <label>提醒冷却（分钟）<input type="number" v-model.number="form.idleQuiet" min="1" class="num" /></label>
      </div>
    </section>

    <!-- 桌宠 -->
    <section class="card">
      <div class="card-header">桌宠</div>
      <div class="card-body form">
        <div class="field">
          <label>快速提问快捷键（全局生效，唤起桌宠输入框）</label>
          <div class="hotkey-row">
            <div
              class="hotkey-box" :class="{ recording: recordingKey, bad: hotkeyError }"
              tabindex="0" title="点击后按下组合键进行录制"
              @click="startRecord" @blur="stopRecord"
              @keydown.prevent="onRecordKeydown"
            >{{ hotkeyDisplay }}</div>
            <button v-if="form.quickAskShortcut" class="mini" @click="form.quickAskShortcut = ''">禁用</button>
          </div>
          <span class="hint" :class="{ bad: hotkeyError }">
            {{ hotkeyError || (recordingKey ? '请按下组合键（需包含 Ctrl / Alt / Shift / Win），Esc 取消' : '例如 Alt+Shift+Q；留空表示禁用') }}
          </span>
          <span v-if="hotkeyStatus" :class="hotkeyStatus.ok ? 'ok' : 'bad-text'">{{ hotkeyStatus.text }}</span>
        </div>
      </div>
    </section>
    </div>

    <div v-if="toast" class="toast">{{ toast }}</div>

    <!-- 新增 LLM 配置档弹窗 -->
    <div v-if="showAddProfile" class="modal-overlay" @click.self="showAddProfile = false">
      <div class="modal">
        <h3>新增 LLM 配置档</h3>
        <div class="field">
          <label>配置档名称</label>
          <input v-model="newProfileName" placeholder="例如 work、personal" @keydown.enter="addProfile" ref="profileNameInput" />
          <span class="hint" :class="{ bad: newProfileError }">{{ newProfileError || '仅允许字母、数字、下划线和短横线' }}</span>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showAddProfile = false">取消</button>
          <button class="btn primary" @click="addProfile">确定</button>
        </div>
      </div>
    </div>

    <!-- 新增 Agent 配置档弹窗 -->
    <div v-if="showAddAgentProfile" class="modal-overlay" @click.self="showAddAgentProfile = false">
      <div class="modal">
        <h3>新增 Agent 配置档</h3>
        <div class="field">
          <label>配置档名称</label>
          <input v-model="newAgentProfileName" placeholder="例如 work、personal" @keydown.enter="addAgentProfile" ref="agentProfileNameInput" />
          <span class="hint" :class="{ bad: newAgentProfileError }">{{ newAgentProfileError || '仅允许字母、数字、下划线和短横线' }}</span>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showAddAgentProfile = false">取消</button>
          <button class="btn primary" @click="addAgentProfile">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, nextTick, watch } from 'vue'
import { useAgentSocket } from '../composables/useAgentSocket'

const { connect, send, on } = useAgentSocket()
const api = window.electronAPI

const activeProfile = ref('default')
const profiles = ref({})
const activeAgentProfile = ref('default')
const agentProfiles = ref({})
const form = reactive({
  provider: 'openai', baseUrl: '', apiKey: '', model: '', extraParamsText: '{}',
  persona: '', memoryWindow: 50, recursionLimit: 50, idleEnabled: true, idleThreshold: 30, idleQuiet: 10,
  quickAskShortcut: 'Alt+Shift+Q'
})
const recordingKey = ref(false)
const hotkeyError = ref('')
const hotkeyStatus = ref(null)
const showKey = ref(false)
const extraError = ref('')
const testing = ref(false)
const testResult = ref(null)
const preview = ref('')
const toast = ref('')
const keyRevealed = ref(false)
const showAddProfile = ref(false)
const newProfileName = ref('')
const newProfileError = ref('')
const profileNameInput = ref(null)
const showAddAgentProfile = ref(false)
const newAgentProfileName = ref('')
const newAgentProfileError = ref('')
const agentProfileNameInput = ref(null)

// 弹窗打开时自动聚焦输入框
// 弹窗打开时自动聚焦输入框
watch(showAddProfile, (val) => {
  if (val) {
    newProfileName.value = ''
    newProfileError.value = ''
    nextTick(() => profileNameInput.value?.focus())
  }
})
watch(showAddAgentProfile, (val) => {
  if (val) {
    newAgentProfileName.value = ''
    newAgentProfileError.value = ''
    nextTick(() => agentProfileNameInput.value?.focus())
  }
})
function showToast(text) {
  toast.value = text
  setTimeout(() => (toast.value = ''), 2500)
}

function validateExtra() {
  try { JSON.parse(form.extraParamsText || '{}'); extraError.value = '' }
  catch (e) { extraError.value = 'JSON 格式错误' }
}

function clamp(key, min, max, fallback) {
  const v = Number(form[key])
  if (!Number.isFinite(v)) { form[key] = fallback; return }
  form[key] = Math.min(max, Math.max(min, Math.round(v)))
}

function step(key, delta, min, max) {
  const cur = Number(form[key])
  const base = Number.isFinite(cur) ? cur : min
  form[key] = Math.min(max, Math.max(min, base + delta))
}

async function loadConfig() {
  const res = await api.getConfig()
  if (!res.success) return showToast('配置加载失败')
  const cfg = res.config
  profiles.value = cfg.llm?.profiles || { default: { label: '默认' } }
  activeProfile.value = cfg.llm?.activeProfile || 'default'
  agentProfiles.value = cfg.agent?.profiles || { default: { label: '默认' } }
  activeAgentProfile.value = cfg.agent?.activeProfile || 'default'
  fillFormFromProfile()
  form.idleEnabled = cfg.pet?.idleReminder?.enabled !== false
  form.idleThreshold = cfg.pet?.idleReminder?.thresholdMinutes ?? 30
  form.idleQuiet = cfg.pet?.idleReminder?.quietPeriodMinutes ?? 10
  form.quickAskShortcut = cfg.pet?.quickAsk?.shortcut ?? 'Alt+Shift+Q'
}

// ---------- 快捷键录制 ----------
const hotkeyDisplay = computed(() => {
  if (recordingKey.value) return '按下组合键…'
  return form.quickAskShortcut || '未设置（已禁用）'
})

// KeyboardEvent -> Electron accelerator 字符串
function eventToAccelerator(e) {
  const mods = []
  if (e.ctrlKey) mods.push('Ctrl')
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  if (e.metaKey) mods.push('Super')
  const KEY_MAP = {
    Control: 'Ctrl', Alt: 'Alt', Shift: 'Shift', Meta: 'Super',
    ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
    ' ': 'Space', Escape: 'Esc', Delete: 'Delete', Backspace: 'Backspace',
    PageUp: 'PageUp', PageDown: 'PageDown', Home: 'Home', End: 'End', Insert: 'Insert'
  }
  let key = KEY_MAP[e.key]
  if (!key) {
    if (e.key.length === 1) {
      key = e.key.toUpperCase()
    } else if (/^F\d{1,2}$/.test(e.key)) {
      key = e.key
    } else {
      return null // 不支持的键（如 CapsLock、输入法键等）
    }
  }
  if (mods.includes(key)) return null // 纯修饰键组合无效
  if (!mods.length) {
    hotkeyError.value = '快捷键必须包含至少一个修饰键（Ctrl / Alt / Shift / Win）'
    return null
  }
  hotkeyError.value = ''
  return [...mods, key].join('+')
}

function startRecord() {
  recordingKey.value = true
  hotkeyError.value = ''
}

function stopRecord() {
  recordingKey.value = false
  hotkeyError.value = ''
}

async function onRecordKeydown(e) {
  if (!recordingKey.value) return
  if (e.key === 'Escape') { stopRecord(); return }
  const acc = eventToAccelerator(e)
  if (!acc) return
  recordingKey.value = false
  // 立即保存并等待主进程注册结果（注册失败时可再次录制换键）
  const res = await api.setConfig('pet.quickAsk.shortcut', acc)
  if (!res.success) return showToast('保存失败: ' + (res.message || ''))
  form.quickAskShortcut = acc
  showToast('快捷键已保存，正在注册…')
}

function fillFormFromProfile() {
  const p = profiles.value[activeProfile.value] || {}
  form.provider = p.provider || 'openai'
  form.baseUrl = p.baseUrl || ''
  form.apiKey = p.apiKey || '' // 掩码值 ***abc
  form.model = p.model || ''
  form.extraParamsText = JSON.stringify(p.extraParams || {}, null, 2)
  keyRevealed.value = false
  validateExtra()
  // Agent 配置从独立的 agent profile 读取
  const ap = agentProfiles.value[activeAgentProfile.value] || {}
  form.persona = ap.persona || ''
  form.memoryWindow = ap.memoryWindow ?? 50
  form.recursionLimit = ap.recursionLimit ?? 50
}

async function switchProfile(name) {
  activeProfile.value = name
  await api.setConfig('llm.activeProfile', name)
  fillFormFromProfile()
}

async function switchAgentProfile(name) {
  activeAgentProfile.value = name
  await api.setConfig('agent.activeProfile', name)
  fillFormFromProfile()
}

function validateProfileName(name, existingProfiles) {
  if (!name || !name.trim()) return '请输入配置档名称'
  if (!/^[a-zA-Z0-9_-]+$/.test(name.trim())) return '仅允许字母、数字、下划线和短横线'
  if (existingProfiles[name.trim()]) return '该配置档已存在'
  return ''
}

async function addProfile() {
  const name = newProfileName.value.trim()
  const err = validateProfileName(name, profiles.value)
  if (err) { newProfileError.value = err; return }
  const base = JSON.parse(JSON.stringify(profiles.value.default || { provider: 'openai', baseUrl: '', apiKey: '', model: '', extraParams: {} }))
  base.label = name
  const res = await api.setConfig(`llm.profiles.${name}`, base)
  if (!res.success) return showToast('新增配置档失败: ' + (res.message || ''))
  newProfileName.value = ''
  newProfileError.value = ''
  showAddProfile.value = false
  await loadConfig()
  await switchProfile(name)
  showToast(`已新增 LLM 配置档「${name}」`)
}

async function deleteProfile() {
  if (activeProfile.value === 'default') return showToast('default 配置档不可删除')
  if (!confirm(`确定要删除 LLM 配置档「${activeProfile.value}」吗？此操作不可撤销。`)) return
  const name = activeProfile.value
  const cfg = await api.getConfig()
  if (!cfg.success) return showToast('读取配置失败')
  const profilesCopy = JSON.parse(JSON.stringify(cfg.config.llm?.profiles || {}))
  delete profilesCopy[name]
  const res = await api.setConfig('llm.profiles', profilesCopy)
  if (!res.success) return showToast('删除配置档失败: ' + (res.message || ''))
  await loadConfig()
  await switchProfile('default')
  showToast(`已删除 LLM 配置档「${name}」`)
}

async function addAgentProfile() {
  const name = newAgentProfileName.value.trim()
  const err = validateProfileName(name, agentProfiles.value)
  if (err) { newAgentProfileError.value = err; return }
  const base = JSON.parse(JSON.stringify(agentProfiles.value.default || { persona: '', memoryWindow: 50, recursionLimit: 50 }))
  base.label = name
  const res = await api.setConfig(`agent.profiles.${name}`, base)
  if (!res.success) return showToast('新增 Agent 配置档失败: ' + (res.message || ''))
  newAgentProfileName.value = ''
  newAgentProfileError.value = ''
  showAddAgentProfile.value = false
  await loadConfig()
  await switchAgentProfile(name)
  showToast(`已新增 Agent 配置档「${name}」`)
}

async function deleteAgentProfile() {
  if (activeAgentProfile.value === 'default') return showToast('default Agent 配置档不可删除')
  if (!confirm(`确定要删除 Agent 配置档「${activeAgentProfile.value}」吗？此操作不可撤销。`)) return
  const name = activeAgentProfile.value
  const cfg = await api.getConfig()
  if (!cfg.success) return showToast('读取配置失败')
  const agentProfilesCopy = JSON.parse(JSON.stringify(cfg.config.agent?.profiles || {}))
  delete agentProfilesCopy[name]
  const res = await api.setConfig('agent.profiles', agentProfilesCopy)
  if (!res.success) return showToast('删除 Agent 配置档失败: ' + (res.message || ''))
  await loadConfig()
  await switchAgentProfile('default')
  showToast(`已删除 Agent 配置档「${name}」`)
}

async function revealKey() {
  if (keyRevealed.value) return
  const res = await api.getRawProfileKey(activeProfile.value)
  if (res.success) { form.apiKey = res.apiKey; keyRevealed.value = true }
}

async function saveAll() {
  validateExtra()
  if (extraError.value) return showToast('额外参数 JSON 无效，未保存')
  const llmPrefix = `llm.profiles.${activeProfile.value}`
  const agentPrefix = `agent.profiles.${activeAgentProfile.value}`
  const patches = [
    { path: 'llm.activeProfile', value: activeProfile.value },
    { path: `${llmPrefix}.provider`, value: form.provider },
    { path: `${llmPrefix}.baseUrl`, value: form.baseUrl.trim() },
    { path: `${llmPrefix}.model`, value: form.model.trim() },
    { path: `${llmPrefix}.extraParams`, value: JSON.parse(form.extraParamsText || '{}') },
    { path: 'agent.activeProfile', value: activeAgentProfile.value },
    { path: `${agentPrefix}.persona`, value: form.persona },
    { path: `${agentPrefix}.memoryWindow`, value: Number(form.memoryWindow) || 50 },
    { path: `${agentPrefix}.recursionLimit`, value: Number(form.recursionLimit) || 50 },
    { path: 'pet.idleReminder.enabled', value: form.idleEnabled },
    { path: 'pet.idleReminder.thresholdMinutes', value: form.idleThreshold },
    { path: 'pet.idleReminder.quietPeriodMinutes', value: form.idleQuiet },
    { path: 'pet.quickAsk.shortcut', value: form.quickAskShortcut },
  ]
  // 仅在用户实际编辑过 key（非掩码）时写入
  if (!String(form.apiKey).startsWith('***')) {
    patches.push({ path: `${llmPrefix}.apiKey`, value: form.apiKey.trim() })
  }
  const res = await api.setConfigMany(patches)
  if (!res.success) return showToast('保存失败: ' + (res.message || ''))
  keyRevealed.value = false
  // 通知 Python 热重建 agent
  send('config.invalidate', { paths: ['llm', 'agent'] })
  showToast('已保存，配置热生效 ✓')
  await loadConfig()
}

function resetPersona() {
  form.persona = ''
  showToast('已恢复默认人设（保存后生效）')
}

async function restartAgent() {
  const res = await api.restartAgent()
  showToast(res.message || '重启中…')
}

async function testConnection() {
  testing.value = true
  testResult.value = null

  const baseUrl = form.baseUrl.trim()
  const apiKey = form.apiKey.trim()
  const model = form.model.trim()

  if (!baseUrl || !apiKey || !model) {
    testing.value = false
    testResult.value = { ok: false, text: '请先填写 Base URL、API Key 和模型名称' }
    return
  }

  try {
    const result = await api.testLlmConnection({ baseUrl, apiKey, model })
    if (result.ok) {
      testResult.value = { ok: true, text: `连接成功（${result.latencyMs}ms）：${result.reply}` }
    } else {
      testResult.value = { ok: false, text: `连接失败：${result.error}` }
    }
  } catch (error) {
    testResult.value = { ok: false, text: `连接失败：${error.message}` }
  } finally {
    testing.value = false
  }
}

function togglePreview() {
  if (preview.value) {
    preview.value = ''
  } else {
    connect()
    send('prompt.preview', { persona: form.persona })
  }
}

onMounted(() => {
  loadConfig()
  connect()
  on('prompt.preview.result', (p) => { preview.value = p.prompt })
  // 快捷键注册结果：主进程注册/重注册后经 shortcut-status 广播
  api.onShortcutStatus?.((p) => {
    if (p && p.shortcut === undefined) return
    hotkeyStatus.value = p.success
      ? (p.shortcut ? { ok: true, text: `✓ ${p.shortcut} 已生效` } : { ok: true, text: '快速提问快捷键已禁用' })
      : { ok: false, text: `✗ 注册失败：${p.message || '未知原因'}，请换一个组合键` }
  })
  // 初始查询当前注册状态
  api.getShortcutStatus?.().then((p) => {
    if (p && p.success && p.shortcut) hotkeyStatus.value = { ok: true, text: `✓ ${p.shortcut} 已生效` }
  })
})
</script>

<style scoped>
.settings-page { max-width: 1200px; }
.settings-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 18px;
}
@media (min-width: 960px) {
  .settings-grid {
    grid-template-columns: 1fr 1fr;
  }
  /* 模型连接和 Agent 配置占满整行（内容较多） */
  .settings-grid .card:nth-child(1),
  .settings-grid .card:nth-child(2) {
    grid-column: 1 / -1;
  }
}
.page-header { margin-bottom: 20px; }
.page-title { font-size: 26px; font-weight: 700; color: #f1f5f9; margin-bottom: 6px; }
.page-subtitle { font-size: 14px; color: #64748b; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 14px; overflow: hidden; }
.card-header { padding: 14px 20px; font-weight: 600; color: #e2e8f0; border-bottom: 1px solid #334155; }
.card-body { padding: 18px 20px; }
.form .field { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form.inline { display: flex; gap: 26px; align-items: center; flex-wrap: wrap; }
.form.inline label { color: #94a3b8; font-size: 14px; display: flex; align-items: center; gap: 8px; }
label { color: #94a3b8; font-size: 13px; }
input, select, textarea { background: #0f172a; border: 1px solid #334155; border-radius: 8px; color: #e2e8f0; padding: 9px 12px; font-size: 14px; font-family: inherit; }
input:focus, textarea:focus, select:focus { outline: none; border-color: #6366f1; }
.mono { font-family: Consolas, monospace; }
.persona { line-height: 1.6; }
.num { width: 80px; }
.stepper { display: inline-flex; align-items: stretch; width: fit-content; border: 1px solid #334155; border-radius: 8px; overflow: hidden; background: #0f172a; }
.stepper:focus-within { border-color: #6366f1; }
.step-input { width: 72px; text-align: center; border: none; border-radius: 0; background: transparent; -moz-appearance: textfield; appearance: textfield; }
.step-input::-webkit-outer-spin-button, .step-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.step-input:focus { outline: none; border: none; }
.step-btn { background: #1e293b; border: none; border-left: 1px solid #334155; color: #94a3b8; width: 34px; font-size: 16px; line-height: 1; cursor: pointer; transition: background .15s, color .15s; }
.step-btn:first-child { border-left: none; border-right: 1px solid #334155; }
.step-btn:hover:not(:disabled) { background: #334155; color: #e2e8f0; }
.step-btn:disabled { opacity: .35; cursor: not-allowed; }
.hotkey-row { display: flex; gap: 8px; align-items: center; }
.hotkey-box {
  min-width: 180px; padding: 9px 12px; border-radius: 8px; cursor: pointer;
  background: #0f172a; border: 1px solid #334155; color: #e2e8f0; font-size: 14px;
  font-family: Consolas, monospace; user-select: none; text-align: center;
}
.hotkey-box.recording { border-color: #6366f1; color: #a5b4fc; animation: hotkey-pulse 1.2s ease-in-out infinite; }
.hotkey-box.bad { border-color: #f87171; }
@keyframes hotkey-pulse { 0%,100% { opacity: 1 } 50% { opacity: .55 } }
.key-row { display: flex; gap: 8px; }
.key-row input { flex: 1; }
.mini { background: #334155; border: none; color: #cbd5e1; border-radius: 8px; padding: 0 14px; cursor: pointer; }
.hint { font-size: 12px; color: #64748b; }
.hint.bad { color: #f87171; }
.global-actions { display: flex; gap: 10px; align-items: center; margin-bottom: 18px; flex-wrap: wrap; }
.actions { display: flex; gap: 10px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
.btn { background: #334155; border: none; color: #e2e8f0; border-radius: 9px; padding: 9px 18px; font-size: 14px; cursor: pointer; }
.btn.primary { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; }
.btn.warn { background: #7f1d1d; color: #fca5a5; }
.btn:disabled { opacity: 0.5; }
.ok { color: #34d399; font-size: 13px; }
.bad-text { color: #f87171; font-size: 13px; }
.preview-box { margin-top: 14px; background: #0f172a; border: 1px dashed #475569; border-radius: 10px; padding: 14px; color: #a5b4fc; font-size: 12px; white-space: pre-wrap; max-height: 320px; overflow: auto; }
.profile-row { display: flex; gap: 8px; align-items: center; }
.profile-row select { flex: 1; }
.mini.danger { background: #7f1d1d; color: #fca5a5; }
.mini.danger:hover:not(:disabled) { background: #991b1b; }
.mini.danger:disabled { opacity: .35; cursor: not-allowed; }

/* 弹窗 */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal {
  background: #1e293b; border: 1px solid #334155; border-radius: 14px;
  padding: 24px; width: 380px; max-width: 90vw; box-shadow: 0 16px 48px rgba(0,0,0,.5);
}
.modal h3 { margin: 0 0 16px; color: #f1f5f9; font-size: 18px; }
.modal .field { margin-bottom: 14px; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 8px; }

/* Toast 提示 - 顶部居中醒目显示 */
.toast {
  position: fixed; top: 24px; left: 50%; transform: translateX(-50%);
  background: #065f46; color: #a7f3d0; padding: 14px 32px; border-radius: 12px;
  font-size: 15px; font-weight: 600; box-shadow: 0 8px 32px rgba(0,0,0,.5);
  z-index: 9999; animation: toast-in .3s ease;
  border: 1px solid #34d399;
}
@keyframes toast-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-16px) }
  to { opacity: 1; transform: translateX(-50%) translateY(0) }
}
</style>
