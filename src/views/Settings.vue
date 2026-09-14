<template>
  <div class="page settings-page">
    <header class="page-header">
      <h1 class="page-title">设置</h1>
      <p class="page-subtitle">模型连接与人设配置，保存后热生效</p>
    </header>

    <!-- 全局操作 -->
    <div class="global-actions">
      <button class="btn primary" @click="saveAll">保存设置</button>
      <button class="btn warn" @click="restartAgent" :disabled="restarting">
        <span v-if="restarting" class="btn-spinner"></span>
        <span v-else-if="restartDone" class="btn-check">✓</span>
        <span v-else>重启服务进程</span>
      </button>
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
            placeholder="你是「优墨」……（支持 {app_name} {time} {os_user} 变量）"></textarea>
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
        <div class="field">
          <label>Tavily API Key（网络搜索工具）</label>
          <div class="key-row">
            <input v-model="form.tavilyApiKey" :type="showTavilyKey ? 'text' : 'password'" placeholder="tvly-..." />
            <button class="mini" @click="showTavilyKey = !showTavilyKey">{{ showTavilyKey ? '隐藏' : '显示' }}</button>
          </div>
          <span class="hint">用于 internet_search 工具，留空则无法使用网络搜索功能</span>
        </div>
        <div class="field">
          <label>对话文档解析引擎（OCR）</label>
          <select v-model="form.agentOcrEngine">
            <option value="markitdown">MarkItDown（快速）</option>
            <option value="docling">Docling（更精细，支持图片识别）</option>
          </select>
          <span class="hint">Agent 对话中解析上传文档所使用的引擎，默认 MarkItDown</span>
        </div>
        <div class="actions">
          <button class="btn" @click="togglePreview">{{ preview ? '隐藏完整提示词' : '预览完整提示词' }}</button>
          <button class="btn" @click="resetPersona">恢复默认人设</button>
        </div>
        <pre v-if="preview" class="preview-box">{{ preview }}</pre>
      </div>
    </section>

    <!-- 知识库（RAG） -->
    <section class="card">
      <div class="card-header">知识库（RAG）</div>
      <div class="card-body form">
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.ragAutoEmbedding" /> 聊天上传文件自动入库</label>
          <span class="hint">开启后，普通对话中上传的文件将异步自动 Embedding 到默认知识库</span>
        </div>
        <div class="field">
          <label>Embedding 模型来源</label>
          <select v-model="form.ragEmbedType" @change="onEmbedTypeChange">
            <option value="local">本地模型（Local）</option>
            <option value="remote">远程 API（OpenAI-Compatible）</option>
          </select>
          <span class="hint">本地模式无需 Base URL / API Key，首次使用时自动下载模型</span>
        </div>
        <div class="field">
          <label>Embedding 模型名称</label>
          <input v-model="form.ragEmbedModel" :placeholder="form.ragEmbedType === 'local' ? '由智能下载自动确定' : 'text-embedding-3-small'"
            :disabled="form.ragEmbedType === 'local'" @change="onEmbedModelChange" />
          <span class="hint">本地模式下模型由「智能下载」按显卡条件自动确定（N 卡 ≥4G 显存用 bge-large，否则 bge-small），无需手动填写；远程模式填服务商模型名</span>
        </div>
        <div class="field">
          <label>Base URL</label>
          <input v-model="form.ragEmbedBaseUrl" placeholder="https://api.openai.com/v1" :disabled="form.ragEmbedType !== 'remote'" />
        </div>
        <div class="field">
          <label>API Key</label>
          <div class="key-row">
            <input v-model="form.ragEmbedApiKey" :type="showRagKey ? 'text' : 'password'" placeholder="sk-..." :disabled="form.ragEmbedType !== 'remote'" />
            <button class="mini" @click="showRagKey = !showRagKey">{{ showRagKey ? '隐藏' : '显示' }}</button>
          </div>
          <span class="hint">仅远程模式需要</span>
        </div>
        <div class="field">
          <label>知识库文档解析引擎（OCR）</label>
          <select v-model="form.ragOcrEngine">
            <option value="docling">Docling（更精细，支持图片识别）</option>
            <option value="markitdown">MarkItDown（快速）</option>
          </select>
          <span class="hint">知识库维护上传时解析文档所使用的引擎，默认 Docling</span>
        </div>
        <div v-if="form.ragEmbedType === 'local' && !form.ragLocalDownloaded" id="rag-model" class="field">
          <label>本地模型下载</label>
          <div class="actions">
            <button class="btn primary" @click="downloadModel" :disabled="downloading">
              <span v-if="downloading" class="btn-spinner"></span>
              <span v-else>⬇ 下载模型</span>
              <span v-if="downloading">下载中…</span>
            </button>
            <span v-if="downloadResult" :class="downloadResult.ok ? 'ok' : 'bad-text'">{{ downloadResult.text }}</span>
          </div>
          <span class="hint">自动检测网络（不可直连时走 hf-mirror 镜像）与显卡（N 卡 ≥4G 显存下载 bge-large，否则 bge-small），模型较大请耐心等待</span>
        </div>
        <div v-else-if="form.ragEmbedType === 'local'" id="rag-model" class="field">
          <label>本地模型状态</label>
          <div class="actions">
            <span class="ok">✓ 模型已下载{{ form.ragEmbedModel ? `：${form.ragEmbedModel}` : '' }}</span>
            <button class="mini" @click="redownloadModel" :disabled="downloading" title="清除已下载状态并重新下载">重新下载</button>
            <span v-if="downloadResult" :class="downloadResult.ok ? 'ok' : 'bad-text'">{{ downloadResult.text }}</span>
          </div>
        </div>
        <div class="actions">
          <span class="hint">RAG 后端功能尚未上线，当前保存的配置将在功能启用后生效</span>
        </div>
      </div>
    </section>

    <!-- 网络代理 -->
    <section class="card">
      <div class="card-header">网络代理</div>
      <div class="card-body form">
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.proxyEnabled" /> 启用 HTTP / HTTPS 代理</label>
          <span class="hint">保存后 Electron 立即生效；Python Agent 需在启用/停用后点击顶部「重启服务进程」以刷新代理环境变量</span>
        </div>
        <div class="field">
          <label>HTTP 代理</label>
          <input v-model="form.proxyHttp" placeholder="http://127.0.0.1:7890" :disabled="!form.proxyEnabled" />
          <span class="hint">支持 http:// 或 socks5:// 前缀，例如 http://127.0.0.1:7890</span>
        </div>
        <div class="field">
          <label>HTTPS 代理</label>
          <input v-model="form.proxyHttps" placeholder="留空则与 HTTP 代理相同" :disabled="!form.proxyEnabled" />
        </div>
        <div class="field">
          <label>绕过代理（NO_PROXY）</label>
          <input v-model="form.proxyNoProxy" placeholder="localhost,127.0.0.1,*.example.com" :disabled="!form.proxyEnabled" />
          <span class="hint">逗号分隔的主机名单，命中这些地址的请求不走代理</span>
        </div>
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

    <!-- 提醒事项 -->
    <section class="card">
      <div class="card-header">提醒事项</div>
      <div class="card-body form">
        <div class="field">
          <label>检查间隔（秒）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('reminderPoll', -1, 3, 30)" :disabled="form.reminderPoll <= 3">−</button>
            <input type="number" v-model.number="form.reminderPoll" min="3" max="30" class="step-input"
              @blur="clamp('reminderPoll', 3, 30, 5)" />
            <button type="button" class="step-btn" @click="step('reminderPoll', 1, 3, 30)" :disabled="form.reminderPoll >= 30">+</button>
          </div>
          <span class="hint">后台检查提醒是否到点的频率，范围 3~30 秒（默认 5 秒，越小触发越及时）</span>
        </div>
        <div class="field">
          <label>气泡显示时长（秒）</label>
          <select v-model.number="form.reminderDuration">
            <option v-for="d in reminderDurationOptions" :key="d" :value="d">{{ d }} 秒</option>
          </select>
          <span class="hint">提醒弹出时桌宠气泡的停留时长，可选 3~30 秒（默认 8 秒）</span>
        </div>
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

    <!-- 切换 Embedding 模型确认弹窗 -->
    <div v-if="showEmbedConfirm" class="modal-overlay" @click.self="cancelEmbedChange">
      <div class="modal">
        <h3>确认切换 Embedding 模型？</h3>
        <p class="hint" style="line-height: 1.6; margin: 0 0 8px;">
          切换后，知识库中所有已入库文档的向量数据将不再匹配，需要重新 Embedding 才能继续使用。
          <br />
          是否确认切换？
        </p>
        <div class="modal-actions">
          <button class="btn" @click="cancelEmbedChange">取消</button>
          <button class="btn primary" @click="confirmEmbedChange">确认切换</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAgentSocket } from '../composables/useAgentSocket'
