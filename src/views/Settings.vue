<template>
  <div class="page settings-page">
    <header class="page-header">
      <h1 class="page-title">设置</h1>
      <p class="page-subtitle">模型连接与人设配置，保存后热生效</p>
    </header>

    <!-- 模型连接 -->
    <section class="card">
      <div class="card-header">模型连接</div>
      <div class="card-body form">
        <div class="field">
          <label>配置档</label>
          <select :value="activeProfile" @change="switchProfile($event.target.value)">
            <option v-for="(p, name) in profiles" :key="name" :value="name">{{ p.label || name }}</option>
          </select>
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

    <!-- 人设与行为 -->
    <section class="card">
      <div class="card-header">人设与系统提示词</div>
      <div class="card-body form">
        <div class="field">
          <label>人设提示词（可编辑，留空使用默认傲娇猫咪人设）</label>
          <textarea v-model="form.persona" rows="10" class="mono persona"
            placeholder="你是「臭屁猫」……（支持 {app_name} {time} {os_user} 变量）"></textarea>
          <span class="hint">{{ form.persona.length }} 字</span>
        </div>
        <div class="actions">
          <button class="btn primary" @click="saveAll">保存设置</button>
          <button class="btn" @click="previewPrompt">预览完整提示词</button>
          <button class="btn" @click="resetPersona">恢复默认人设</button>
          <button class="btn warn" @click="restartAgent">重启服务进程</button>
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

    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useAgentSocket } from '../composables/useAgentSocket'

const { connect, send, on } = useAgentSocket()
const api = window.electronAPI

const activeProfile = ref('default')
const profiles = ref({})
const form = reactive({
  baseUrl: '', apiKey: '', model: '', extraParamsText: '{}',
  persona: '', idleEnabled: true, idleThreshold: 30, idleQuiet: 10
})
const showKey = ref(false)
const extraError = ref('')
const testing = ref(false)
const testResult = ref(null)
const preview = ref('')
const toast = ref('')
const keyRevealed = ref(false)

function showToast(text) {
  toast.value = text
  setTimeout(() => (toast.value = ''), 2500)
}

function validateExtra() {
  try { JSON.parse(form.extraParamsText || '{}'); extraError.value = '' }
  catch (e) { extraError.value = 'JSON 格式错误' }
}

async function loadConfig() {
  const res = await api.getConfig()
  if (!res.success) return showToast('配置加载失败')
  const cfg = res.config
  profiles.value = cfg.llm?.profiles || { default: { label: '默认' } }
  activeProfile.value = cfg.llm?.activeProfile || 'default'
  fillFormFromProfile()
  form.persona = cfg.agent?.persona || ''
  form.idleEnabled = cfg.pet?.idleReminder?.enabled !== false
  form.idleThreshold = cfg.pet?.idleReminder?.thresholdMinutes ?? 30
  form.idleQuiet = cfg.pet?.idleReminder?.quietPeriodMinutes ?? 10
}

function fillFormFromProfile() {
  const p = profiles.value[activeProfile.value] || {}
  form.baseUrl = p.baseUrl || ''
  form.apiKey = p.apiKey || '' // 掩码值 ***abc
  form.model = p.model || ''
  form.extraParamsText = JSON.stringify(p.extraParams || {}, null, 2)
  keyRevealed.value = false
  validateExtra()
}

async function switchProfile(name) {
  activeProfile.value = name
  await api.setConfig('llm.activeProfile', name)
  fillFormFromProfile()
}

async function revealKey() {
  if (keyRevealed.value) return
  const res = await api.getRawProfileKey(activeProfile.value)
  if (res.success) { form.apiKey = res.apiKey; keyRevealed.value = true }
}

async function saveAll() {
  validateExtra()
  if (extraError.value) return showToast('额外参数 JSON 无效，未保存')
  const prefix = `llm.profiles.${activeProfile.value}`
  const patches = [
    { path: 'llm.activeProfile', value: activeProfile.value },
    { path: `${prefix}.baseUrl`, value: form.baseUrl.trim() },
    { path: `${prefix}.model`, value: form.model.trim() },
    { path: `${prefix}.extraParams`, value: JSON.parse(form.extraParamsText || '{}') },
    { path: 'agent.persona', value: form.persona },
    { path: 'pet.idleReminder.enabled', value: form.idleEnabled },
    { path: 'pet.idleReminder.thresholdMinutes', value: form.idleThreshold },
    { path: 'pet.idleReminder.quietPeriodMinutes', value: form.idleQuiet },
  ]
  // 仅在用户实际编辑过 key（非掩码）时写入
  if (!String(form.apiKey).startsWith('***')) {
    patches.push({ path: `${prefix}.apiKey`, value: form.apiKey.trim() })
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
  showToast('已恢复默认（保存后生效）')
}

async function restartAgent() {
  const res = await api.restartAgent()
  showToast(res.message || '重启中…')
}

function testConnection() {
  connect()
  testing.value = true
  testResult.value = null
  send('llm.test', { profileName: activeProfile.value })
}

function previewPrompt() {
  connect()
  send('prompt.preview', { persona: form.persona })
}

onMounted(() => {
  loadConfig()
  connect()
  on('llm.test.result', (p) => {
    testing.value = false
    testResult.value = p.ok
      ? { ok: true, text: `连接成功（${p.latencyMs}ms）：${p.reply}` }
      : { ok: false, text: '连接失败：' + p.error }
  })
  on('prompt.preview.result', (p) => { preview.value = p.prompt })
})
</script>

<style scoped>
.settings-page { max-width: 860px; }
.page-header { margin-bottom: 20px; }
.page-title { font-size: 26px; font-weight: 700; color: #f1f5f9; margin-bottom: 6px; }
.page-subtitle { font-size: 14px; color: #64748b; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 14px; margin-bottom: 18px; overflow: hidden; }
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
.key-row { display: flex; gap: 8px; }
.key-row input { flex: 1; }
.mini { background: #334155; border: none; color: #cbd5e1; border-radius: 8px; padding: 0 14px; cursor: pointer; }
.hint { font-size: 12px; color: #64748b; }
.hint.bad { color: #f87171; }
.actions { display: flex; gap: 10px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
.btn { background: #334155; border: none; color: #e2e8f0; border-radius: 9px; padding: 9px 18px; font-size: 14px; cursor: pointer; }
.btn.primary { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; }
.btn.warn { background: #7f1d1d; color: #fca5a5; }
.btn:disabled { opacity: 0.5; }
.ok { color: #34d399; font-size: 13px; }
.bad-text { color: #f87171; font-size: 13px; }
.preview-box { margin-top: 14px; background: #0f172a; border: 1px dashed #475569; border-radius: 10px; padding: 14px; color: #a5b4fc; font-size: 12px; white-space: pre-wrap; max-height: 320px; overflow: auto; }
.toast { position: fixed; bottom: 28px; right: 28px; background: #065f46; color: #a7f3d0; padding: 12px 20px; border-radius: 10px; font-size: 14px; box-shadow: 0 8px 24px rgba(0,0,0,.4); z-index: 99; }
</style>
