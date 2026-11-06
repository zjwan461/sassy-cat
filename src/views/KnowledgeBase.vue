<template>
  <div class="kb-page">
    <header class="kb-header">
      <div class="header-main">
        <div class="eyebrow">
          <AppIcon name="database" :size="12" />
          知识库
        </div>
        <h1 class="kb-title">藏书阁</h1>
        <p class="kb-subtitle">创建知识库并上传文档，自动分块与向量化入库</p>
      </div>
      <div class="header-actions">
        <button class="ui-btn ui-btn--primary" @click="openCreate">
          <AppIcon name="plus" :size="14" />
          新建知识库
        </button>
      </div>
    </header>

    <div v-if="loading" class="kb-state">
      <span class="ui-spinner"></span>
      <span>加载中…</span>
    </div>
    <div v-else-if="error" class="kb-error">
      <span class="kb-error-icon"><AppIcon name="alert" :size="15" /></span>
      <span>{{ error }}</span>
    </div>
    <div v-else-if="kbs.length === 0" class="ui-card kb-empty">
      <div class="ui-empty">
        <div class="ui-empty-icon"><AppIcon name="book" :size="24" /></div>
        <div class="ui-empty-title">还没有知识库</div>
        <p class="ui-empty-text">点击右上角「新建知识库」开始</p>
        <button class="ui-btn ui-btn--primary kb-empty-cta" @click="openCreate">
          <AppIcon name="plus" :size="14" />
          新建知识库
        </button>
      </div>
    </div>

    <div v-else class="kb-grid">
      <article
        v-for="kb in kbs"
        :key="kb.id"
        class="kb-card"
        @click="goDetail(kb)"
      >
        <div class="card-top">
          <div class="card-top-left">
            <span class="card-icon"><AppIcon name="book" :size="15" /></span>
            <!-- 默认知识库不可修改、不可删除，仅显示标记 -->
            <span v-if="kb.id === DEFAULT_KB_ID" class="card-badge" title="默认知识库，存放聊天上传文件，不可修改、不可删除">
              默认
            </span>
          </div>
          <div v-if="kb.id !== DEFAULT_KB_ID" class="card-top-actions">
            <button class="card-action" title="编辑名称与描述" @click.stop="openEdit(kb)">
              <AppIcon name="edit" :size="14" />
            </button>
            <button class="card-action danger" title="删除知识库" @click.stop="confirmDelete(kb)">
              <AppIcon name="x" :size="14" />
            </button>
          </div>
        </div>
        <div class="card-name" :title="kb.name">{{ kb.name }}</div>
        <div class="card-desc">{{ kb.description || '暂无描述' }}</div>
        <div class="card-meta">
          <span class="meta-item">
            <AppIcon name="file" :size="12" />
            <span class="meta-num">{{ kb.docCount }}</span>
            <span>文档</span>
          </span>
          <span class="meta-item">
            <AppIcon name="layers" :size="12" />
            <span class="meta-num">{{ kb.chunkCount }}</span>
            <span>分块</span>
          </span>
        </div>
        <div class="card-time">
          <AppIcon name="clock" :size="12" />
          <span>{{ formatTime(kb.updatedAt) }}</span>
        </div>
      </article>
    </div>

    <!-- 本地模型未下载：强制阻断弹窗（本地模式必须先下载模型，无「稍后再说」） -->
    <div v-if="showModelWarn" class="modal-mask block-mask">
      <div class="modal modal--warn" role="dialog" aria-modal="true">
        <div class="modal-head">
          <span class="modal-icon"><AppIcon name="alert" :size="16" /></span>
          <div class="modal-title">尚未下载 Embedding 模型</div>
        </div>
        <p class="modal-notice">
          当前知识库使用本地 Embedding 模型，但检测到模型尚未下载，
          文档入库与语义检索无法工作。必须先完成模型下载才能使用知识库
          （自动按显卡和网络选择最优方案）。
        </p>
        <div class="modal-actions">
          <button class="ui-btn ui-btn--primary" @click="goModelDownload">前往下载模型</button>
        </div>
      </div>
    </div>

    <!-- 新建知识库弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head">
          <span class="modal-icon"><AppIcon name="plus" :size="15" /></span>
          <div class="modal-title">新建知识库</div>
        </div>
        <input
          v-model="formName"
          class="ui-input"
          placeholder="知识库名称（必填）"
          maxlength="50"
          @keyup.enter="submitCreate"
        />
        <textarea
          v-model="formDesc"
          class="ui-textarea"
          placeholder="描述（可选）"
          rows="3"
          maxlength="200"
        ></textarea>
        <div v-if="createError" class="modal-error">
          <AppIcon name="alert" :size="13" />
          <span>{{ createError }}</span>
        </div>
        <div class="modal-actions">
          <button class="ui-btn ui-btn--ghost" @click="showCreate = false">取消</button>
          <button class="ui-btn ui-btn--primary" :disabled="creating || !formName.trim()" @click="submitCreate">
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 编辑知识库弹窗（仅修改名称/描述，默认知识库不可编辑） -->
    <div v-if="showEdit" class="modal-mask" @click.self="showEdit = false">
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head">
          <span class="modal-icon"><AppIcon name="edit" :size="15" /></span>
          <div class="modal-title">编辑知识库</div>
        </div>
        <input
          v-model="editName"
          class="ui-input"
          placeholder="知识库名称（必填）"
          maxlength="50"
          @keyup.enter="submitEdit"
        />
        <textarea
          v-model="editDesc"
          class="ui-textarea"
          placeholder="描述（可选）"
          rows="3"
          maxlength="200"
        ></textarea>
        <div v-if="editError" class="modal-error">
          <AppIcon name="alert" :size="13" />
          <span>{{ editError }}</span>
        </div>
        <div class="modal-actions">
          <button class="ui-btn ui-btn--ghost" @click="showEdit = false">取消</button>
          <button class="ui-btn ui-btn--primary" :disabled="editing || !editName.trim()" @click="submitEdit">
            {{ editing ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listKbs, createKb, updateKb, deleteKb } from '../api/kb'
import AppIcon from '../components/AppIcon.vue'

const router = useRouter()
const api = window.electronAPI

// 默认知识库 id 固定为 "default"（与后端 server/db/seed.py 的 DEFAULT_KB_ID 保持一致），不可删除
const DEFAULT_KB_ID = 'default'

const showModelWarn = ref(false)

const kbs = ref([])
const loading = ref(true)
const error = ref('')

const showCreate = ref(false)
const formName = ref('')
const formDesc = ref('')
const creating = ref(false)
const createError = ref('')

// 编辑知识库状态
const showEdit = ref(false)
const editId = ref('')
const editName = ref('')
const editDesc = ref('')
const editing = ref(false)
const editError = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listKbs()
    kbs.value = res.items || []
  } catch (e) {
    error.value = `加载知识库失败：${e.message}`
  } finally {
    loading.value = false
  }
}

