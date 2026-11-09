<template>
  <div class="kb-detail">
    <!-- 顶栏 -->
    <header class="detail-header">
      <button class="btn-back" @click="goBack">
        <AppIcon name="arrow-left" :size="15" />
        <span>返回</span>
      </button>
      <div class="header-info">
        <div class="eyebrow">知识库 · 文档分块</div>
        <h1 class="header-title" :title="kb?.name">{{ kb?.name || '加载中…' }}</h1>
        <p class="header-desc" v-if="kb?.description">{{ kb.description }}</p>
      </div>
      <button class="ui-btn ui-btn--primary" :disabled="uploading" @click="triggerUpload">
        <span v-if="uploading" class="ui-spinner"></span>
        <AppIcon v-else name="upload" :size="14" />
        {{ uploading ? '上传处理中…' : '上传文档' }}
      </button>
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.md,.markdown,.txt,.csv,.json,.html,.htm"
        style="display: none"
        @change="onFilesSelected"
      />
    </header>

    <div v-if="pageError" class="page-error">
      <AppIcon name="alert" :size="15" />
      <span>{{ pageError }}</span>
    </div>

    <div class="detail-body">
      <!-- 左侧：文档列表 -->
      <aside class="doc-panel">
        <div class="panel-title">
          <span class="panel-title-icon"><AppIcon name="file" :size="13" /></span>
          <span>文档（<span class="panel-count">{{ documents.length }}</span>）</span>
        </div>
        <div v-if="docsLoading" class="panel-hint">
          <span class="ui-spinner"></span>
          <span>加载中…</span>
        </div>
        <div v-else-if="documents.length === 0" class="panel-dropzone">
          <span class="dropzone-icon"><AppIcon name="upload" :size="18" /></span>
          <p class="dropzone-text">暂无文档，点击右上角上传</p>
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
              <button class="doc-del doc-reindex" title="重新索引（重读原始文件并重跑 OCR/分块）" @click.stop="reindexDoc(doc)" :disabled="reindexingId === doc.id">
                <span v-if="reindexingId === doc.id" class="doc-spinner"></span>
                <AppIcon v-else name="refresh" :size="13" />
              </button>
              <button class="doc-del" title="删除文档" @click.stop="confirmDeleteDoc(doc)">
                <AppIcon name="x" :size="13" />
              </button>
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
            <span class="panel-title-icon"><AppIcon name="layers" :size="13" /></span>
            <span>文档分块</span>
            <span class="chunk-filter" v-if="selectedDoc">
              / {{ selectedDoc.fileName }}
              <button class="filter-clear" @click="selectDoc(null)">
                <AppIcon name="x" :size="10" />
                显示全部
              </button>
            </span>
          </div>
          <div class="chunk-actions">
            <span class="stream-progress">
              {{ chunks.length }} / {{ chunkTotal }} 分块
            </span>
            <button class="ui-btn ui-btn--sm" :class="{ 'is-active': searchOpen }" @click="toggleSearch">
              <AppIcon name="search" :size="13" />
              检索测试
            </button>
            <button class="ui-btn ui-btn--sm" :disabled="chunkLoading" @click="reloadChunks">
              <AppIcon name="refresh" :size="13" :class="{ spinning: chunkLoading }" />
              刷新
            </button>
          </div>
        </div>

        <!-- 检索测试：与 Agent 的 search_from_kb 共用同一套混合检索 -->
        <div v-if="searchOpen" class="kb-search-panel">
          <div class="kb-search-bar">
            <div class="kb-search-input-wrap">
              <AppIcon name="search" :size="14" />
              <input
                ref="searchInputEl"
                v-model="searchQuery"
                placeholder="输入问题，测试这个知识库的检索效果…"
                @keydown.enter="runSearch"
              />
            </div>
            <select v-model.number="searchK" class="kb-search-k" title="返回条数">
              <option :value="4">Top 4</option>
              <option :value="8">Top 8</option>
              <option :value="12">Top 12</option>
            </select>
            <label class="kb-search-hybrid" title="向量语义 + BM25 关键词，RRF 融合">
              <input type="checkbox" v-model="searchHybrid" />
              混合检索
            </label>
            <button class="ui-btn ui-btn--primary ui-btn--sm" :disabled="searchLoading || !searchQuery.trim()" @click="runSearch">
              <span v-if="searchLoading" class="ui-spinner"></span>
              {{ searchLoading ? '检索中…' : '检索' }}
            </button>
            <button class="kb-search-close" title="关闭" @click="searchOpen = false">
              <AppIcon name="x" :size="13" />
            </button>
          </div>

          <div v-if="searchError" class="kb-search-error">{{ searchError }}</div>
          <div v-else-if="searchResults.length" class="kb-search-results">
            <div v-for="(hit, i) in searchResults" :key="hit.id" class="kb-hit">
              <div class="kb-hit-head">
                <span class="kb-hit-rank">#{{ i + 1 }}</span>
                <span class="kb-hit-source" :title="hit.source">{{ hit.source || '未知来源' }}</span>
                <span class="kb-hit-match" :class="'m-' + (hit.match || 'vector')">{{ matchText(hit.match) }}</span>
                <span class="kb-hit-score" :title="'融合相关度（归一化）'">{{ Math.round((hit.score || 0) * 100) }}%</span>
                <button v-if="hit.docId" class="kb-hit-jump" @click="jumpToDoc(hit)">查看文档</button>
              </div>
              <div class="kb-hit-content">{{ hit.content }}</div>
            </div>
          </div>
          <div v-else-if="searchSearched && !searchLoading" class="kb-search-empty">
            没有命中任何分块，试试换个问法、减少限定词，或关闭混合检索再试。
          </div>
        </div>

        <div v-if="chunkError" class="chunk-error">
          <AppIcon name="alert" :size="14" />
          <span>{{ chunkError }}</span>
        </div>

        <div v-if="!chunkLoading && !chunks.length && !chunkError" class="chunk-empty">
          <div class="chunk-empty-icon"><AppIcon name="layers" :size="22" /></div>
          <div class="chunk-empty-title">暂无文档分块</div>
          <p class="chunk-empty-text">请先上传文档</p>
        </div>

        <div ref="chunkListEl" class="chunk-list" @scroll="onChunkScroll">
          <div v-for="(c, i) in chunks" :key="c.id" class="chunk-card">
            <div class="chunk-head">
              <span class="chunk-index">#{{ i + 1 }}</span>
              <span class="chunk-source">
                <AppIcon name="file" :size="12" />
                <span class="chunk-source-name">{{ c.source || '未知来源' }}</span>
              </span>
              <span class="chunk-len">{{ c.content.length }} 字</span>
              <span class="chunk-actions">
                <button v-if="editingChunkId !== c.id" class="chunk-btn" title="编辑分块" @click="startEdit(c)">
                  <AppIcon name="edit" :size="13" />
                </button>
                <button class="chunk-btn danger" title="删除分块" @click="confirmDeleteChunk(c)">
                  <AppIcon name="trash" :size="13" />
                </button>
              </span>
            </div>
            <!-- 编辑态：文本域 + 保存/取消 -->
            <div v-if="editingChunkId === c.id" class="chunk-edit">
              <textarea v-model="editingContent" class="chunk-edit-textarea" rows="6"></textarea>
              <div class="chunk-edit-actions">
                <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="cancelEdit">取消</button>
                <button class="ui-btn ui-btn--primary ui-btn--sm" :disabled="savingChunk" @click="saveEdit(c)">
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
            <span class="ui-spinner"></span>
            <span>正在加载…</span>
          </div>
          <div v-else-if="chunks.length && chunkFinished" class="chunk-done">
            <AppIcon name="check" :size="13" />
            <span>已加载全部分块（{{ chunks.length }}）</span>
          </div>
        </div>
      </section>
    </div>

    <!-- 上传进度遮罩（可切换到后台处理，不阻塞浏览；悬浮条在 App.vue 全局渲染） -->
    <div v-if="uploading && maskVisible" class="upload-mask">
      <div class="upload-box">
        <div class="upload-spinner"></div>
        <div class="upload-title">正在处理文档（<span class="tabular">{{ uploadDone }}</span>/<span class="tabular">{{ uploadTotal }}</span>）</div>
        <div class="upload-file">{{ uploadCurrent }}</div>
        <div class="upload-progress">
          <div class="upload-progress-bar" :style="{ width: uploadPercent + '%' }"></div>
        </div>
        <div class="upload-hint">OCR 解析 → 分块 → Embedding 入库，请稍候…<span class="hint-dots"><i></i><i></i><i></i></span></div>
        <div class="upload-actions">
          <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="maskVisible = false">后台处理</button>
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
  searchKb, reindexDocument,
} from '../api/kb'
import { useKbUploadState } from '../composables/useKbUploadState'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import AppIcon from '../components/AppIcon.vue'

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

