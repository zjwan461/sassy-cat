<template>
  <div class="kb-page">
    <div class="kb-header">
      <div>
        <h2 class="kb-title">藏书阁</h2>
        <p class="kb-subtitle">创建知识库并上传文档，自动分块与向量化入库</p>
      </div>
      <button class="btn-primary" @click="openCreate">＋ 新建知识库</button>
    </div>

    <div v-if="loading" class="kb-empty">加载中…</div>
    <div v-else-if="error" class="kb-error">{{ error }}</div>
    <div v-else-if="kbs.length === 0" class="kb-empty">
      还没有知识库，点击右上角「新建知识库」开始
    </div>

    <div v-else class="kb-grid">
      <div
        v-for="kb in kbs"
        :key="kb.id"
        class="kb-card"
        @click="goDetail(kb)"
      >
        <div class="card-top">
          <div class="card-top-left">
            <span class="card-icon">📚</span>
            <!-- 默认知识库不可修改、不可删除，仅显示标记 -->
            <span v-if="kb.id === DEFAULT_KB_ID" class="card-badge" title="默认知识库，存放聊天上传文件，不可修改、不可删除">
              默认
            </span>
          </div>
          <div v-if="kb.id !== DEFAULT_KB_ID" class="card-top-actions">
            <button class="card-edit" title="编辑名称与描述" @click.stop="openEdit(kb)">✎</button>
            <button class="card-del" title="删除知识库" @click.stop="confirmDelete(kb)">✕</button>
          </div>
        </div>
        <div class="card-name" :title="kb.name">{{ kb.name }}</div>
        <div class="card-desc">{{ kb.description || '暂无描述' }}</div>
        <div class="card-meta">
          <span class="meta-item">📄 {{ kb.docCount }} 文档</span>
          <span class="meta-item">🧩 {{ kb.chunkCount }} 分块</span>
        </div>
        <div class="card-time">{{ formatTime(kb.updatedAt) }}</div>
      </div>
    </div>

    <!-- 本地模型未下载：强制阻断弹窗（本地模式必须先下载模型，无「稍后再说」） -->
    <div v-if="showModelWarn" class="modal-mask block-mask">
      <div class="modal">
        <div class="modal-title">⚠️ 尚未下载 Embedding 模型</div>
        <p class="modal-notice">
          当前知识库使用本地 Embedding 模型，但检测到模型尚未下载，
          文档入库与语义检索无法工作。必须先完成模型下载才能使用知识库
          （自动按显卡和网络选择最优方案）。
        </p>
        <div class="modal-actions">
          <button class="btn-primary" @click="goModelDownload">前往下载模型</button>
        </div>
      </div>
    </div>

    <!-- 新建知识库弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-title">新建知识库</div>
        <input
          v-model="formName"
          class="modal-input"
          placeholder="知识库名称（必填）"
          maxlength="50"
          @keyup.enter="submitCreate"
        />
        <textarea
          v-model="formDesc"
          class="modal-textarea"
          placeholder="描述（可选）"
          rows="3"
          maxlength="200"
        ></textarea>
        <div v-if="createError" class="modal-error">{{ createError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn-primary" :disabled="creating || !formName.trim()" @click="submitCreate">
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 编辑知识库弹窗（仅修改名称/描述，默认知识库不可编辑） -->
    <div v-if="showEdit" class="modal-mask" @click.self="showEdit = false">
      <div class="modal">
        <div class="modal-title">编辑知识库</div>
        <input
          v-model="editName"
          class="modal-input"
          placeholder="知识库名称（必填）"
          maxlength="50"
          @keyup.enter="submitEdit"
        />
        <textarea
          v-model="editDesc"
          class="modal-textarea"
          placeholder="描述（可选）"
          rows="3"
          maxlength="200"
        ></textarea>
        <div v-if="editError" class="modal-error">{{ editError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="showEdit = false">取消</button>
          <button class="btn-primary" :disabled="editing || !editName.trim()" @click="submitEdit">
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
  max-width: 1100px;
}

.kb-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.kb-title {
  margin: 0;
  font-size: 22px;
  color: #f1f5f9;
}

.kb-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
}

.btn-primary {
  background: #4f46e5;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 9px 16px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-primary:hover:not(:disabled) { background: #6366f1; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ghost {
  background: transparent;
  color: #94a3b8;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 9px 16px;
  font-size: 14px;
  cursor: pointer;
}
.btn-ghost:hover { color: #e2e8f0; border-color: #475569; }

.kb-empty {
  padding: 80px 0;
  text-align: center;
  color: #64748b;
  font-size: 14px;
}

.kb-error {
  padding: 20px;
  color: #f87171;
  font-size: 14px;
}

/* ===== 卡片网格 ===== */
.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.kb-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kb-card:hover {
  border-color: #4f46e5;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-icon { font-size: 24px; }

/* 默认知识库标记 */
.card-badge {
  background: rgba(79, 70, 229, 0.15);
  color: #818cf8;
  border: 1px solid rgba(79, 70, 229, 0.4);
  border-radius: 6px;
  font-size: 11px;
  padding: 2px 8px;
  cursor: default;
}

.card-top-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-top-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-edit {
  background: transparent;
  border: none;
  color: #475569;
  font-size: 14px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
}
.card-edit:hover { color: #818cf8; background: rgba(79, 70, 229, 0.1); }

.card-del {
  background: transparent;
  border: none;
  color: #475569;
  font-size: 14px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
}
.card-del:hover { color: #f87171; background: rgba(248, 113, 113, 0.1); }

.card-name {
  font-size: 16px;
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-desc {
  font-size: 12px;
  color: #64748b;
  min-height: 32px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #94a3b8;
}

.card-time {
  font-size: 11px;
  color: #475569;
}

/* ===== 弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

/* 强制阻断层：更高透明度与层级，遮住「新建知识库」等全部操作 */
.block-mask {
  background: rgba(0, 0, 0, 0.75);
  z-index: 200;
}

.modal {
  width: 400px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: #f1f5f9;
}

.modal-input,
.modal-textarea {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 10px 12px;
  color: #e2e8f0;
  font-size: 14px;
  outline: none;
  font-family: inherit;
  resize: vertical;
}
.modal-input:focus,
.modal-textarea:focus { border-color: #4f46e5; }

.modal-error {
  color: #f87171;
  font-size: 12px;
}

.modal-notice {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #94a3b8;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}
</style>
