<template>
  <div class="mcp-page">
    <header class="mcp-header">
      <div class="head-main">
        <div class="eyebrow">MCP · 服务注册</div>
        <h2 class="mcp-title">MCP</h2>
        <p class="mcp-subtitle">MCP 服务的注册与发现 · 已启用的 Server 工具将自动装配给本喵</p>
      </div>
      <div class="header-actions">
        <button class="btn-primary" @click="openCreate">
          <AppIcon name="plus" :size="14" />
          注册
        </button>
        <button class="btn-secondary" @click="openImport">
          <AppIcon name="upload" :size="14" />
          导入
        </button>
        <button class="btn-secondary" :disabled="!servers.length" @click="doExport">
          <AppIcon name="download" :size="14" />
          导出
        </button>
        <button class="btn-refresh" :disabled="loading" @click="load">
          <AppIcon name="refresh" :size="14" :class="{ spinning: loading }" />
          刷新
        </button>
      </div>
    </header>

    <div v-if="loading" class="state-block">
      <span class="ui-spinner"></span>
      <span>加载中…</span>
    </div>
    <div v-else-if="error" class="mcp-error">
      <AppIcon name="alert" :size="15" />
      <span>{{ error }}</span>
    </div>
    <div v-else-if="servers.length === 0" class="ui-empty">
      <div class="ui-empty-icon"><AppIcon name="plug" :size="24" /></div>
      <div class="ui-empty-title">还没有注册任何 MCP Server</div>
      <p class="ui-empty-text">点击右上角「注册」添加第一个吧</p>
    </div>

    <div v-else class="mcp-grid">
      <div v-for="server in servers" :key="server.name" class="mcp-card" :class="{ disabled: !server.enabled }">
        <div class="card-top">
          <span class="card-icon"><AppIcon name="plug" :size="17" /></span>
          <div class="card-top-right">
            <span class="card-badge" :class="{ off: !server.enabled }">
              <span class="badge-dot"></span>{{ server.enabled ? '已启用' : '已停用' }}
            </span>
            <span class="transport-tag" :title="transportTitle(server.transport)">{{ transportLabel(server.transport) }}</span>
            <button class="card-delete" title="删除该注册" @click="askDelete(server)">
              <AppIcon name="trash" :size="14" />
            </button>
          </div>
        </div>
        <div class="card-name" :title="server.name">{{ server.displayName || server.name }}</div>
        <div class="card-desc">{{ server.description || '暂无描述' }}</div>
        <div class="card-target" :title="server.target">{{ server.target || '—' }}</div>
        <div class="card-test" v-if="server.lastTest">
          <template v-if="server.lastTest.ok">
            <span class="test-ok"><AppIcon name="check" :size="12" />连通</span>
            <span class="test-meta">
              {{ server.lastTest.toolCount }} 个工具 · {{ server.lastTest.latencyMs }}ms
              <span v-if="server.lastTest.mismatch" class="test-mismatch" :title="`注册为 ${server.transport}，实际以 ${server.lastTest.usedTransport} 连通，建议编辑改为该传输`">
                （经 {{ transportLabel(server.lastTest.usedTransport) }} 回退连通）
              </span>
            </span>
          </template>
          <template v-else>
            <span class="test-fail"><AppIcon name="alert" :size="12" />不可达</span>
            <span class="test-meta" :title="server.lastTest.error">{{ server.lastTest.error }}</span>
          </template>
          <span class="test-time">{{ formatTime(server.lastTest.at) }}</span>
        </div>
        <div class="card-time" v-else>尚未测试连接</div>
        <div class="card-actions">
          <button class="btn-tiny" :disabled="testing === server.name" @click="doTest(server)">
            <AppIcon name="zap" :size="13" />
            {{ testing === server.name ? '测试中…' : '测试' }}
          </button>
          <button
            class="btn-tiny"
            :disabled="!(server.tools && server.tools.length)"
            :title="server.tools && server.tools.length ? `查看已发现的 ${server.tools.length} 个工具` : '尚未测试发现工具'"
            @click="openTools(server)"
          >
            <AppIcon name="wrench" :size="13" />
            工具{{ server.tools && server.tools.length ? ` (${server.tools.length})` : '' }}
          </button>
          <button class="btn-tiny" @click="openEdit(server)">
            <AppIcon name="edit" :size="13" />
            编辑
          </button>
          <button class="btn-tiny" @click="toggleEnabled(server)">
            <AppIcon :name="server.enabled ? 'stop' : 'play'" :size="13" />
            {{ server.enabled ? '停用' : '启用' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 注册/编辑弹窗 -->
    <div v-if="showForm" class="modal-mask" @click.self="closeForm">
      <div class="modal modal-wide">
        <div class="modal-title">
          <AppIcon :name="editingName ? 'edit' : 'plus'" :size="16" />
          {{ editingName ? '编辑 MCP Server' : '注册 MCP Server' }}
        </div>
        <div class="form-grid">
          <div class="form-row">
            <label class="form-label">标识名 *</label>
            <input v-model="form.name" class="modal-input" placeholder="如 filesystem-tools" maxlength="64" :disabled="!!editingName" />
          </div>
          <div class="form-row">
            <label class="form-label">显示名称</label>
            <input v-model="form.displayName" class="modal-input" placeholder="缺省与标识名相同" maxlength="64" />
          </div>
          <div class="form-row full">
            <label class="form-label">描述</label>
            <input v-model="form.description" class="modal-input" placeholder="该 MCP 服务的用途" maxlength="200" />
          </div>
          <div class="form-row full">
            <label class="form-label">传输类型 *</label>
            <div class="transport-picker">
              <button
                v-for="t in TRANSPORTS" :key="t.value"
                class="transport-opt" :class="{ picked: form.transport === t.value }"
                @click="form.transport = t.value"
              >{{ t.label }}</button>
            </div>
          </div>

          <template v-if="form.transport === 'stdio'">
            <div class="form-row full">
              <label class="form-label">启动命令 *</label>
              <input v-model="form.command" class="modal-input" placeholder="如 npx / uvx / python" />
            </div>
            <div class="form-row full">
              <label class="form-label">命令参数（每行一个）</label>
              <textarea v-model="form.argsText" class="modal-input form-area" rows="3" placeholder="-y&#10;@modelcontextprotocol/server-filesystem&#10;D:/data"></textarea>
            </div>
            <div class="form-row full">
              <label class="form-label">环境变量（KEY=VALUE 每行一个，如 API Key）</label>
              <textarea v-model="form.envText" class="modal-input form-area" rows="3" placeholder="API_KEY=sk-xxx&#10;TZ=Asia/Shanghai"></textarea>
            </div>
          </template>
          <template v-else>
            <div class="form-row full">
              <label class="form-label">服务 URL *</label>
              <input v-model="form.url" class="modal-input" placeholder="https://example.com/mcp" />
            </div>
            <div class="form-row full">
              <label class="form-label">请求头（KEY=VALUE 每行一个，如 Authorization）</label>
              <textarea v-model="form.headersText" class="modal-input form-area" rows="3" placeholder="Authorization=Bearer xxx"></textarea>
            </div>
          </template>

          <div class="form-row full">
            <label class="import-overwrite">
              <input type="checkbox" v-model="form.enabled" />
              启用该服务
            </label>
          </div>
        </div>
        <div class="modal-hint">配置保存在用户数据目录（%APPDATA%\sassy-cat\mcp-servers.json）；启用状态的 Server 工具会自动装载进 agent。</div>
        <div v-if="formError" class="modal-error">{{ formError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="closeForm">取消</button>
          <button class="btn-primary" :disabled="saving" @click="submitForm">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 导入弹窗 -->
    <div v-if="showImport" class="modal-mask" @click.self="showImport = false">
      <div class="modal modal-wide">
        <div class="modal-title">
          <AppIcon name="upload" :size="16" />
          导入 MCP 配置
        </div>
        <textarea
          v-model="importText"
          class="modal-input form-area"
          rows="10"
          placeholder='{ "mcpServers": { "example": { "command": "npx", "args": ["-y", "some-mcp-server"], "env": { "API_KEY": "sk-xxx" } } } }'
        ></textarea>
        <label class="import-overwrite">
          <input type="checkbox" v-model="importOverwrite" />
          同名 server 已存在时覆盖
        </label>
        <div class="modal-hint">兼容 Claude Desktop / mcp.json 风格：command/args/env（stdio）或 url/headers（sse、streamable_http）</div>
        <div v-if="importError" class="modal-error">{{ importError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="showImport = false">取消</button>
          <button class="btn-primary" :disabled="importing || !importText.trim()" @click="submitImport">
            {{ importing ? '导入中…' : '导入' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="modal-mask" @click.self="deleteTarget = null">
      <div class="modal">
        <div class="modal-title danger-title">
          <AppIcon name="alert" :size="16" />
          删除 MCP Server
        </div>
        <p class="modal-notice">
          确定要删除「{{ deleteTarget.displayName || deleteTarget.name }}」的注册信息吗？仅移除登记配置，不会删除任何本地程序。
        </p>
        <div v-if="deleteError" class="modal-error">{{ deleteError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="deleteTarget = null">取消</button>
          <button class="btn-danger" :disabled="deleting" @click="confirmDelete">
            {{ deleting ? '删除中…' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 已发现工具列表弹窗（来自注册表持久化数据，无需重新建联） -->
    <div v-if="toolsViewer" class="modal-mask" @click.self="toolsViewer = null">
      <div class="modal modal-wide">
        <div class="modal-title">
          <AppIcon name="wrench" :size="16" />
          工具列表 — {{ toolsViewer.displayName || toolsViewer.name }}
        </div>
        <div class="tools-viewer-meta">
          发现于 {{ formatTime(toolsViewer.toolsDiscoveredAt) }}（来自最近一次连接测试的缓存结果）
        </div>
        <div class="tool-list">
          <div v-for="t in toolsViewer.tools" :key="t.name" class="tool-item">
            <span class="tool-name">{{ t.name }}</span>
            <span class="tool-desc">{{ t.description || '—' }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="toolsViewer = null">关闭</button>
          <button class="btn-primary" :disabled="testing === toolsViewer.name" @click="refreshTools">
            <AppIcon name="refresh" :size="14" />
            {{ testing === toolsViewer.name ? '发现中…' : '重新发现' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 测试结果弹窗 -->
    <div v-if="testResult" class="modal-mask" @click.self="testResult = null">
      <div class="modal modal-wide">
        <div class="modal-title" :class="{ 'danger-title': !testResult.ok }">
          <AppIcon :name="testResult.ok ? 'check' : 'x'" :size="16" />
          {{ testResult.ok ? '连接成功' : '连接失败' }} — {{ testTargetName }}
        </div>
        <template v-if="testResult.ok">
          <div class="test-summary">
            <span>协议版本：{{ testResult.serverInfo.protocolVersion || '—' }}</span>
            <span>服务端：{{ testResult.serverInfo.name || '—' }} {{ testResult.serverInfo.version }}</span>
            <span>耗时：{{ testResult.latencyMs }} ms</span>
            <span v-if="testResult.usedTransport && testResult.usedTransport !== testTargetTransport" class="test-mismatch">
              注册传输为 {{ transportLabel(testTargetTransport) }}，实际经 {{ transportLabel(testResult.usedTransport) }} 连通，建议在编辑中更正
            </span>
          </div>
          <div class="tool-list">
            <div class="tool-list-title">发现 {{ testResult.tools.length }} 个工具</div>
            <div v-if="!testResult.tools.length" class="mcp-empty">（该服务未暴露任何工具）</div>
            <div v-for="t in testResult.tools" :key="t.name" class="tool-item">
              <span class="tool-name">{{ t.name }}</span>
              <span class="tool-desc">{{ t.description || '—' }}</span>
            </div>
          </div>
        </template>
        <template v-else>
          <p class="modal-notice test-error-text">{{ testResult.error }}</p>
        </template>
        <div class="modal-actions">
          <button class="btn-ghost" @click="testResult = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { listServers, createServer, updateServer, deleteServer, importServers, testServer, exportServers } from '../api/mcp'
import AppIcon from '../components/AppIcon.vue'

const TRANSPORTS = [
  { value: 'stdio', label: 'stdio（本地进程）' },
  { value: 'streamable_http', label: 'streamable_http（远程）' },
  { value: 'sse', label: 'sse（远程·旧）' },
]

const servers = ref([])
const loading = ref(true)
const error = ref('')

// 注册/编辑表单
const showForm = ref(false)
const editingName = ref('')
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '', displayName: '', description: '', transport: 'stdio',
  command: '', argsText: '', envText: '', url: '', headersText: '', enabled: true,
})

// 删除
const deleteTarget = ref(null)
const deleting = ref(false)
const deleteError = ref('')

// 导入
const showImport = ref(false)
const importText = ref('')
const importOverwrite = ref(false)
const importing = ref(false)
const importError = ref('')

// 测试
const testing = ref('')
const testResult = ref(null)
const testTargetName = ref('')
const testTargetTransport = ref('')

// 工具列表查看器（数据来自注册表持久化的 server.tools）
const toolsViewer = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listServers()
    servers.value = res.items || []
  } catch (e) {
    error.value = `加载 MCP 列表失败：${e.message}`
  } finally {
    loading.value = false
  }
}

function transportLabel(t) {
  return { stdio: 'stdio', sse: 'SSE', streamable_http: 'HTTP' }[t] || t
}
function transportTitle(t) {
  return TRANSPORTS.find((x) => x.value === t)?.label || t
}

// ---------- 表单 ----------
function parseKv(text) {
  // KEY=VALUE 每行一条；值中允许包含 =（按首个 = 切分），忽略空行与注释行
  const out = {}
  for (const line of (text || '').split(/\r?\n/)) {
    const s = line.trim()
    if (!s || s.startsWith('#')) continue
    const i = s.indexOf('=')
    if (i <= 0) continue
    out[s.slice(0, i).trim()] = s.slice(i + 1).trim()
  }
  return out
}
function stringifyKv(obj) {
  return Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join('\n')
}
function resetForm() {
  Object.assign(form, {
    name: '', displayName: '', description: '', transport: 'stdio',
    command: '', argsText: '', envText: '', url: '', headersText: '', enabled: true,
  })
  formError.value = ''
}
function openCreate() {
  editingName.value = ''
  resetForm()
  showForm.value = true
}
function openEdit(server) {
  editingName.value = server.name
  Object.assign(form, {
    name: server.name,
    displayName: server.displayName || '',
    description: server.description || '',
    transport: server.transport || 'stdio',
    command: server.command || '',
    argsText: (server.args || []).join('\n'),
    envText: stringifyKv(server.env),
    url: server.url || '',
    headersText: stringifyKv(server.headers),
    enabled: server.enabled !== false,
  })
  formError.value = ''
  showForm.value = true
}
function closeForm() {
  showForm.value = false
}
function buildPayload() {
  return {
    name: form.name.trim(),
    displayName: form.displayName.trim(),
    description: form.description.trim(),
    transport: form.transport,
    command: form.command.trim(),
    args: form.argsText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
    env: parseKv(form.envText),
    url: form.url.trim(),
    headers: parseKv(form.headersText),
    enabled: form.enabled,
  }
}
async function submitForm() {
  const payload = buildPayload()
  if (!payload.name) {
    formError.value = '请填写标识名'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    if (editingName.value) {
      await updateServer(editingName.value, payload)
    } else {
      await createServer(payload)
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

// ---------- 启停 ----------
async function toggleEnabled(server) {
  error.value = ''
  try {
    await updateServer(server.name, {
      name: server.name,
      displayName: server.displayName,
      description: server.description,
      transport: server.transport,
      command: server.command,
      args: server.args,
      env: server.env,
      url: server.url,
      headers: server.headers,
      enabled: !server.enabled,
    })
    await load()
  } catch (e) {
    error.value = `切换状态失败：${e.message}`
  }
}

// ---------- 删除 ----------
function askDelete(server) {
  deleteError.value = ''
  deleteTarget.value = server
}
async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await deleteServer(deleteTarget.value.name)
    deleteTarget.value = null
    await load()
  } catch (e) {
    deleteError.value = e.message
  } finally {
    deleting.value = false
  }
}

// ---------- 导入/导出 ----------
function openImport() {
  importText.value = ''
  importOverwrite.value = false
  importError.value = ''
  showImport.value = true
}
async function submitImport() {
  importing.value = true
  importError.value = ''
  try {
    const res = await importServers(importText.value, importOverwrite.value)
    showImport.value = false
    if (res.skipped?.length) {
      error.value = `导入完成，部分跳过：${res.skipped.join('；')}`
    }
    await load()
  } catch (e) {
    importError.value = e.message
  } finally {
    importing.value = false
  }
}
async function doExport() {
  error.value = ''
  try {
    const data = await exportServers()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'mcp-servers.json'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = `导出失败：${e.message}`
  }
}

// ---------- 连接测试 ----------
function openTools(server) {
  toolsViewer.value = server
}

// 弹窗内「重新发现」：对该 server 再跑一次连接测试并刷新缓存的工具列表
async function refreshTools() {
  if (!toolsViewer.value) return
  const server = servers.value.find((s) => s.name === toolsViewer.value.name)
  if (!server) {
    toolsViewer.value = null
    return
  }
  await doTest(server)
  // 测试成功后 load() 已刷新 servers；把最新 tools 同步进查看器
  const fresh = servers.value.find((s) => s.name === server.name)
  if (fresh && fresh.tools && fresh.tools.length) {
    toolsViewer.value = fresh
  }
}

async function doTest(server) {
  testing.value = server.name
  error.value = ''
  try {
    const res = await testServer(server.name)
    testTargetName.value = server.displayName || server.name
    testTargetTransport.value = server.transport
    testResult.value = res
    await load()  // 刷新卡片上的 lastTest 摘要
  } catch (e) {
    error.value = `连接测试失败：${e.message}`
  } finally {
    testing.value = ''
  }
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.mcp-page {
  max-width: var(--content-max);
  margin: 0 auto;
  color: var(--text-2);
  animation: fadeIn var(--dur-slow) var(--ease-out) both;
}

/* ===== 页头 ===== */
.mcp-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.head-main {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--amber-500);
  margin-bottom: 8px;
}

.mcp-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.02em;
  color: var(--text-1);
}

.mcp-subtitle {
  margin: 7px 0 0;
  font-size: 13px;
  color: var(--text-3);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* ===== 按钮 ===== */
.btn-primary,
.btn-secondary,
.btn-refresh,
.btn-ghost,
.btn-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--ink-750);
  color: var(--text-1);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast),
    color var(--dur-fast), box-shadow var(--dur-fast), filter var(--dur-fast),
    transform var(--dur-fast);
}

.btn-primary {
  background: var(--amber-grad);
  border-color: transparent;
  color: var(--amber-ink);
  font-weight: 650;
  box-shadow: var(--shadow-1), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--line-2);
  color: var(--text-2);
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--line-3);
  color: var(--text-1);
}

.btn-refresh {
  background: transparent;
  border-color: var(--line-2);
  color: var(--text-3);
}

.btn-refresh:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--line-3);
  color: var(--text-1);
}

.btn-ghost {
  background: transparent;
  border-color: transparent;
  color: var(--text-2);
}

.btn-ghost:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-1);
}

.btn-danger {
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.32);
  color: var(--coral-400);
  font-weight: 600;
}

.btn-danger:hover:not(:disabled) {
  background: rgba(233, 119, 110, 0.2);
  border-color: rgba(233, 119, 110, 0.55);
}

.btn-primary:disabled,
.btn-secondary:disabled,
.btn-refresh:disabled,
.btn-ghost:disabled,
.btn-danger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-primary:active:not(:disabled),
.btn-secondary:active:not(:disabled),
.btn-refresh:active:not(:disabled),
.btn-ghost:active:not(:disabled),
.btn-danger:active:not(:disabled) {
  transform: translateY(1px);
}

.spinning {
  animation: spin 1s linear infinite;
}

/* ===== 状态 ===== */
.state-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 56px 0;
  font-size: 13px;
  color: var(--text-3);
}

.mcp-error {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 12px 14px;
  margin-bottom: 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.3);
  border-radius: var(--r-md);
}