// ---- 检索测试 ----
// 与 Agent 工具 search_from_kb 共用 /api/kb/{id}/search，结果就是线上召回结果
const searchOpen = ref(false)
const searchInputEl = ref(null)
const searchQuery = ref('')
const searchK = ref(8)
const searchHybrid = ref(true)
const searchLoading = ref(false)
const searchResults = ref([])
const searchError = ref('')
const searchSearched = ref(false)

// ---- 文档重新索引 ----
const reindexingId = ref('')

function matchText(match) {
  return { hybrid: '混合', keyword: '关键词', vector: '语义' }[match] || '语义'
}

function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (searchOpen.value) {
    nextTick(() => searchInputEl.value?.focus())
  }
}

async function runSearch() {
  const query = searchQuery.value.trim()
  if (!query || searchLoading.value) return
  searchLoading.value = true
  searchError.value = ''
  searchSearched.value = false
  try {
    const res = await searchKb(kbId, query, searchK.value, searchHybrid.value)
    searchResults.value = res.items || []
    searchSearched.value = true
  } catch (e) {
    searchError.value = `检索失败：${e.message}`
  } finally {
    searchLoading.value = false
  }
}

function jumpToDoc(hit) {
  if (!hit.docId) return
  selectedDocId.value = hit.docId
  searchOpen.value = false
  reloadChunks()
}

