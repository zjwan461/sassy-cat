<template>
  <div class="mcp-page">
    <div class="mcp-header">
      <div>
        <h2 class="mcp-title">MCP</h2>
        <p class="mcp-subtitle">MCP 服务的注册与发现 🔌 已启用的 Server 工具将自动装配给本喵</p>
      </div>
      <div class="header-actions">
        <button class="btn-primary" @click="openCreate">＋ 注册</button>
        <button class="btn-secondary" @click="openImport">⇪ 导入</button>
        <button class="btn-secondary" :disabled="!servers.length" @click="doExport">⤓ 导出</button>
        <button class="btn-refresh" :disabled="loading" @click="load">
          <span :class="{ spinning: loading }">⟳</span> 刷新
        </button>
      </div>
    </div>

    <div v-if="loading" class="mcp-empty">加载中…</div>
    <div v-else-if="error" class="mcp-error">{{ error }}</div>
    <div v-else-if="servers.length === 0" class="mcp-empty">
      还没有注册任何 MCP Server，点击右上角「＋ 注册」添加第一个吧
    </div>

    <div v-else class="mcp-grid">
      <div v-for="server in servers" :key="server.name" class="mcp-card" :class="{ disabled: !server.enabled }">
        <div class="card-top">
          <span class="card-icon">🔌</span>
          <div class="card-top-right">
            <span class="card-badge" :class="{ off: !server.enabled }">{{ server.enabled ? '已启用' : '已停用' }}</span>
            <span class="transport-tag" :title="transportTitle(server.transport)">{{ transportLabel(server.transport) }}</span>
            <button class="card-delete" title="删除该注册" @click="askDelete(server)">✕</button>
          </div>
        </div>
        <div class="card-name" :title="server.name">{{ server.displayName || server.name }}</div>
        <div class="card-desc">{{ server.description || '暂无描述' }}</div>
        <div class="card-target" :title="server.target">{{ server.target || '—' }}</div>
        <div class="card-test" v-if="server.lastTest">
          <template v-if="server.lastTest.ok">
            <span class="test-ok">✓ 连通</span>
            <span class="test-meta">
              {{ server.lastTest.toolCount }} 个工具 · {{ server.lastTest.latencyMs }}ms
              <span v-if="server.lastTest.mismatch" class="test-mismatch" :title="`注册为 ${server.transport}，实际以 ${server.lastTest.usedTransport} 连通，建议编辑改为该传输`">
                （经 {{ transportLabel(server.lastTest.usedTransport) }} 回退连通）
              </span>
            </span>
          </template>
          <template v-else>
            <span class="test-fail">✗ 不可达</span>
            <span class="test-meta" :title="server.lastTest.error">{{ server.lastTest.error }}</span>
          </template>
          <span class="test-time">{{ formatTime(server.lastTest.at) }}</span>
        </div>
        <div class="card-time" v-else>尚未测试连接</div>
        <div class="card-actions">
          <button class="btn-tiny" :disabled="testing === server.name" @click="doTest(server)">
            {{ testing === server.name ? '测试中…' : '⚡ 测试' }}
          </button>
          <button
            class="btn-tiny"
            :disabled="!(server.tools && server.tools.length)"
            :title="server.tools && server.tools.length ? `查看已发现的 ${server.tools.length} 个工具` : '尚未测试发现工具'"
            @click="openTools(server)"
          >🔧 工具{{ server.tools && server.tools.length ? ` (${server.tools.length})` : '' }}</button>
          <button class="btn-tiny" @click="openEdit(server)">✎ 编辑</button>
          <button class="btn-tiny" @click="toggleEnabled(server)">{{ server.enabled ? '⏸ 停用' : '▶ 启用' }}</button>
        </div>
      </div>
    </div>

    <!-- 注册/编辑弹窗 -->
    <div v-if="showForm" class="modal-mask" @click.self="closeForm">
      <div class="modal modal-wide">
        <div class="modal-title">{{ editingName ? '✎ 编辑 MCP Server' : '＋ 注册 MCP Server' }}</div>
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
        <div class="modal-title">⇪ 导入 MCP 配置</div>
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
        <div class="modal-title danger-title">⚠️ 删除 MCP Server</div>
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
        <div class="modal-title">🔧 工具列表 — {{ toolsViewer.displayName || toolsViewer.name }}</div>
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
            {{ testing === toolsViewer.name ? '发现中…' : '⚡ 重新发现' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 测试结果弹窗 -->
    <div v-if="testResult" class="modal-mask" @click.self="testResult = null">
      <div class="modal modal-wide">
        <div class="modal-title" :class="{ 'danger-title': !testResult.ok }">
          {{ testResult.ok ? '✓ 连接成功' : '✗ 连接失败' }} — {{ testTargetName }}
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
  padding: 24px;
  height: 100%;
  overflow-y: auto;
  color: #e2e8f0;
}

.mcp-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.mcp-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 4px;
}