import { useRestartState } from '../composables/useRestartState'
import { useModelDownloadState } from '../composables/useModelDownloadState'
import { downloadEmbeddingModel } from '../api/embeddingModelDownload'

const { connect, send, on } = useAgentSocket()
const api = window.electronAPI
const route = useRoute()

// 模块级单例状态：切换 tab 导致组件卸载/重新挂载时，重启进度与提示不丢失
const { restarting, restartDone, toast } = useRestartState()
// 模型下载进度同样为模块级单例：下载中切换 tab 后动画与结果不丢失
const { downloading, result: downloadResult } = useModelDownloadState()

const activeProfile = ref('default')
const profiles = ref({})
const activeAgentProfile = ref('default')
const agentProfiles = ref({})
// 提醒气泡显示时长可选值（秒），范围 3~30
const reminderDurationOptions = [3, 5, 8, 10, 15, 20, 30]
const form = reactive({
  provider: 'openai', baseUrl: '', apiKey: '', model: '', extraParamsText: '{}',
  persona: '', memoryWindow: 50, recursionLimit: 50, idleEnabled: true, idleThreshold: 30, idleQuiet: 10,
  quickAskShortcut: 'Alt+Shift+Q',
  reminderPoll: 5, reminderDuration: 8,
  tavilyApiKey: '',
  agentOcrEngine: 'markitdown',
  ragAutoEmbedding: true, ragEmbedType: 'local', ragEmbedModel: 'BAAI/bge-small-zh-v1.5',
  ragEmbedBaseUrl: '', ragEmbedApiKey: '', ragOcrEngine: 'docling',
  ragLocalDownloaded: false,
  proxyEnabled: false, proxyHttp: '', proxyHttps: '', proxyNoProxy: ''
})