async function reindexDoc(doc) {
  if (reindexingId.value) return
  if (!window.confirm(`重新索引「${doc.fileName}」？\n将重读原始文件并重跑 OCR / 分块 / embedding，期间该文档暂不可用。`)) return
  reindexingId.value = doc.id
  try {
    await reindexDocument(kbId, doc.id)
    await Promise.all([loadDocs(), loadKb()])
    reloadChunks()
  } catch (e) {
    alert(`重新索引失败：${e.message}`)
  } finally {
    reindexingId.value = ''
  }
}
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
  max-width: 1180px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 104px);
  min-height: 480px;
}

/* ===== 顶栏 ===== */
.detail-header {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.btn-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 11px;
  font-size: 12.5px;
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}

.btn-back:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--line-3);
}

.header-info {
  flex: 1;
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
  margin-bottom: 6px;
}

.header-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-desc {
  margin: 5px 0 0;
  font-size: 12.5px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-header .ui-btn {
  height: 36px;
  padding: 0 16px;
}

.detail-header .ui-spinner {
  width: 14px;
  height: 14px;
}

.page-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.24);
  border-radius: var(--r-md);
}

/* ===== 主体布局 ===== */
.detail-body {
  display: flex;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.panel-title-icon {
  display: inline-flex;
  align-items: center;
  color: var(--amber-400);
}

.panel-count {
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}

.panel-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 18px 0;
  font-size: 12.5px;
  color: var(--text-3);
  text-align: center;
}

