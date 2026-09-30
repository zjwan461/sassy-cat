<template>
  <div class="sd-page">
    <!-- 顶部信息栏 -->
    <header class="sd-header">
      <button class="btn-back" @click="goBack">← 返回</button>
      <div class="sd-title-block">
        <h2 class="sd-title">🛠️ {{ skill?.displayName || routeName }}</h2>
        <p class="sd-subtitle" :title="skill?.description">{{ skill?.description || '暂无描述' }}</p>
      </div>
      <div class="sd-stats" v-if="skill">
        <span>📄 {{ skill.fileCount }} 文件</span>
        <span>📖 {{ skill.referenceCount }} 参考</span>
        <span>📜 {{ skill.scriptCount }} 脚本</span>
      </div>
    </header>

    <div v-if="loading" class="sd-empty">加载中…</div>
    <div v-else-if="error" class="sd-error">
      {{ error }}
      <button class="btn-retry" @click="load">重试</button>
    </div>

    <div v-else class="sd-body">
      <!-- 左侧目录树 -->
      <aside class="sd-tree">
        <div class="tree-head">
          <span>目录结构</span>
          <button class="btn-newfile" title="在技能内新增文件" @click="openCreate">＋ 新增文件</button>
        </div>
        <div class="tree-scroll">
          <div class="tree-node root" :class="{ active: !currentPath }" @click="openSkillMd">
            <span class="tree-icon">📦</span>
            <span class="tree-name">{{ routeName }}/</span>
          </div>
          <div
            v-for="node in visibleNodes"
            :key="node.path"
            class="tree-node"
            :class="{ active: currentPath === node.path }"
            :style="{ paddingLeft: 10 + node.depth * 16 + 'px' }"
            @click="onNodeClick(node)"
          >
            <span v-if="node.type === 'dir'" class="tree-caret">{{ expanded.has(node.path) ? '▾' : '▸' }}</span>
            <span v-else class="tree-caret"></span>
            <span class="tree-icon">{{ nodeIcon(node) }}</span>
            <span class="tree-name" :title="node.path">{{ node.name }}</span>
            <span class="tree-size" v-if="node.type === 'file'">{{ fmtSize(node.size) }}</span>
          </div>
        </div>
      </aside>

      <!-- 右侧文件查看 / 编辑区 -->
      <section class="sd-viewer">
        <template v-if="currentPath">
          <div class="viewer-head">
            <span class="viewer-path" :title="currentPath">{{ routeName }}/{{ currentPath }}</span>
            <div class="viewer-actions">
              <button
                class="mode-btn"
                :class="{ on: previewMode }"
                @click="previewMode = true"
              >预览</button>
              <button
                class="mode-btn"
                :class="{ on: !previewMode }"
                @click="previewMode = false"
              >编辑</button>
              <button
                class="btn-save"
                :disabled="!dirty || saving"
                @click="saveFile"
              >{{ saving ? '保存中…' : '💾 保存' }}</button>
              <button class="btn-del" title="删除该文件" @click="confirmDelete">🗑 删除</button>
            </div>
          </div>
          <div v-if="fileLoading" class="sd-empty">文件加载中…</div>
          <div v-else-if="fileUnsupported" class="sd-empty">
            ⚠️ {{ fileUnsupported }}
          </div>
          <div v-else class="viewer-body">
            <div v-if="isMarkdown && previewMode" class="md-wrap">
              <MarkdownRenderer :content="fileContent" />
            </div>
            <div
              v-else-if="!isMarkdown && previewMode"
              class="code-wrap"
            >
              <pre class="code-pre"><code class="hljs" v-html="highlightedHtml"></code></pre>
            </div>
            <textarea
              v-else
              v-model="editContent"
              class="code-editor"
              spellcheck="false"
              @keydown.ctrl.s.prevent="saveFile"
              @keydown.meta.s.prevent="saveFile"
            ></textarea>
          </div>
          <div class="viewer-foot" v-if="dirty && !previewMode">
            ● 有未保存的修改（保存前自动备份为 {{ currentPath }}.bak，Ctrl+S 快捷保存）
          </div>
        </template>
        <div v-else class="viewer-placeholder">
          <div class="ph-icon">🗂️</div>
          <p>从左侧目录树选择一个文件查看 / 编辑</p>
          <p class="ph-hint">技能下所有文本文件（含脚本）均可在线修改，保存后即刻生效</p>
        </div>
      </section>
    </div>

    <!-- 新增文件弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-title">＋ 新增文件</div>
        <input
          v-model="newPath"
          class="modal-input"
          placeholder="相对路径，如 scripts/helper.py 或 notes.md"
          maxlength="200"
          @keyup.enter="submitCreate"
        />
        <div class="modal-hint">支持子目录（自动创建）；同名文件已存在时会提示冲突</div>
        <div v-if="createError" class="modal-error">{{ createError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn-primary" :disabled="creating || !newPath.trim()" @click="submitCreate">
            {{ creating ? '创建中…' : '创建并编辑' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createSkillFile, deleteSkillFile, getSkill, readSkillFile, writeSkillFile } from '../api/skills'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/atom-one-dark.css'

// 扩展名 -> highlight.js 语言（未命中则自动探测）
const HL_LANG = {
  py: 'python', js: 'javascript', mjs: 'javascript', cjs: 'javascript', ts: 'typescript',
  json: 'json', md: 'markdown', markdown: 'markdown', sh: 'bash', bash: 'bash',
  bat: 'dos', cmd: 'dos', ps1: 'powershell', yml: 'yaml', yaml: 'yaml', toml: 'ini',
  ini: 'ini', cfg: 'ini', html: 'xml', xml: 'xml', css: 'css', lua: 'lua', go: 'go',
  rs: 'rust', java: 'java', rb: 'ruby', php: 'php', sql: 'sql', txt: 'plaintext',
}

const route = useRoute()
const router = useRouter()
const routeName = computed(() => route.params.name)

const skill = ref(null)
const tree = ref([])
const loading = ref(true)
const error = ref('')

// ---------- 目录树扁平化（展开状态驱动） ----------
const expanded = ref(new Set())

const visibleNodes = computed(() => {
  const out = []
  const walk = (nodes, depth) => {
    for (const n of nodes) {
      out.push({ ...n, depth })
      if (n.type === 'dir' && expanded.value.has(n.path)) {
        walk(n.children || [], depth + 1)
      }
    }
  }
  walk(tree.value, 0)
  return out
})

function nodeIcon(node) {
  if (node.type === 'dir') return '📁'
  const ext = node.name.slice(node.name.lastIndexOf('.')).toLowerCase()
  if (ext === '.md') return '📝'
  if (ext === '.py') return '🐍'
  if (['.js', '.ts', '.json'].includes(ext)) return '📜'
  if (['.sh', '.bat', '.ps1'].includes(ext)) return '⚙️'
  return '📄'
}

function fmtSize(n) {
  if (n == null) return ''
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

function onNodeClick(node) {
  if (node.type === 'dir') {
    const s = new Set(expanded.value)
    s.has(node.path) ? s.delete(node.path) : s.add(node.path)
    expanded.value = s
  } else {
    openFile(node.path)
  }
}

// ---------- 文件查看 / 编辑 ----------
const currentPath = ref('')
const fileContent = ref('')
const editContent = ref('')
const fileLoading = ref(false)
const fileUnsupported = ref('')
const saving = ref(false)
const previewMode = ref(true)

const isMarkdown = computed(() => /\.(md|markdown)$/i.test(currentPath.value))
const dirty = computed(() => currentPath.value && editContent.value !== fileContent.value)

// 脚本/代码预览：highlight.js 语法高亮（按扩展名选语言，未命中自动探测）
const highlightedHtml = computed(() => {
  const code = editContent.value
  if (!code) return ''
  const ext = currentPath.value.slice(currentPath.value.lastIndexOf('.') + 1).toLowerCase()
  const lang = HL_LANG[ext]
  try {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
    }
    return hljs.highlightAuto(code).value
  } catch {
    return code.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>')
  }
})

function findNode(nodes, path) {
  for (const n of nodes) {
    if (n.path === path) return n
    if (n.type === 'dir') {
      const hit = findNode(n.children || [], path)
      if (hit) return hit
    }
  }
  return null
}

async function openFile(path) {
  if (dirty.value && !window.confirm('当前文件有未保存的修改，切换将丢弃，确定吗？')) return
  currentPath.value = path
  fileContent.value = ''
  editContent.value = ''
  fileUnsupported.value = ''
  fileLoading.value = true
  previewMode.value = true
  try {
    const node = findNode(tree.value, path)
    if (node && node.text === false) {
      fileUnsupported.value = '该文件类型不支持在线查看 / 编辑'
    } else {
      const res = await readSkillFile(routeName.value, path)
      fileContent.value = res.content
      editContent.value = res.content
    }
  } catch (e) {
    fileUnsupported.value = e.message
  } finally {
    fileLoading.value = false
  }
}

async function openSkillMd() {
  // 点击根节点：默认展示 SKILL.md（存在时）
  if (skill.value && tree.value.some((n) => n.name === 'SKILL.md')) {
    await openFile('SKILL.md')
  }
}

async function saveFile() {
  if (!dirty.value || saving.value) return
  saving.value = true
  try {
    await writeSkillFile(routeName.value, currentPath.value, editContent.value)
    fileContent.value = editContent.value
    error.value = ''
  } catch (e) {
    window.alert(`保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

// ---------- 删除文件 ----------
const deleting = ref(false)

async function confirmDelete() {
  if (!currentPath.value || deleting.value) return
  if (dirty.value && !window.confirm(`「${currentPath.value}」有未保存的修改，仍要删除吗？`)) return
  if (!window.confirm(`确定删除「${currentPath.value}」吗？该操作不可撤销（.bak 备份将一并删除）。`)) return
  deleting.value = true
  try {
    await deleteSkillFile(routeName.value, currentPath.value)
    currentPath.value = ''
    fileContent.value = ''
    editContent.value = ''
    fileUnsupported.value = ''
    // 重新拉目录树，刷新文件计数与树节点
    await reloadTree()
  } catch (e) {
    window.alert(`删除失败：${e.message}`)
  } finally {
    deleting.value = false
  }
}

// 仅刷新目录树与元信息，不清空当前打开的文件
async function reloadTree() {
  try {
    const res = await getSkill(routeName.value)
    skill.value = res.skill
    tree.value = res.tree || []
  } catch (e) {
    error.value = `刷新目录失败：${e.message}`
  }
}

// ---------- 新增文件 ----------
const showCreate = ref(false)
const newPath = ref('')
const createError = ref('')
const creating = ref(false)

function openCreate() {
  newPath.value = ''
  createError.value = ''
  showCreate.value = true
}

async function submitCreate() {
  const path = newPath.value.trim().replace(/^\/+/, '')
  if (!path) return
  creating.value = true
  createError.value = ''
  try {
    await createSkillFile(routeName.value, path, '')
    showCreate.value = false
    // 重新拉目录树（可能引入了新子目录），并展开新文件所在目录
    await load({ keepFile: false })
    // 展开新文件的各级父目录
    const s = new Set(expanded.value)
    const parts = path.split('/')
    for (let i = 1; i < parts.length; i++) {
      s.add(parts.slice(0, i).join('/'))
    }
    expanded.value = s
    await openFile(path)
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

// ---------- 详情加载 ----------
async function load(opts = {}) {
  loading.value = true
  error.value = ''
  currentPath.value = ''
  fileContent.value = ''
  editContent.value = ''
  try {
    const res = await getSkill(routeName.value)
    skill.value = res.skill
    tree.value = res.tree || []
    // 默认展开 references 与 scripts 之外的顶层目录，方便一眼看到文件
    const top = new Set()
    for (const n of tree.value) {
      if (n.type === 'dir' && !['references', 'scripts'].includes(n.name.toLowerCase())) {
        top.add(n.path)
      }
    }
    expanded.value = top
    // 默认打开 SKILL.md
    if (res.skill && res.tree?.some((n) => n.name === 'SKILL.md')) {
      await openFile('SKILL.md')
    }
  } catch (e) {
    error.value = `加载技能详情失败：${e.message}`
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/skills')
}

watch(routeName, () => load())
onMounted(load)
</script>

<style scoped>
.sd-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 18px 24px 24px;
  color: #e2e8f0;
  overflow: hidden;
}

/* ===== 头部 ===== */
.sd-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
  flex-shrink: 0;
}

.btn-back {
  background: #1e293b;
  color: #cbd5e1;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-back:hover { border-color: #475569; }

.sd-title-block { flex: 1; min-width: 0; }
.sd-title { font-size: 19px; font-weight: 700; margin: 0; }
.sd-subtitle {
  font-size: 12px;
  color: #94a3b8;
  margin: 2px 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sd-stats {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #64748b;
  flex-shrink: 0;
}

.sd-empty {
  padding: 50px 0;
  text-align: center;
  color: #64748b;
  font-size: 14px;
}

.sd-error {
  padding: 16px;
  background: rgba(251, 113, 133, 0.1);
  border: 1px solid rgba(251, 113, 133, 0.35);
  color: #fb7185;
  border-radius: 8px;
  font-size: 14px;
  text-align: center;
}
.btn-retry {
  margin-left: 10px;
  background: transparent;
  border: 1px solid #fb7185;
  color: #fb7185;
  border-radius: 6px;
  padding: 4px 12px;
  cursor: pointer;
}

/* ===== 主体两栏 ===== */
.sd-body {
  flex: 1;
  display: flex;
  gap: 14px;
  min-height: 0;
}

/* 左：目录树 */
.sd-tree {
  width: 270px;
  min-width: 220px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tree-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px 8px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  border-bottom: 1px solid #293548;
  flex-shrink: 0;
}

.btn-newfile {
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.4);
  color: #38bdf8;
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}
.btn-newfile:hover { background: rgba(56, 189, 248, 0.25); }

/* ===== 新增文件弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(2, 6, 23, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: 420px;
  max-width: calc(100vw - 48px);
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
  font-weight: 700;
  color: #f1f5f9;
}
.modal-input {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  color: #e2e8f0;
  padding: 9px 12px;
  font-size: 13px;
  outline: none;
  font-family: Consolas, 'Courier New', monospace;
}
.modal-input:focus { border-color: #38bdf8; }
.modal-hint {
  font-size: 11px;
  color: #64748b;
}
.modal-error {
  font-size: 12px;
  color: #fb7185;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.btn-ghost {
  background: transparent;
  border: 1px solid #334155;
  color: #94a3b8;
  border-radius: 8px;
  padding: 7px 16px;
  font-size: 13px;
  cursor: pointer;
}
.btn-ghost:hover { border-color: #475569; color: #cbd5e1; }
.btn-primary {
  background: #0ea5e9;
  border: none;
  color: #fff;
  border-radius: 8px;
  padding: 7px 16px;
  font-size: 13px;
  cursor: pointer;
}
.btn-primary:hover:not(:disabled) { background: #38bdf8; }
.btn-primary:disabled { opacity: 0.5; cursor: default; }

.tree-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  font-size: 13px;
  color: #cbd5e1;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.tree-node:hover { background: #263449; }
.tree-node.active { background: rgba(56, 189, 248, 0.14); color: #38bdf8; }
.tree-node.root { font-weight: 600; padding-left: 10px; }

.tree-caret {
  width: 12px;
  font-size: 10px;
  color: #64748b;
  flex-shrink: 0;
}
.tree-icon { flex-shrink: 0; }
.tree-name { overflow: hidden; text-overflow: ellipsis; }
.tree-size {
  margin-left: auto;
  font-size: 10px;
  color: #475569;
  padding-right: 6px;
  flex-shrink: 0;
}

/* 右：查看器 */
.sd-viewer {
  flex: 1;
  min-width: 0;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.viewer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid #293548;
  flex-shrink: 0;
}

.viewer-path {
  font-size: 13px;
  font-family: Consolas, 'Courier New', monospace;
  color: #7dd3fc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.mode-btn {
  background: transparent;
  border: 1px solid #334155;
  color: #94a3b8;
  border-radius: 6px;
  padding: 3px 12px;
  font-size: 12px;
  cursor: pointer;
}
.mode-btn.on {
  background: rgba(56, 189, 248, 0.15);
  border-color: #38bdf8;
  color: #38bdf8;
}

.btn-save {
  background: #0ea5e9;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 5px 14px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-save:hover:not(:disabled) { background: #38bdf8; }
.btn-save:disabled { opacity: 0.4; cursor: default; }

.btn-del {
  background: transparent;
  border: 1px solid rgba(251, 113, 133, 0.5);
  color: #fb7185;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-del:hover { background: rgba(251, 113, 133, 0.15); border-color: #fb7185; }

.viewer-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
}

.md-wrap {
  flex: 1;
  min-width: 0;
  padding: 24px 44px 32px;
  box-sizing: border-box;
}
.md-wrap :deep(.markdown-body) {
  max-width: 860px;
}

/* 脚本/代码高亮预览 */
.code-wrap {
  flex: 1;
  min-width: 0;
  overflow: auto;
  background: #0f172a;
}
.code-pre {
  margin: 0;
  padding: 18px 24px;
  min-height: 100%;
}
.code-pre code {
  display: block;
  background: transparent;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre;
}

.code-editor {
  flex: 1;
  background: #0f172a;
  color: #e2e8f0;
  border: none;
  outline: none;
  resize: none;
  padding: 16px 18px;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  tab-size: 4;
  white-space: pre;
}

.viewer-foot {
  padding: 6px 14px;
  font-size: 12px;
  color: #fbbf24;
  border-top: 1px solid #293548;
  flex-shrink: 0;
}

.viewer-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 14px;
}
.ph-icon { font-size: 42px; margin-bottom: 10px; }
.ph-hint { font-size: 12px; color: #475569; }
</style>
