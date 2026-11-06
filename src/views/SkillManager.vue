<template>
  <div class="skill-page">
    <header class="skill-header">
      <div class="head-main">
        <div class="eyebrow">SKILL · 技能库</div>
        <h2 class="skill-title">Skill</h2>
        <p class="skill-subtitle">本喵的十八般武艺 · 点击卡片查看与编辑技能文件</p>
      </div>
      <div class="header-actions">
        <button class="btn-primary" @click="openCreate">
          <AppIcon name="plus" :size="14" />
          新增
        </button>
        <button class="btn-secondary" @click="openImport">
          <AppIcon name="upload" :size="14" />
          导入
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
    <div v-else-if="error" class="skill-error">
      <AppIcon name="alert" :size="15" />
      <span>{{ error }}</span>
    </div>
    <div v-else-if="skills.length === 0" class="ui-empty">
      <div class="ui-empty-icon"><AppIcon name="wrench" :size="24" /></div>
      <div class="ui-empty-title">还没有任何技能</div>
      <p class="ui-empty-text">点击右上角「新增」创建第一个技能吧</p>
    </div>

    <div v-else class="skill-grid">
      <div
        v-for="skill in skills"
        :key="skill.name"
        class="skill-card"
        @click="goDetail(skill)"
      >
        <div class="card-top">
          <span class="card-icon"><AppIcon name="wrench" :size="17" /></span>
          <div class="card-top-right">
            <span v-if="!skill.hasSkillMd" class="card-badge warn" title="缺少 SKILL.md，agent 可能无法加载该技能">缺 SKILL.md</span>
            <button
              class="card-export"
              title="导出为 zip"
              @click.stop="doExport(skill)"
            ><AppIcon name="download" :size="14" /></button>
            <button
              class="card-delete"
              title="删除该技能"
              @click.stop="askDelete(skill)"
            ><AppIcon name="trash" :size="14" /></button>
          </div>
        </div>
        <div class="card-name" :title="skill.name">{{ skill.displayName }}</div>
        <div class="card-desc">{{ skill.description || '暂无描述' }}</div>
        <div class="card-meta">
          <span class="meta-item"><AppIcon name="file" :size="12" />{{ skill.fileCount }} 文件</span>
          <span class="meta-item"><AppIcon name="book" :size="12" />{{ skill.referenceCount }} 参考</span>
          <span class="meta-item"><AppIcon name="terminal" :size="12" />{{ skill.scriptCount }} 脚本</span>
        </div>
        <div class="card-time" v-if="skill.updatedAt">更新于 {{ formatTime(skill.updatedAt) }}</div>
      </div>
    </div>

    <!-- 新增技能弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-title">
          <AppIcon name="plus" :size="16" />
          新增 Skill
        </div>
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
        <div class="modal-title">
          <AppIcon name="upload" :size="16" />
          导入 Skill
        </div>
        <label class="import-file" :class="{ picked: importFile }">
          <input type="file" accept=".zip" hidden @change="onFilePick" />
          <AppIcon :name="importFile ? 'package' : 'upload'" :size="15" />
          <span>{{ importFile ? importFile.name : '点击选择技能 zip 包（≤20MB）' }}</span>
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
        <div class="modal-title danger-title">
          <AppIcon name="alert" :size="16" />
          删除 Skill
        </div>
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
import AppIcon from '../components/AppIcon.vue'

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
  max-width: var(--content-max);
  margin: 0 auto;
  color: var(--text-2);
  animation: fadeIn var(--dur-slow) var(--ease-out) both;
}

/* ===== 页头 ===== */
.skill-header {
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

.skill-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.02em;
  color: var(--text-1);
}

.skill-subtitle {
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
  color: var(--text-1);
  background: var(--ink-750);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast),
    color var(--dur-fast), box-shadow var(--dur-fast), filter var(--dur-fast),
    transform var(--dur-fast);
}

.btn-primary {
  color: var(--amber-ink);
  background: var(--amber-grad);
  border-color: transparent;
  font-weight: 650;
  box-shadow: var(--shadow-1), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.btn-secondary {
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--line-2);
}

.btn-secondary:hover:not(:disabled) {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--line-3);
}

.btn-refresh {
  color: var(--text-3);
  background: transparent;
  border-color: var(--line-2);
}

.btn-refresh:hover:not(:disabled) {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--line-3);
}

.btn-ghost {
  color: var(--text-2);
  background: transparent;
  border-color: transparent;
}

.btn-ghost:hover:not(:disabled) {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
}

.btn-danger {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.32);
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

.skill-error {
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

.skill-error :deep(.app-icon) {
  margin-top: 2px;
}

/* ===== 卡片网格 ===== */
.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.skill-card {
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
  cursor: pointer;
  transition: border-color var(--dur) var(--ease-out), transform var(--dur) var(--ease-out),
    box-shadow var(--dur) var(--ease-out);
}

.skill-card:hover {
  border-color: var(--line-2);
  transform: translateY(-2px);
  box-shadow: var(--shadow-2), var(--hairline);
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

.card-export,
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

.skill-card:hover .card-export,
.skill-card:hover .card-delete,
.skill-card:focus-within .card-export,
.skill-card:focus-within .card-delete {
  opacity: 1;
}

.card-export:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.07);
}

.card-delete:hover {
  color: var(--coral-400);
  background: var(--coral-a12);
}

.card-badge {
  display: inline-flex;
  align-items: center;
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

.card-badge.warn {
  color: var(--warn-400);
  background: var(--warn-a12);
  border-color: rgba(232, 192, 106, 0.26);
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
  min-height: 56px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-3);
  overflow: hidden;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: var(--text-3);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.meta-item :deep(.app-icon) {
  color: var(--text-4);
}

.card-time {
  padding-top: 8px;
  font-size: 11.5px;
  color: var(--text-4);
  border-top: 1px solid var(--line-1);
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

.import-file {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px 12px;
  font-size: 13px;
  color: var(--text-3);
  background: var(--ink-1000);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: border-color var(--dur-fast), color var(--dur-fast), background var(--dur-fast);
}

.import-file:hover {
  color: var(--amber-200);
  background: var(--amber-a08);
  border-color: var(--amber-a55);
}

.import-file.picked {
  color: var(--jade-400);
  background: var(--jade-a12);
  border-color: rgba(126, 203, 161, 0.4);
  border-style: solid;
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

/* ===== 响应式 ===== */
@media (max-width: 980px) {
  .skill-header {
    align-items: flex-start;
  }

  .skill-title {
    font-size: 23px;
  }
}

@media (max-width: 720px) {
  .skill-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .header-actions {
    width: 100%;
  }
}

@media (max-width: 560px) {
  .modal {
    padding: 18px;
  }
}
</style>