.mcp-subtitle {
  font-size: 13px;
  color: #94a3b8;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.btn-refresh {
  background: #1e293b;
  color: #cbd5e1;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-refresh:hover { border-color: #475569; background: #263449; }
.btn-refresh:disabled { opacity: 0.6; cursor: default; }
.spinning { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.btn-primary {
  background: #4f46e5;
  color: #fff;
  border: 1px solid #4f46e5;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-primary:hover { background: #6366f1; border-color: #6366f1; }
.btn-primary:disabled { opacity: 0.6; cursor: default; }

.btn-secondary {
  background: #1e293b;
  color: #cbd5e1;
  border: 1px solid #475569;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-secondary:hover { border-color: #64748b; background: #263449; }
.btn-secondary:disabled { opacity: 0.6; cursor: default; }

.btn-ghost {
  background: transparent;
  color: #94a3b8;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-ghost:hover { border-color: #475569; color: #cbd5e1; }

.btn-danger {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-danger:hover { background: rgba(239, 68, 68, 0.3); }
.btn-danger:disabled { opacity: 0.6; cursor: default; }

.mcp-empty {
  padding: 60px 0;
  text-align: center;
  color: #64748b;
  font-size: 14px;
}

.mcp-error {
  padding: 16px;
  background: rgba(251, 113, 133, 0.1);
  border: 1px solid rgba(251, 113, 133, 0.35);
  color: #fb7185;
  border-radius: 8px;
  font-size: 14px;
  margin-bottom: 16px;
}

/* ===== 卡片网格 ===== */
.mcp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.mcp-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.mcp-card:hover {
  border-color: #38bdf8;
  box-shadow: 0 6px 18px rgba(56, 189, 248, 0.12);
}
.mcp-card.disabled { opacity: 0.6; }

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-top-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-icon {
  font-size: 26px;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(56, 189, 248, 0.12);
  border-radius: 10px;
}

.card-delete {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #475569;
  font-size: 14px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s;
}
.mcp-card:hover .card-delete { opacity: 1; }
.card-delete:hover { background: rgba(239, 68, 68, 0.18); color: #f87171; }

.card-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
}
.card-badge.off {
  background: rgba(100, 116, 139, 0.2);
  color: #94a3b8;
}

.transport-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.12);
  color: #38bdf8;
}

.card-name {
  font-size: 16px;
  font-weight: 600;
  color: #f1f5f9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  height: 36px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-target {
  font-size: 11px;
  color: #64748b;
  font-family: Consolas, Menlo, monospace;
  background: #0f172a;
  border-radius: 6px;
  padding: 6px 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-test {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  overflow: hidden;
}
.test-ok { color: #34d399; flex-shrink: 0; }
.test-mismatch { color: #fbbf24; }
.test-fail { color: #f87171; flex-shrink: 0; }
.test-meta {
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.test-time { color: #475569; font-size: 11px; flex-shrink: 0; }

.card-time {
  font-size: 11px;
  color: #475569;
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px solid #293548;
  padding-top: 10px;
}
.btn-tiny {
  background: transparent;
  border: 1px solid #334155;
  color: #cbd5e1;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  flex: 0 0 auto;
}
.btn-tiny:hover { border-color: #4f46e5; color: #a5b4fc; }
.btn-tiny:disabled { opacity: 0.5; cursor: default; }

/* ===== 弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.modal {
  width: 420px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 14px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 86vh;
  overflow-y: auto;
}
.modal-wide { width: 560px; }

.modal-title {
  font-size: 16px;
  font-weight: 700;
  color: #f1f5f9;
}
.danger-title { color: #f87171; }

.modal-input {
  background: #0f172a;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  width: 100%;
  box-sizing: border-box;
}
.modal-input:focus { border-color: #4f46e5; }
.modal-input:disabled { opacity: 0.6; }
.form-area {
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
  resize: vertical;
  line-height: 1.6;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row.full { grid-column: 1 / -1; }
.form-label { font-size: 12px; color: #94a3b8; }

.transport-picker { display: flex; gap: 8px; }
.transport-opt {
  background: #0f172a;
  border: 1px solid #334155;
  color: #94a3b8;
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.transport-opt:hover { border-color: #475569; color: #cbd5e1; }
.transport-opt.picked { border-color: #4f46e5; color: #a5b4fc; background: rgba(79, 70, 229, 0.12); }

.modal-hint {
  font-size: 11px;
  color: #64748b;
}

.modal-notice {
  margin: 0;
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.6;
}

.modal-error {
  font-size: 12px;
  color: #f87171;
}

.import-overwrite {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #cbd5e1;
  cursor: pointer;
}
.import-overwrite input { accent-color: #4f46e5; }

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
  color: #94a3b8;
}
.tool-list {
  border-top: 1px solid #293548;
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}
.tool-list-title {
  font-size: 13px;
  color: #cbd5e1;
  font-weight: 600;
}
.tool-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: #0f172a;
  border-radius: 8px;
  padding: 8px 10px;
}
.tool-name {
  font-size: 12px;
  font-family: Consolas, Menlo, monospace;
  color: #38bdf8;
}
.tool-desc {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.5;
}
.test-error-text { color: #f87171; }
.tools-viewer-meta {
  font-size: 12px;
  color: #64748b;
}
</style>