function openCreate() {
  formName.value = ''
  formDesc.value = ''
  createError.value = ''
  showCreate.value = true
}

async function submitCreate() {
  const name = formName.value.trim()
  if (!name) return
  creating.value = true
  createError.value = ''
  try {
    await createKb(name, formDesc.value.trim())
    showCreate.value = false
    await load()
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

function openEdit(kb) {
  editId.value = kb.id
  editName.value = kb.name
  editDesc.value = kb.description || ''
  editError.value = ''
  showEdit.value = true
}

async function submitEdit() {
  const name = editName.value.trim()
  if (!name) return
  editing.value = true
  editError.value = ''
  try {
    await updateKb(editId.value, name, editDesc.value.trim())
    showEdit.value = false
    await load()
  } catch (e) {
    editError.value = e.message
  } finally {
    editing.value = false
  }
}

async function confirmDelete(kb) {
  if (kb.id === DEFAULT_KB_ID) {
    alert('默认知识库不可删除')
    return
  }
  if (!window.confirm(`确定删除知识库「${kb.name}」？其下所有文档与向量数据将一并删除。`)) return
  try {
    await deleteKb(kb.id)
    await load()
  } catch (e) {
    alert(`删除失败：${e.message}`)
  }
}

function goDetail(kb) {
  router.push(`/kb/${kb.id}`)
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 进入知识库页时检查：本地模式且模型未下载则强制阻断（弹窗无关闭入口，只能跳转下载）
async function checkEmbeddingModel() {
  if (!api?.getConfig) return // 非 Electron 环境无配置可查，跳过
  try {
    const res = await api.getConfig()
    if (!res.success) return
    const emb = res.config?.rag?.embeddingModel || {}
    const type = emb.type === 'remote' ? 'remote' : 'local'
    if (type === 'local' && emb.downloaded !== true) {
      showModelWarn.value = true
    }
  } catch {
    // 检查失败不打扰用户
  }
}

function goModelDownload() {
  showModelWarn.value = false
  router.push('/settings#rag-model')
}

onMounted(() => {
  load()
  checkEmbeddingModel()
})
</script>

<style scoped>
.kb-page {
  max-width: 1180px;
  margin: 0 auto;
}

/* ===== 页头 ===== */
.kb-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.header-main {
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

.kb-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
  color: var(--text-1);
}

.kb-subtitle {
  margin: 7px 0 0;
  font-size: 13px;
  color: var(--text-3);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-actions .ui-btn {
  height: 36px;
  padding: 0 16px;
}

/* ===== 加载 / 错误 ===== */
.kb-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 72px 0;
  font-size: 13px;
  color: var(--text-3);
}

.kb-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 15px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.24);
  border-radius: var(--r-md);
}

.kb-error-icon {
  display: inline-flex;
  flex-shrink: 0;
}

/* ===== 空状态 ===== */
.kb-empty {
  padding: 0;
}

.kb-empty .ui-empty {
  padding: 64px 24px;
}

.kb-empty-cta {
  margin-top: 4px;
  height: 34px;
}

/* ===== 卡片网格 ===== */
.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(248px, 1fr));
  gap: 14px;
}