.mcp-error :deep(.app-icon) {
  margin-top: 2px;
}

/* ===== 卡片网格 ===== */
.mcp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}

.mcp-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 16px 18px 14px;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  transition: border-color var(--dur) var(--ease-out), transform var(--dur) var(--ease-out),
    box-shadow var(--dur) var(--ease-out), opacity var(--dur);
}

.mcp-card:hover {
  border-color: var(--line-2);
  transform: translateY(-2px);
  box-shadow: var(--shadow-2), var(--hairline);
}

.mcp-card.disabled {
  opacity: 0.62;
}

.mcp-card.disabled:hover {
  opacity: 0.85;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-top-right {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  color: var(--amber-400);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

.card-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  padding: 0;
  color: var(--text-4);
  background: transparent;
  border: none;
  border-radius: var(--r-xs);
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--dur-fast), background var(--dur-fast), color var(--dur-fast);
}

.mcp-card:hover .card-delete,
.mcp-card:focus-within .card-delete {
  opacity: 1;
}

.card-delete:hover {
  background: var(--coral-a12);
  color: var(--coral-400);
}

.card-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 20px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
  color: var(--jade-400);
  background: var(--jade-a12);
  border: 1px solid rgba(126, 203, 161, 0.24);
  border-radius: var(--r-full);
}