const recordingKey = ref(false)
const hotkeyError = ref('')
const hotkeyStatus = ref(null)
const showKey = ref(false)
const showTavilyKey = ref(false)
const showRagKey = ref(false)
const extraError = ref('')
const testing = ref(false)
const testResult = ref(null)
const preview = ref('')
const keyRevealed = ref(false)
const showAddProfile = ref(false)
const newProfileName = ref('')
const newProfileError = ref('')
const profileNameInput = ref(null)
const showAddAgentProfile = ref(false)
const newAgentProfileName = ref('')
const newAgentProfileError = ref('')
const agentProfileNameInput = ref(null)

// Embedding 模型切换确认：记录已保存（配置中落盘）的模型来源与名称，
// 变更时弹窗提示知识库文档需要重新 Embedding
let savedEmbedType = 'local'
let savedEmbedModel = ''
const showEmbedConfirm = ref(false)
const embedPendingChange = ref(null) // { kind: 'type' | 'model', value: 新值 }

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
  // 提醒事项
  form.reminderPoll = cfg.pet?.reminders?.pollIntervalSeconds ?? 5
  const durSec = Math.round((cfg.pet?.reminders?.bubbleDurationMs ?? 8000) / 1000)
  form.reminderDuration = reminderDurationOptions.includes(durSec)
    ? durSec
    : reminderDurationOptions.reduce((a, b) => Math.abs(b - durSec) < Math.abs(a - durSec) ? b : a)
  // 网络代理
  form.proxyEnabled = cfg.network?.proxy?.enabled === true
  form.proxyHttp = cfg.network?.proxy?.http || ''
  form.proxyHttps = cfg.network?.proxy?.https || ''
  form.proxyNoProxy = cfg.network?.proxy?.noProxy || ''
  // Tavily API Key：掩码处理
  const tavilyKey = cfg.agent?.tavilyApiKey || ''
  form.tavilyApiKey = tavilyKey.length > 3 ? '***' + tavilyKey.slice(-3) : tavilyKey
  // 对话 OCR 引擎
  form.agentOcrEngine = cfg.agent?.ocrEngine === 'docling' ? 'docling' : 'markitdown'
  // 知识库（RAG）
  form.ragAutoEmbedding = cfg.rag?.autoEmbedding !== false
  form.ragEmbedType = cfg.rag?.embeddingModel?.type === 'remote' ? 'remote' : 'local'
  form.ragEmbedModel = cfg.rag?.embeddingModel?.model || ''
  // 本地模型已下载状态（下载成功后由本页面写入配置，切换回来即不再显示下载按钮）
  form.ragLocalDownloaded = cfg.rag?.embeddingModel?.downloaded === true
  form.ragEmbedBaseUrl = cfg.rag?.embeddingModel?.baseUrl || ''
  const ragKey = cfg.rag?.embeddingModel?.apiKey || ''
  form.ragEmbedApiKey = ragKey.length > 3 ? '***' + ragKey.slice(-3) : ragKey
  form.ragOcrEngine = cfg.rag?.ocrEngine === 'markitdown' ? 'markitdown' : 'docling'
  // 记录已保存的 Embedding 配置，用于判断用户是否切换了模型
  savedEmbedType = form.ragEmbedType
  savedEmbedModel = form.ragEmbedModel
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
    { path: 'pet.reminders.pollIntervalSeconds', value: Number(form.reminderPoll) || 5 },
    { path: 'pet.reminders.bubbleDurationMs', value: (Number(form.reminderDuration) || 8) * 1000 },
    { path: 'pet.quickAsk.shortcut', value: form.quickAskShortcut },
    { path: 'network.proxy.enabled', value: !!form.proxyEnabled },
    { path: 'network.proxy.http', value: form.proxyHttp.trim() },
    { path: 'network.proxy.https', value: form.proxyHttps.trim() },
    { path: 'network.proxy.noProxy', value: form.proxyNoProxy.trim() },
    { path: 'agent.ocrEngine', value: form.agentOcrEngine === 'docling' ? 'docling' : 'markitdown' },
    { path: 'rag.autoEmbedding', value: !!form.ragAutoEmbedding },
    { path: 'rag.embeddingModel.type', value: form.ragEmbedType === 'remote' ? 'remote' : 'local' },
    { path: 'rag.embeddingModel.baseUrl', value: form.ragEmbedBaseUrl.trim() },
    { path: 'rag.ocrEngine', value: form.ragOcrEngine === 'markitdown' ? 'markitdown' : 'docling' },
  ]
  // 本地模式的模型名由智能下载写入（downloadModel 内即时落盘），保存时不覆盖；
  // 仅远程模式允许用户自定义模型名
  if (form.ragEmbedType === 'remote') {
    patches.push({ path: 'rag.embeddingModel.model', value: form.ragEmbedModel.trim() })
  }
  // 远程模式下才写入 embedding apiKey（非掩码时）；本地模式清空
  if (form.ragEmbedType === 'remote' && !String(form.ragEmbedApiKey).startsWith('***')) {
    patches.push({ path: 'rag.embeddingModel.apiKey', value: form.ragEmbedApiKey.trim() })
  }
  // 代理启用时做简单格式校验
  if (form.proxyEnabled && !form.proxyHttp.trim() && !form.proxyHttps.trim()) {
    return showToast('已启用代理，请至少填写 HTTP 或 HTTPS 代理地址')
  }
  // 仅在用户实际编辑过 key（非掩码）时写入
  if (!String(form.apiKey).startsWith('***')) {
    patches.push({ path: `${llmPrefix}.apiKey`, value: form.apiKey.trim() })
  }
  // Tavily API Key：仅在非掩码时写入
  if (!String(form.tavilyApiKey).startsWith('***')) {
    patches.push({ path: 'agent.tavilyApiKey', value: form.tavilyApiKey.trim() })
  }
  const res = await api.setConfigMany(patches)
  if (!res.success) return showToast('保存失败: ' + (res.message || ''))
  keyRevealed.value = false
  // 通知 Python 热重建 agent（同时让 agent.ocrEngine / rag 配置热重载）
  send('config.invalidate', { paths: ['llm', 'agent', 'rag'] })
  showToast('已保存，配置热生效 ✓')
  await loadConfig()
}