/* ---- 文档面板 ---- */
.doc-panel,
.chunk-panel {
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  padding: 14px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.doc-panel {
  width: 288px;
  min-width: 288px;
}

/* 面板头做成通栏表头：极淡白底 + 发丝分割 */
.doc-panel > .panel-title {
  margin: -14px -14px 10px;
  padding: 11px 14px;
  background: rgba(255, 255, 255, 0.035);
  border-bottom: 1px solid var(--line-1);
}

/* 空文档态：虚线投放区（复用既有上传入口，不新增行为） */
.panel-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px 12px;
  text-align: center;
  border: 1px dashed var(--line-3);
  border-radius: var(--r-md);
  transition: border-color var(--dur), background var(--dur);
}

.panel-dropzone:hover {
  border-color: var(--amber-a55);
  background: var(--amber-a08);
}

.dropzone-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: var(--r-md);
  color: var(--amber-400);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

.dropzone-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-3);
}

.doc-list {
  list-style: none;
  margin: 0;
  padding: 0 2px 0 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 文档列表按「表格行」处理：发丝分隔线 + hover 行底色 */
.doc-item {
  padding: 9px 8px;
  background: transparent;
  border-bottom: 1px solid var(--line-1);
  border-radius: 0;
  cursor: pointer;
  transition: background var(--dur-fast), box-shadow var(--dur-fast);
}

.doc-item:first-child {
  border-top: 1px solid var(--line-1);
}

.doc-item:hover {
  background: rgba(255, 255, 255, 0.035);
}

.doc-item.selected {
  background: var(--amber-a08);
  box-shadow: inset 2px 0 0 var(--amber-400);
}

.doc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.doc-name {
  font-size: 12.5px;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-del {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  padding: 0;
  color: var(--text-4);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}

.doc-del:hover {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.3);
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  min-width: 0;
}

.doc-meta-text {
  font-size: 10.5px;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 18px;
  padding: 0 7px;
  font-size: 10.5px;
  font-weight: 600;
  border-radius: var(--r-full);
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--line-1);
  white-space: nowrap;
}

.status-badge::before {
  content: '';
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.st-done {
  color: var(--jade-400);
  background: var(--jade-a12);
  border-color: rgba(126, 203, 161, 0.24);
}

.st-processing,
.st-pending {
  color: var(--amber-300);
  background: var(--amber-a12);
  border-color: var(--amber-a20);
}

.st-error {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.24);
}

.doc-error-msg {
  margin-top: 5px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--coral-400);
  word-break: break-all;
}

/* ---- 分块面板 ---- */
.chunk-panel {
  flex: 1;
  min-width: 0;
}

.chunk-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin: -14px -14px 0;
  padding: 11px 14px;
  background: rgba(255, 255, 255, 0.035);
  border-bottom: 1px solid var(--line-1);
}

.chunk-toolbar .panel-title {
  margin-bottom: 0;
  min-width: 0;
}

/* 检索测试按钮的开启态 */
.chunk-actions .ui-btn.is-active {
  color: var(--amber-300);
  background: var(--amber-a12);
  border-color: var(--amber-a35);
}

.chunk-filter {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 4px;
  font-size: 11.5px;
  font-weight: 400;
  color: var(--text-3);
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.filter-clear {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  margin-left: 2px;
  padding: 2px 7px;
  font-size: 11px;
  color: var(--amber-300);
  background: var(--amber-a08);
  border: 1px solid var(--amber-a20);
  border-radius: var(--r-full);
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}

.filter-clear:hover {
  color: var(--amber-200);
  background: var(--amber-a12);
  border-color: var(--amber-a35);
}

.chunk-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.stream-progress {
  font-size: 11.5px;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}

.chunk-error {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 10px 0 0;
  padding: 10px 12px;
  font-size: 12.5px;
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.24);
  border-radius: var(--r-sm);
}

/* ===== 检索测试 ===== */
.kb-search-panel {
  margin: 10px 0 0;
  padding: 10px 12px;
  max-height: 46%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: rgba(0, 0, 0, 0.16);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
}

.kb-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.kb-search-input-wrap {
  flex: 1 1 240px;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 10px;
  color: var(--text-4);
  background: var(--ink-900);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}

