<template>
  <div class="skill-page">
    <div class="skill-header">
      <div>
        <h2 class="skill-title">Skill</h2>
        <p class="skill-subtitle">本喵的十八般武艺 🛠️ 点击卡片查看与编辑技能文件</p>
      </div>
      <div class="header-actions">
        <button class="btn-primary" @click="openCreate">＋ 新增</button>
        <button class="btn-secondary" @click="openImport">⇪ 导入</button>
        <button class="btn-refresh" :disabled="loading" @click="load">
          <span :class="{ spinning: loading }">⟳</span> 刷新
        </button>
      </div>
    </div>

    <div v-if="loading" class="skill-empty">加载中…</div>
    <div v-else-if="error" class="skill-error">{{ error }}</div>
    <div v-else-if="skills.length === 0" class="skill-empty">
      还没有任何技能，点击右上角「＋ 新增」创建第一个技能吧
    </div>

    <div v-else class="skill-grid">
      <div
        v-for="skill in skills"
        :key="skill.name"
        class="skill-card"
        @click="goDetail(skill)"
      >
        <div class="card-top">
          <span class="card-icon">🛠️</span>
          <div class="card-top-right">
            <span v-if="!skill.hasSkillMd" class="card-badge warn" title="缺少 SKILL.md，agent 可能无法加载该技能">缺 SKILL.md</span>
            <button
              class="card-export"
              title="导出为 zip"
              @click.stop="doExport(skill)"
            >⤓</button>
            <button
              class="card-delete"
              title="删除该技能"
              @click.stop="askDelete(skill)"
            >✕</button>
          </div>
        </div>
        <div class="card-name" :title="skill.name">{{ skill.displayName }}</div>
        <div class="card-desc">{{ skill.description || '暂无描述' }}</div>
        <div class="card-meta">
          <span class="meta-item">📄 {{ skill.fileCount }} 文件</span>
          <span class="meta-item">📖 {{ skill.referenceCount }} 参考</span>
          <span class="meta-item">📜 {{ skill.scriptCount }} 脚本</span>
        </div>
        <div class="card-time" v-if="skill.updatedAt">更新于 {{ formatTime(skill.updatedAt) }}</div>
      </div>
    </div>

    <!-- 新增技能弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-title">＋ 新增 Skill</div>
        <input
          v-model="newName"
          class="modal-input"
          placeholder="技能名称，如 my-skill"
          maxlength="64"
          @keyup.enter="submitCreate"
        />
        <div class="modal-hint">仅限字母、数字、-、_、.，将在 runtime/skills 下创建同名目录并生成 SKILL.md 骨架</div>
        <div v-if="createError" class="modal-error">{{ createError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn-primary" :disabled="creating" @click="submitCreate">
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 导入技能弹窗 -->
    <div v-if="showImport" class="modal-mask" @click.self="showImport = false">
      <div class="modal">
        <div class="modal-title">⇪ 导入 Skill</div>
        <label class="import-file" :class="{ picked: importFile }">
          <input type="file" accept=".zip" hidden @change="onFilePick" />
          <span>{{ importFile ? `📦 ${importFile.name}` : '点击选择技能 zip 包（≤20MB）' }}</span>
        </label>
        <input
          v-model="importName"
          class="modal-input"
          placeholder="技能名称（可选，缺省取 zip 顶层目录名）"
          maxlength="64"
        />
        <label class="import-overwrite">
          <input type="checkbox" v-model="importOverwrite" />
          同名技能已存在时覆盖
        </label>
        <div class="modal-hint">zip 包结构：顶层单个技能目录（含 SKILL.md），或根目录直接放 SKILL.md</div>
        <div v-if="importError" class="modal-error">{{ importError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="showImport = false">取消</button>
          <button class="btn-primary" :disabled="importing || !importFile" @click="submitImport">
            {{ importing ? '导入中…' : '导入' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="modal-mask" @click.self="deleteTarget = null">
      <div class="modal">
        <div class="modal-title danger-title">⚠️ 删除 Skill</div>
        <p class="modal-notice">
          确定要删除「{{ deleteTarget.displayName }}」吗？该技能目录下的所有文件（{{ deleteTarget.fileCount }} 个）将被永久删除，此操作不可恢复。
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listSkills, createSkill, deleteSkill, exportSkill, importSkill } from '../api/skills'

const router = useRouter()

const skills = ref([])
const loading = ref(true)
const error = ref('')

// 新增技能
const showCreate = ref(false)
const newName = ref('')
const creating = ref(false)
const createError = ref('')

// 删除技能
const deleteTarget = ref(null)
const deleting = ref(false)
const deleteError = ref('')

// 导入/导出技能
const showImport = ref(false)
const importFile = ref(null)
const importName = ref('')
const importOverwrite = ref(false)
const importing = ref(false)
const importError = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listSkills()
    skills.value = res.items || []
  } catch (e) {
    error.value = `加载技能列表失败：${e.message}`
  } finally {
    loading.value = false
  }
}

function openCreate() {
  newName.value = ''
  createError.value = ''
  showCreate.value = true
}

async function submitCreate() {
  const name = newName.value.trim()
  if (!name) {
    createError.value = '请填写技能名称'
    return
  }
  creating.value = true
  createError.value = ''
  try {
    await createSkill(name)
    showCreate.value = false
    await load()
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

function openImport() {
  importFile.value = null
  importName.value = ''
  importOverwrite.value = false
  importError.value = ''
  showImport.value = true
}

function onFilePick(e) {
  const f = e.target.files && e.target.files[0]
  if (f) {
    importFile.value = f
    importError.value = ''
  }
  e.target.value = ''  // 允许重复选择同一文件
}

async function submitImport() {
  if (!importFile.value) {
    importError.value = '请先选择 zip 文件'
    return
  }
  importing.value = true
  importError.value = ''
  try {
    await importSkill(importFile.value, {
      name: importName.value.trim(),
      overwrite: importOverwrite.value,
    })
    showImport.value = false
    await load()
  } catch (e) {
    importError.value = e.message
  } finally {
    importing.value = false
  }
}

async function doExport(skill) {
  try {
    await exportSkill(skill.name)
  } catch (e) {
    error.value = `导出技能失败：${e.message}`
  }
}

function askDelete(skill) {
  deleteError.value = ''
  deleteTarget.value = skill
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await deleteSkill(deleteTarget.value.name)
    deleteTarget.value = null
    await load()
  } catch (e) {
    deleteError.value = e.message
  } finally {
    deleting.value = false
  }
}

function goDetail(skill) {
  router.push(`/skills/${encodeURIComponent(skill.name)}`)
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
.skill-page {
  padding: 24px;
  height: 100%;
  overflow-y: auto;
  color: #e2e8f0;
}

.skill-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.skill-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 4px;
}

.skill-subtitle {
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

.skill-empty {
  padding: 60px 0;
  text-align: center;
  color: #64748b;
  font-size: 14px;
}

.skill-error {
  padding: 16px;
  background: rgba(251, 113, 133, 0.1);
  border: 1px solid rgba(251, 113, 133, 0.35);
  color: #fb7185;
  border-radius: 8px;
  font-size: 14px;
}

/* ===== 卡片网格 ===== */
.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.skill-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.skill-card:hover {
  border-color: #38bdf8;
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(56, 189, 248, 0.12);
}

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

.card-export,
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
.skill-card:hover .card-export,
.skill-card:hover .card-delete { opacity: 1; }
.card-export:hover { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
.card-delete:hover { background: rgba(239, 68, 68, 0.18); color: #f87171; }

.card-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
}
.card-badge.warn {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
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
  height: 54px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.card-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #64748b;
}

.card-time {
  font-size: 11px;
  color: #475569;
  border-top: 1px solid #293548;
  padding-top: 8px;
}

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
}

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
}
.modal-input:focus { border-color: #4f46e5; }

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

.import-file {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #475569;
  border-radius: 8px;
  padding: 18px 12px;
  font-size: 13px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s;
}
.import-file:hover { border-color: #4f46e5; color: #cbd5e1; }
.import-file.picked { border-color: #34d399; color: #34d399; }

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
</style>