function resetPersona() {
  form.persona = ''
  showToast('已恢复默认人设（保存后生效）')
}

async function restartAgent() {
  if (restarting.value) return
  restarting.value = true
  restartDone.value = false

  const res = await api.restartAgent()
  if (!res.success) {
    restarting.value = false
    showToast('重启失败: ' + (res.message || ''))
    return
  }

  // 等待 Python 服务实际启动完成（主进程发送 status-update running:true）
  const started = await new Promise((resolve) => {
    const timer = setTimeout(() => {
      api.offStatusUpdate?.(onStarted)
      resolve(false)
    }, 30000) // 30s 超时

    const onStarted = (status) => {
      if (status && status.running) {
        clearTimeout(timer)
        api.offStatusUpdate?.(onStarted)
        resolve(true)
      }
    }
    api.onStatusUpdate?.(onStarted)
  })

  restarting.value = false
  if (started) {
    restartDone.value = true
    showToast('服务重启成功 ✓')
    setTimeout(() => { restartDone.value = false }, 2500)
  } else {
    showToast('服务启动超时，请检查日志')
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null

  const baseUrl = form.baseUrl.trim()
  let apiKey = form.apiKey.trim()
  const model = form.model.trim()

  if (!baseUrl || !apiKey || !model) {
    testing.value = false
    testResult.value = { ok: false, text: '请先填写 Base URL、API Key 和模型名称' }
    return
  }

  // 如果 apiKey 是掩码值（***开头），先从后端获取真实 key
  if (apiKey.startsWith('***')) {
    const res = await api.getRawProfileKey(activeProfile.value)
    if (res.success) {
      apiKey = res.apiKey
    } else {
      testing.value = false
      testResult.value = { ok: false, text: '无法获取真实 API Key，请先点击「显示」按钮' }
      return
    }
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

// 下载逻辑不依赖组件实例：await 的 Promise 由模块级函数持有，
// 即使下载中途切换 tab 导致本组件卸载，完成后仍会写回模块级单例状态并落盘配置
async function downloadModel() {
  if (downloading.value) return
  downloading.value = true
  downloadResult.value = null
  try {
    const res = await downloadEmbeddingModel()
    // 下载成功：把实际下载的模型名与已下载状态写入配置（config.user.json），
    // 下次进入设置页读到 downloaded=true 即不再显示下载按钮
    const patchRes = await api.setConfigMany([
      { path: 'rag.embeddingModel.model', value: res.model || '' },
      { path: 'rag.embeddingModel.localPath', value: res.path || '' },
      { path: 'rag.embeddingModel.downloaded', value: true },
    ])
    if (!patchRes.success) {
      downloadResult.value = { ok: false, text: `模型已下载但写入配置失败：${patchRes.message || ''}` }
      return
    }
    form.ragEmbedModel = res.model || form.ragEmbedModel
    savedEmbedModel = form.ragEmbedModel // 模型已落盘，同步切换基线
    form.ragLocalDownloaded = true
    downloadResult.value = { ok: true, text: `下载完成 ✓ ${res.model || ''}` }
    showToast('模型下载完成 ✓')
  } catch (e) {
    downloadResult.value = { ok: false, text: `下载失败：${e.message}` }
  } finally {
    downloading.value = false
  }
}

// 清除已下载状态并重新走智能下载（例如更换显卡后想升级到大模型）
async function redownloadModel() {
  if (downloading.value) return
  if (!confirm('确定要清除已下载状态并重新下载模型吗？（本地缓存的模型文件不会被删除）')) return
  const res = await api.setConfig('rag.embeddingModel.downloaded', false)
  if (!res.success) return showToast('清除下载状态失败: ' + (res.message || ''))
  form.ragLocalDownloaded = false
  await downloadModel()
}

// ---------- Embedding 模型切换确认 ----------
function onEmbedTypeChange() {
  if (form.ragEmbedType === savedEmbedType) return
  embedPendingChange.value = { kind: 'type', value: form.ragEmbedType }
  showEmbedConfirm.value = true
}

function onEmbedModelChange() {
  if (form.ragEmbedModel === savedEmbedModel) return
  embedPendingChange.value = { kind: 'model', value: form.ragEmbedModel }
  showEmbedConfirm.value = true
}

// 取消：回滚为已保存的模型配置
function cancelEmbedChange() {
  const pending = embedPendingChange.value
  if (pending?.kind === 'type') form.ragEmbedType = savedEmbedType
  else if (pending?.kind === 'model') form.ragEmbedModel = savedEmbedModel
  showEmbedConfirm.value = false
  embedPendingChange.value = null
}

// 确认：保留新值，并同步基线，避免重复弹窗
function confirmEmbedChange() {
  const pending = embedPendingChange.value
  if (pending?.kind === 'type') savedEmbedType = form.ragEmbedType
  else if (pending?.kind === 'model') savedEmbedModel = form.ragEmbedModel
  showEmbedConfirm.value = false
  embedPendingChange.value = null
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
  // 知识库页「前往下载模型」跳转过来时，滚动定位到模型下载区域
  if (route.hash === '#rag-model') {
    nextTick(() => {
      setTimeout(() => {
        document.getElementById('rag-model')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 300)
    })
  }
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
.btn { background: #334155; border: none; color: #e2e8f0; border-radius: 9px; padding: 9px 18px; font-size: 14px; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; }
.btn-check { color: #34d399; font-weight: 700; font-size: 16px; }
.btn-spinner {
  width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.25);
  border-top-color: #fff; border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg) } }
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