.kb-search-input-wrap:focus-within {
  border-color: var(--amber-a55);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.kb-search-input-wrap input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-1);
  font-size: 12.5px;
}

.kb-search-input-wrap input::placeholder {
  color: var(--text-4);
}

.kb-search-k {
  height: 32px;
  padding: 0 8px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--ink-900);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
}

.kb-search-hybrid {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-3);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.kb-search-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-4);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-xs);
  cursor: pointer;
}

.kb-search-close:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
}

.kb-search-results {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
}

.kb-hit {
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
}

.kb-hit-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  font-size: 11px;
  color: var(--text-3);
}

.kb-hit-rank {
  color: var(--amber-300);
  font-weight: 700;
}

.kb-hit-source {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-hit-match {
  padding: 1px 6px;
  color: var(--text-4);
  border: 1px solid var(--line-2);
  border-radius: var(--r-full);
}

.kb-hit-match.m-hybrid {
  color: var(--amber-300);
  background: var(--amber-a12);
  border-color: var(--amber-a35);
}

.kb-hit-match.m-keyword {
  color: #8FD3B6;
  background: rgba(143, 211, 182, 0.1);
  border-color: rgba(143, 211, 182, 0.28);
}

.kb-hit-score {
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}

.kb-hit-jump {
  padding: 0;
  color: var(--amber-300);
  font-size: 11px;
  background: none;
  border: none;
  cursor: pointer;
}

.kb-hit-jump:hover {
  text-decoration: underline;
}

.kb-hit-content {
  max-height: 96px;
  overflow-y: auto;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.kb-search-empty,
.kb-search-error {
  padding: 6px 2px;
  font-size: 12px;
  color: var(--text-4);
}

.kb-search-error {
  color: var(--coral-400);
}

/* 文档重新索引：与删除按钮并排，悬停变琥珀色 */
.doc-reindex:hover:not(:disabled) {
  color: var(--amber-300);
  background: var(--amber-a12);
  border-color: var(--amber-a35);
}

.doc-reindex:disabled {
  opacity: 0.6;
  cursor: default;
}

.doc-spinner {
  width: 11px;
  height: 11px;
  border: 1.5px solid var(--line-3);
  border-top-color: var(--amber-300);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.chunk-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 24px;
  text-align: center;
}

.chunk-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: var(--r-lg);
  color: var(--amber-400);
  background: radial-gradient(circle at 50% 30%, var(--amber-a20), transparent 70%),
    var(--ink-850);
  border: 1px solid var(--line-2);
}

.chunk-empty-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}

.chunk-empty-text {
  margin: 0;
  font-size: 13px;
  color: var(--text-3);
}

/* 空态占据全部高度时，让空的滚动容器不再瓜分空间 */
.chunk-empty + .chunk-list {
  flex: 0 0 auto;
  margin-top: 0;
}

.chunk-list {
  flex: 1;
  overflow-y: auto;
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 4px;
  min-height: 0;
}

.chunk-list::-webkit-scrollbar {
  width: 8px;
}

.chunk-list::-webkit-scrollbar-thumb {
  background: var(--line-2);
  border-radius: var(--r-full);
}

.chunk-card {
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.018);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
  transition: border-color var(--dur-fast), background var(--dur-fast);
}

.chunk-card:hover {
  border-color: var(--line-2);
  background: rgba(255, 255, 255, 0.032);
}

.chunk-head {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  margin-bottom: 7px;
  font-size: 11px;
  color: var(--text-4);
}

.chunk-index {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--amber-400);
  font-variant-numeric: tabular-nums;
}

.chunk-source {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 62%;
  color: var(--text-3);
}

.chunk-source-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chunk-head .chunk-actions {
  gap: 6px;
}

.chunk-len {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}

.chunk-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  color: var(--text-4);
  background: transparent;
  border: 1px solid var(--line-1);
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: color var(--dur-fast), border-color var(--dur-fast), background var(--dur-fast);
}

.chunk-btn:hover {
  color: var(--text-1);
  border-color: var(--line-3);
  background: rgba(255, 255, 255, 0.05);
}

