<template>
  <div class="kb-page">
    <div class="kb-header">
      <div>
        <h2 class="kb-title">知识库</h2>
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
          <span class="card-icon">📚</span>
          <button class="card-del" title="删除知识库" @click.stop="confirmDelete(kb)">✕</button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listKbs, createKb, deleteKb } from '../api/kb'

const router = useRouter()

const kbs = ref([])
const loading = ref(true)
const error = ref('')

const showCreate = ref(false)
const formName = ref('')
const formDesc = ref('')
const creating = ref(false)
const createError = ref('')

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

async function confirmDelete(kb) {
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

onMounted(load)
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

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}
</style>
