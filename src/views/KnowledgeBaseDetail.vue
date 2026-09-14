<template>
  <div class="kb-detail">
    <!-- 顶栏 -->
    <div class="detail-header">
      <button class="btn-back" @click="goBack">← 返回</button>
      <div class="header-info">
        <h2 class="header-title">{{ kb?.name || '加载中…' }}</h2>
        <p class="header-desc" v-if="kb?.description">{{ kb.description }}</p>
      </div>
      <button class="btn-primary" :disabled="uploading" @click="triggerUpload">
        {{ uploading ? '上传处理中…' : '⬆ 上传文档' }}
      </button>
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.md,.markdown,.txt,.csv,.json,.html,.htm"
        style="display: none"
        @change="onFilesSelected"
      />
    </div>

    <div v-if="pageError" class="page-error">{{ pageError }}</div>

    <div class="detail-body">
      <!-- 左侧：文档列表 -->
      <aside class="doc-panel">
        <div class="panel-title">文档（{{ documents.length }}）</div>
        <div v-if="docsLoading" class="panel-hint">加载中…</div>
        <div v-else-if="documents.length === 0" class="panel-hint">
          暂无文档，点击右上角上传
        </div>
        <ul v-else class="doc-list">
          <li
            v-for="doc in documents"
            :key="doc.id"
            class="doc-item"
            :class="{ selected: selectedDocId === doc.id }"
            @click="selectDoc(doc)"
          >
            <div class="doc-row">
              <span class="doc-name" :title="doc.fileName">{{ doc.fileName }}</span>
              <button class="doc-del" title="删除文档" @click.stop="confirmDeleteDoc(doc)">✕</button>
            </div>
            <div class="doc-meta">
              <span class="status-badge" :class="'st-' + doc.status">{{ statusText(doc.status) }}</span>
              <span class="doc-meta-text">{{ formatSize(doc.fileSize) }}</span>
              <span class="doc-meta-text">{{ doc.chunkCount }} 分块</span>
            </div>
            <div v-if="doc.status === 'error' && doc.error" class="doc-error-msg">{{ doc.error }}</div>
          </li>
        </ul>
      </aside>

      <!-- 右侧：文档分块流式展示 -->
      <section class="chunk-panel">
        <div class="chunk-toolbar">
          <div class="panel-title">
            文档分块
            <span class="chunk-filter" v-if="selectedDoc">
              / {{ selectedDoc.fileName }}
              <button class="filter-clear" @click="selectDoc(null)">显示全部</button>
            </span>
          </div>
          <div class="chunk-actions">
            <span class="stream-progress">
              {{ chunks.length }} / {{ chunkTotal }} 分块
            </span>
            <button class="btn-primary btn-sm" :disabled="chunkLoading" @click="reloadChunks">
              ↻ 刷新
            </button>
          </div>
        </div>

        <div v-if="chunkError" class="chunk-error">{{ chunkError }}</div>

        <div v-if="!chunkLoading && !chunks.length && !chunkError" class="panel-hint chunk-hint">
          暂无文档分块，请先上传文档
        </div>

        <div ref="chunkListEl" class="chunk-list" @scroll="onChunkScroll">
          <div v-for="(c, i) in chunks" :key="c.id" class="chunk-card">
            <div class="chunk-head">
              <span class="chunk-index">#{{ i + 1 }}</span>
              <span class="chunk-source">📄 {{ c.source || '未知来源' }}</span>
              <span class="chunk-len">{{ c.content.length }} 字</span>
              <span class="chunk-actions">
                <button v-if="editingChunkId !== c.id" class="chunk-btn" title="编辑分块" @click="startEdit(c)">✎</button>
                <button class="chunk-btn danger" title="删除分块" @click="confirmDeleteChunk(c)">🗑</button>
              </span>
            </div>
            <!-- 编辑态：文本域 + 保存/取消 -->
            <div v-if="editingChunkId === c.id" class="chunk-edit">
              <textarea v-model="editingContent" class="chunk-edit-textarea" rows="6"></textarea>
              <div class="chunk-edit-actions">
                <button class="btn-ghost btn-sm" @click="cancelEdit">取消</button>
                <button class="btn-primary btn-sm" :disabled="savingChunk" @click="saveEdit(c)">
                  {{ savingChunk ? '保存中…' : '保存' }}
                </button>
              </div>
            </div>
            <!-- 展示态：渲染为 Markdown -->
            <div v-else class="chunk-content markdown-wrap">
              <MarkdownRenderer :content="c.content" />
            </div>
          </div>
          <div v-if="chunkLoading" class="chunk-loading">
            <span class="dot-pulse"></span> 正在加载…
          </div>
          <div v-else-if="chunks.length && chunkFinished" class="chunk-done">
            ✓ 已加载全部分块（{{ chunks.length }}）
          </div>
        </div>
      </section>
    </div>

    <!-- 上传进度遮罩（可切换到后台处理，不阻塞浏览；悬浮条在 App.vue 全局渲染） -->
    <div v-if="uploading && maskVisible" class="upload-mask">
      <div class="upload-box">
        <div class="upload-spinner"></div>
        <div class="upload-title">正在处理文档（{{ uploadDone }}/{{ uploadTotal }}）</div>
        <div class="upload-file">{{ uploadCurrent }}</div>
        <div class="upload-progress">
          <div class="upload-progress-bar" :style="{ width: uploadPercent + '%' }"></div>
        </div>
        <div class="upload-hint">OCR 解析 → 分块 → Embedding 入库，请稍候…<span class="hint-dots"><i></i><i></i><i></i></span></div>
        <div class="upload-actions">
          <button class="btn-ghost btn-sm" @click="maskVisible = false">后台处理</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  listKbs, listDocuments, deleteDocument, fetchChunks, updateChunk, deleteChunk,
} from '../api/kb'
import { useKbUploadState } from '../composables/useKbUploadState'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'