.chunk-btn.danger:hover {
  color: var(--coral-400);
  border-color: rgba(233, 119, 110, 0.4);
  background: var(--coral-a12);
}

.chunk-content {
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-2);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: hidden;
}

.chunk-card:hover .chunk-content {
  max-height: none;
}

/* Markdown 渲染包装：让渲染器的排版与卡片一致 */
.markdown-wrap {
  white-space: normal;
}

.markdown-wrap :deep(.markdown-body) {
  font-size: 12.5px;
  color: var(--text-2);
}

.markdown-wrap :deep(.markdown-body p) {
  margin: 0 0 8px;
}

.markdown-wrap :deep(.markdown-body p:last-child) {
  margin-bottom: 0;
}

.markdown-wrap :deep(.markdown-body pre) {
  margin: 8px 0;
}

.markdown-wrap :deep(.markdown-body code) {
  font-size: 12px;
  font-family: var(--font-mono);
}

.markdown-wrap :deep(.markdown-body img) {
  max-width: 100%;
}

/* 分块编辑态 */
.chunk-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chunk-edit-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-1);
  background: var(--bg-input);
  border: 1px solid var(--amber-a35);
  border-radius: var(--r-sm);
  resize: vertical;
  outline: none;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}

.chunk-edit-textarea:focus {
  border-color: var(--amber-a55);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.chunk-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.chunk-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  font-size: 12.5px;
  color: var(--text-3);
  text-align: center;
}

.chunk-done {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  font-size: 12.5px;
  color: var(--jade-400);
  text-align: center;
}

.spinning {
  animation: spin 1s linear infinite;
}

/* ---- 上传遮罩 ---- */
.upload-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(6, 8, 11, 0.72);
  backdrop-filter: blur(2px);
  animation: fadeIn var(--dur) var(--ease-out);
}

.upload-box {
  width: min(420px, 100%);
  padding: 26px 30px 22px;
  text-align: center;
  background: rgba(16, 19, 26, 0.94);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3), var(--hairline);
  backdrop-filter: blur(16px);
  animation: box-in 0.25s var(--ease-out);
}

@keyframes box-in {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.upload-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.upload-file {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--azure-400);
  word-break: break-all;
}

.upload-hint {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  font-size: 11.5px;
  color: var(--text-4);
}

/* 旋转加载圈：2px 琥珀环 */
.upload-spinner {
  width: 36px;
  height: 36px;
  margin: 0 auto 14px;
  border: 2px solid var(--amber-a20);
  border-top-color: var(--amber-400);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

/* 进度条 */
.upload-progress {
  margin-top: 14px;
  height: 5px;
  border-radius: var(--r-full);
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  overflow: hidden;
}

.upload-progress-bar {
  height: 100%;
  background: var(--amber-grad);
  border-radius: var(--r-full);
  box-shadow: 0 0 10px var(--amber-a35);
  transition: width 0.4s var(--ease-out);
}

/* 「请稍候…」逐点跳动 */
.hint-dots {
  display: inline-flex;
  margin-left: 2px;
}

.hint-dots i {
  width: 3px;
  height: 3px;
  margin-left: 3px;
  border-radius: 50%;
  background: var(--text-4);
  animation: dot-blink 1.2s infinite;
}

.hint-dots i:nth-child(2) {
  animation-delay: 0.2s;
}

.hint-dots i:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes dot-blink {
  0%,
  60%,
  100% {
    opacity: 0.25;
  }
  30% {
    opacity: 1;
  }
}

.upload-actions {
  margin-top: 16px;
}

@media (max-width: 980px) {
  .doc-panel {
    width: 250px;
    min-width: 250px;
  }

  .header-title {
    font-size: 23px;
  }
}

@media (max-width: 760px) {
  .kb-detail {
    height: auto;
    min-height: 0;
  }

  .detail-body {
    flex-direction: column;
  }

  .doc-panel {
    width: 100%;
    min-width: 0;
    max-height: 260px;
  }

  .chunk-panel {
    min-height: 420px;
  }
}
</style>