.card-badge.off {
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.045);
  border-color: var(--line-1);
}

.badge-dot {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  border-radius: 50%;
  background: currentColor;
}

.transport-tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.02em;
  white-space: nowrap;
  color: var(--azure-400);
  background: var(--azure-a12);
  border: 1px solid rgba(143, 182, 232, 0.24);
  border-radius: var(--r-full);
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  display: -webkit-box;
  min-height: 38px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-3);
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-target {
  padding: 5px 8px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-3);
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-test {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-width: 0;
  font-size: 12px;
}

.test-ok,
.test-fail {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  height: 20px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: var(--r-full);
}

.test-ok {
  color: var(--jade-400);
  background: var(--jade-a12);
  border: 1px solid rgba(126, 203, 161, 0.24);
}

.test-fail {
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.24);
}

.test-mismatch {
  color: var(--warn-400);
}

.test-meta {
  flex: 1;
  min-width: 0;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 失败信息通常很长：让它独占一行（时间靠右留在首行），
   不再把「不可达 + 错误 + 时间」挤成一条 */
.test-fail + .test-meta {
  flex: 1 1 100%;
  order: 3;
}

.test-time {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}

.card-time {
  font-size: 11.5px;
  color: var(--text-4);
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
  padding-top: 10px;
  border-top: 1px solid var(--line-1);
}

.btn-tiny {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  height: 26px;
  padding: 0 9px;
  font-size: 12px;
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line-1);
  border-radius: var(--r-xs);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}