const route = useRoute()
const router = useRouter()
const kbId = route.params.kbId

const kb = ref(null)
const pageError = ref('')

// ---- 文档列表 ----
const documents = ref([])
const docsLoading = ref(true)
const selectedDocId = ref(null)
const selectedDoc = computed(() => documents.value.find(d => d.id === selectedDocId.value) || null)

// ---- 上传（模块级单例队列：切 tab 不中断，数量跨批次累计） ----
const fileInput = ref(null)
const {
  uploading, uploadTotal, uploadDone, uploadCurrent,
  maskVisible, uploadPercent,
  enqueueFiles, takeFailed,
} = useKbUploadState()

// ---- 分块流 ----
// ---- 分块信息流（滚动分页加载） ----
const CHUNK_PAGE_SIZE = 20
const chunks = ref([])
const chunkPage = ref(1)
const chunkTotal = ref(0)
const chunkLoading = ref(false)
const chunkFinished = ref(false)
const chunkError = ref('')
const chunkListEl = ref(null)

// ---- 分块编辑 / 删除 ----
const editingChunkId = ref(null)
const editingContent = ref('')
const savingChunk = ref(false)
const deletingChunkId = ref(null)
function statusText(s) {
  return { pending: '待处理', processing: '处理中', done: '已完成', error: '失败' }[s] || s
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

async function loadKb() {
  try {
    const res = await listKbs()
    kb.value = (res.items || []).find(k => k.id === kbId) || null
    if (!kb.value) pageError.value = '知识库不存在或已被删除'
  } catch (e) {
    pageError.value = `加载失败：${e.message}`
  }
}

async function loadDocs() {
  docsLoading.value = true
  try {
    const res = await listDocuments(kbId)
    documents.value = res.items || []
  } catch (e) {
    pageError.value = `加载文档失败：${e.message}`
  } finally {
    docsLoading.value = false
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

// 每个文件完成即刷新文档列表；全部完成再刷新分块与统计
watch(uploadDone, () => { loadDocs() })
watch(uploading, (busy) => {
  if (!busy) {
    reloadChunks() // 新文档入库后刷新分块信息流
    loadKb()       // 刷新卡片统计（文档数/分块数）
    const failed = takeFailed()
    if (failed.length) {
      alert(`以下文档处理失败：\n${failed.join('\n')}`)
    }
  }
})

function onFilesSelected(ev) {
  const files = Array.from(ev.target.files || [])
  ev.target.value = '' // 允许重复选择同名文件
  if (!files.length) return
  enqueueFiles(kbId, files)
}

async function confirmDeleteDoc(doc) {
  if (!window.confirm(`确定删除文档「${doc.fileName}」？其向量分块将一并删除。`)) return
  try {
    await deleteDocument(kbId, doc.id)
    if (selectedDocId.value === doc.id) {
      selectedDocId.value = null
    }
    await Promise.all([loadDocs(), loadKb()])
    reloadChunks()
  } catch (e) {
    alert(`删除失败：${e.message}`)
  }
}

function selectDoc(doc) {
  // 点击已选中的文档则取消选择
  const newId = doc ? (selectedDocId.value === doc.id ? null : doc.id) : null
  selectedDocId.value = newId
  reloadChunks() // 切换过滤条件后重置信息流
}

// ---- 分块信息流：首屏加载 + 滚动到接近底部自动请求下一页 ----
async function loadChunkPage(reset = false) {
  if (chunkLoading.value) return
  if (!reset && chunkFinished.value) return
  chunkLoading.value = true
  chunkError.value = ''
  try {
    if (reset) {
      chunks.value = []
      chunkPage.value = 1
      chunkFinished.value = false
    }
    const res = await fetchChunks(kbId, chunkPage.value, CHUNK_PAGE_SIZE, selectedDocId.value || '')
    chunks.value.push(...(res.items || []))
    chunkTotal.value = res.total || 0
    chunkFinished.value = chunks.value.length >= chunkTotal.value || (res.items || []).length === 0
    chunkPage.value += 1
  } catch (e) {
    chunkError.value = `分块加载失败：${e.message}`
    chunkFinished.value = true
  } finally {
    chunkLoading.value = false
  }
}
function reloadChunks() {
  loadChunkPage(true)
  nextTick(() => {
    const el = chunkListEl.value
    if (el) el.scrollTop = 0
  })
}

function startEdit(c) {
  editingChunkId.value = c.id
  editingContent.value = c.content
}

function cancelEdit() {
  editingChunkId.value = null
  editingContent.value = ''
}

async function saveEdit(c) {
  const content = editingContent.value.trim()
  if (!content) return alert('分块内容不能为空')
  savingChunk.value = true
  try {
    await updateChunk(kbId, c.id, content)
    editingChunkId.value = null
    editingContent.value = ''
    reloadChunks() // 重新拉取（内容与分块号）
    await Promise.all([loadDocs(), loadKb()]) // 字数/统计刷新
  } catch (e) {
    alert(`编辑失败：${e.message}`)
  } finally {
    savingChunk.value = false
  }
}

async function confirmDeleteChunk(c) {
  if (!window.confirm(`确定删除分块 #（${c.source || ''}）？其向量数据将一并删除。`)) return
  deletingChunkId.value = c.id
  try {
    await deleteChunk(kbId, c.id)
    chunkTotal.value = Math.max(0, chunkTotal.value - 1)
    const idx = chunks.value.findIndex(x => x.id === c.id)
    if (idx !== -1) chunks.value.splice(idx, 1)
    await Promise.all([loadDocs(), loadKb()]) // 文档分块数与知识库统计刷新
  } catch (e) {
    alert(`删除失败：${e.message}`)
  } finally {
    deletingChunkId.value = null
  }
}

function onChunkScroll(ev) {
  const el = ev.target
  // 距底部 80px 内触发下一页
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 80) {
    loadChunkPage(false)
  }
}

function goBack() {
  router.push('/kb')
}

onMounted(async () => {
  await loadKb()
  if (kb.value) {
    await loadDocs()
    loadChunkPage(true) // 进入页面即开始加载第一页分块
  }
})
</script>

<style scoped>
.kb-detail {
  max-width: 1200px;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 64px);
}

/* ===== 顶栏 ===== */
.detail-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

.btn-back {
  background: transparent;
  border: 1px solid #334155;
  color: #94a3b8;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
}
.btn-back:hover { color: #e2e8f0; border-color: #475569; }

.header-info { flex: 1; min-width: 0; }
.header-title { margin: 0; font-size: 20px; color: #f1f5f9; }
.header-desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: #64748b;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.btn-primary {
  background: #4f46e5; color: #fff; border: none; border-radius: 8px;
  padding: 9px 16px; font-size: 14px; cursor: pointer; white-space: nowrap;
}
.btn-primary:hover:not(:disabled) { background: #6366f1; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ghost {
  background: transparent; color: #94a3b8; border: 1px solid #334155;
  border-radius: 8px; padding: 9px 16px; font-size: 14px; cursor: pointer;
}
.btn-ghost:hover { color: #e2e8f0; border-color: #475569; }

.btn-sm { padding: 6px 12px; font-size: 13px; }

.page-error { color: #f87171; font-size: 14px; margin-bottom: 12px; }

/* ===== 主体布局 ===== */
.detail-body {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #cbd5e1;
  margin-bottom: 10px;
}

.panel-hint { color: #64748b; font-size: 13px; padding: 20px 0; text-align: center; }

/* ---- 文档面板 ---- */
.doc-panel {
  width: 280px;
  min-width: 280px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.doc-list {
  list-style: none;
  margin: 0; padding: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-item {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.doc-item:hover { border-color: #475569; }
.doc-item.selected { border-color: #4f46e5; }

.doc-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.doc-name {
  font-size: 13px;
  color: #e2e8f0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.doc-del {
  background: transparent; border: none; color: #475569;
  cursor: pointer; font-size: 12px; padding: 2px 4px; border-radius: 4px;
}
.doc-del:hover { color: #f87171; }

.doc-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.doc-meta-text { font-size: 11px; color: #64748b; }

.status-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
}
.st-done { background: rgba(34, 197, 94, 0.15); color: #4ade80; }
.st-processing, .st-pending { background: rgba(234, 179, 8, 0.15); color: #facc15; }
.st-error { background: rgba(248, 113, 113, 0.15); color: #f87171; }

.doc-error-msg {
  margin-top: 4px;
  font-size: 11px;
  color: #f87171;
  word-break: break-all;
}

/* ---- 分块面板 ---- */
.chunk-panel {
  flex: 1;
  min-width: 0;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chunk-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.chunk-filter {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
  margin-left: 6px;
}

.filter-clear {
  background: transparent;
  border: none;
  color: #818cf8;
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
  margin-left: 6px;
}

.chunk-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.stream-progress { font-size: 12px; color: #facc15; }

.chunk-error { color: #f87171; font-size: 13px; margin: 8px 0; }

.chunk-hint { flex: 1; display: flex; align-items: center; justify-content: center; }

.chunk-list {
  flex: 1;
  overflow-y: auto;
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}

.chunk-list::-webkit-scrollbar { width: 6px; }
.chunk-list::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }

.chunk-card {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 10px 12px;
}
.chunk-head {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 6px;
}

.chunk-actions { display: inline-flex; align-items: center; gap: 6px; }

.chunk-btn {
  background: transparent;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #94a3b8;
  font-size: 12px;
  line-height: 1;
  padding: 4px 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.chunk-btn:hover { color: #e2e8f0; border-color: #818cf8; background: rgba(129, 140, 248, 0.08); }
.chunk-btn.danger:hover { color: #f87171; border-color: #f87171; background: rgba(248, 113, 113, 0.08); }


.chunk-index { color: #818cf8; font-weight: 600; }
.chunk-source {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 60%;
}
.chunk-len { margin-left: auto; }

.chunk-content {
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: hidden;
}
.chunk-card:hover .chunk-content { max-height: none; }

/* Markdown 渲染包装：让渲染器的排版与卡片一致 */
.markdown-wrap { white-space: normal; }
.markdown-wrap :deep(.markdown-body) {
  font-size: 13px;
  color: #cbd5e1;
}
.markdown-wrap :deep(.markdown-body p) { margin: 0 0 8px; }
.markdown-wrap :deep(.markdown-body p:last-child) { margin-bottom: 0; }
.markdown-wrap :deep(.markdown-body pre) { margin: 8px 0; }
.markdown-wrap :deep(.markdown-body code) { font-size: 12px; }
.markdown-wrap :deep(.markdown-body img) { max-width: 100%; }

/* 分块编辑态 */
.chunk-edit { display: flex; flex-direction: column; gap: 8px; }
.chunk-edit-textarea {
  width: 100%;
  box-sizing: border-box;
  background: #0f172a;
  border: 1px solid #4f46e5;
  border-radius: 8px;
  color: #e2e8f0;
  font-size: 13px;
  font-family: Consolas, monospace;
  line-height: 1.6;
  padding: 10px 12px;
  resize: vertical;
  outline: none;
}
.chunk-edit-textarea:focus { border-color: #818cf8; }
.chunk-edit-actions { display: flex; justify-content: flex-end; gap: 8px; }

.chunk-loading {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.chunk-done {
  text-align: center;
  color: #4ade80;
  font-size: 13px;
  padding: 10px;
}

.dot-pulse {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #818cf8;
  animation: pulse 1s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

/* ---- 上传遮罩 ---- */
.upload-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.upload-box {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 24px 32px;
  text-align: center;
  max-width: 420px;
  animation: box-in 0.25s ease;
}
@keyframes box-in {
  from { opacity: 0; transform: translateY(10px) scale(0.97); }
  to { opacity: 1; transform: none; }
}

.upload-title { font-size: 16px; font-weight: 600; color: #f1f5f9; }
.upload-file {
  margin-top: 10px;
  font-size: 13px;
  color: #818cf8;
  word-break: break-all;
}
.upload-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
  display: inline-flex;
  align-items: center;
}

/* 旋转加载圈 */
.upload-spinner {
  width: 36px;
  height: 36px;
  margin: 0 auto 12px;
  border: 3px solid rgba(129, 140, 248, 0.25);
  border-top-color: #818cf8;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
.upload-spinner.sm {
  width: 14px;
  height: 14px;
  margin: 0;
  border-width: 2px;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 进度条 */
.upload-progress {
  margin-top: 14px;
  height: 6px;
  border-radius: 3px;
  background: #0f172a;
  border: 1px solid #334155;
  overflow: hidden;
}
.upload-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4f46e5, #818cf8);
  border-radius: 3px;
  transition: width 0.4s ease;
}

/* 「请稍候…」逐点跳动 */
.hint-dots { display: inline-flex; margin-left: 2px; }
.hint-dots i {
  width: 3px;
  height: 3px;
  margin-left: 3px;
  border-radius: 50%;
  background: #64748b;
  animation: dot-blink 1.2s infinite;
}
.hint-dots i:nth-child(2) { animation-delay: 0.2s; }
.hint-dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-blink {
  0%, 60%, 100% { opacity: 0.25; }
  30% { opacity: 1; }
}

.upload-actions { margin-top: 16px; }
</style>