.kb-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 15px 16px 13px;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  cursor: pointer;
  overflow: hidden;
  transition: transform var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out),
    box-shadow var(--dur) var(--ease-out);
}

.kb-card:hover {
  transform: translateY(-2px);
  border-color: var(--line-2);
  box-shadow: var(--shadow-2), var(--hairline);
}

.kb-card:focus-visible {
  outline: 2px solid var(--amber-a55);
  outline-offset: 2px;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 2px;
}

.card-top-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: var(--r-sm);
  color: var(--amber-400);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

/* 默认知识库标记 */
.card-badge {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: var(--r-full);
  font-size: 11px;
  font-weight: 600;
  color: var(--amber-300);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
  cursor: default;
  white-space: nowrap;
}

.card-top-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0.5;
  transition: opacity var(--dur);
}

.kb-card:hover .card-top-actions,
.card-top-actions:focus-within {
  opacity: 1;
}

.card-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  color: var(--text-4);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}

.card-action:hover {
  color: var(--amber-300);
  background: var(--amber-a08);
  border-color: var(--amber-a20);
}

.card-action.danger:hover {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.3);
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-3);
  min-height: 38px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 2px;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  font-size: 11.5px;
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line-1);
  border-radius: var(--r-full);
  font-variant-numeric: tabular-nums;
}

.meta-item .app-icon {
  color: var(--text-4);
}

.meta-num {
  font-weight: 600;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}

.card-time {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  padding-top: 6px;
  font-size: 11px;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}

/* ===== 弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(6, 8, 11, 0.68);
  backdrop-filter: blur(2px);
  animation: fadeIn var(--dur) var(--ease-out);
}

/* 强制阻断层：更高透明度与层级，遮住「新建知识库」等全部操作 */
.block-mask {
  background: rgba(6, 8, 11, 0.82);
  z-index: 200;
}

.modal {
  width: min(420px, 100%);
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 22px;
  background: rgba(16, 19, 26, 0.94);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3), var(--hairline);
  backdrop-filter: blur(16px);
  animation: fadeUp var(--dur) var(--ease-out);
}

.modal--warn {
  width: min(440px, 100%);
}

.modal-head {
  display: flex;
  align-items: center;
  gap: 9px;
}

.modal-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: var(--r-sm);
  color: var(--amber-400);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

.modal-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.modal-error {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--coral-400);
}

.modal-notice {
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-3);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

@media (max-width: 980px) {
  .kb-grid {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  }
}

@media (max-width: 640px) {
  .kb-header {
    align-items: flex-start;
  }

  .kb-title {
    font-size: 23px;
  }

  .header-actions,
  .header-actions .ui-btn {
    width: 100%;
  }

  .kb-grid {
    grid-template-columns: 1fr;
  }

  .card-desc {
    min-height: 0;
  }
}
</style>