.btn-tiny:hover:not(:disabled) {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--line-3);
}

.btn-tiny:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ===== 弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(6, 8, 11, 0.68);
  backdrop-filter: blur(8px);
  animation: fadeIn var(--dur) var(--ease-out);
}

.modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 420px;
  max-width: 100%;
  max-height: 86vh;
  padding: 22px;
  overflow-y: auto;
  background: rgba(16, 19, 26, 0.96);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3);
  backdrop-filter: blur(18px);
  animation: fadeUp var(--dur) var(--ease-out);
}

.modal-wide {
  width: 600px;
}

.modal-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.danger-title {
  color: var(--coral-400);
}

.modal-input {
  width: 100%;
  padding: 9px 11px;
  font-size: 13px;
  color: var(--text-1);
  background: var(--bg-input);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  outline: none;
  transition: border-color var(--dur-fast), background var(--dur-fast), box-shadow var(--dur-fast);
}

.modal-input::placeholder {
  color: var(--text-4);
}

.modal-input:hover:not(:disabled) {
  border-color: var(--line-3);
}

.modal-input:focus {
  border-color: var(--amber-a55);
  background: var(--ink-900);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.modal-input:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.form-area {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
  resize: vertical;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.form-row.full {
  grid-column: 1 / -1;
}

.form-label {
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-3);
}

.transport-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.transport-opt {
  height: 30px;
  padding: 0 12px;
  font-size: 12px;
  color: var(--text-3);
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: border-color var(--dur-fast), color var(--dur-fast), background var(--dur-fast);
}

.transport-opt:hover {
  color: var(--text-2);
  border-color: var(--line-3);
}

.transport-opt.picked {
  color: var(--amber-200);
  background: var(--amber-a12);
  border-color: var(--amber-a55);
}

.modal-hint {
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--text-4);
}

.modal-notice {
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-2);
}

.modal-error {
  font-size: 12px;
  line-height: 1.6;
  color: var(--coral-400);
}

.import-overwrite {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--text-2);
  cursor: pointer;
}

.import-overwrite input {
  accent-color: var(--amber-400);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

/* ===== 测试结果 ===== */
.test-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-3);
}

.tool-list {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  padding-top: 6px;
  overflow-y: auto;
  border-top: 1px solid var(--line-1);
}

.tool-list-title {
  padding: 5px 2px 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
}

.tool-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 2px;
  border-bottom: 1px solid var(--line-1);
}

.tool-item:last-child {
  border-bottom: none;
}

.tool-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-1);
  word-break: break-all;
}

.tool-desc {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--text-3);
}

.test-error-text {
  color: var(--coral-400);
}

.tools-viewer-meta {
  font-size: 11.5px;
  color: var(--text-4);
}

.mcp-empty {
  padding: 20px 0;
  font-size: 12.5px;
  color: var(--text-4);
  text-align: center;
}

/* ===== 响应式 ===== */
@media (max-width: 980px) {
  .mcp-header {
    align-items: flex-start;
  }

  .mcp-title {
    font-size: 23px;
  }
}

@media (max-width: 720px) {
  .mcp-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .header-actions {
    width: 100%;
  }
}

@media (max-width: 560px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .modal {
    padding: 18px;
  }
}
</style>
